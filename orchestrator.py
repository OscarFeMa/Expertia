"""
Coral Thought Orchestrator - Production-Ready Pipeline
Phase A: Cascade Wikidata scanning with progressive QID expansion & checkpoints
Phase B: Web scraping + LLM distillation with EMA scoring
"""

import time
import logging
import json
import asyncio
import os
import re
import signal
import subprocess
import argparse
import math
import requests
import threading
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Set
from datetime import datetime

from dissect_wikidata import ClassHierarchyCache, BatchWikidataExtractor, CHECKPOINT_INTERVAL

LLM_QUERY_TIMEOUT = 180
PHASE_B_PER_SPECIALIST_TIMEOUT = 3600  # 60 min max per specialist per cycle
MAX_PHASE_B_CYCLES = 100
VRAM_WARN_THRESHOLD_MB = 2048
_shutdown_event = threading.Event()

# ── Tier System ──────────────────────────────────────────────────────────────
TIER_NONE = 0
TIER_BRONZE = 1
TIER_SILVER = 2
TIER_GOLD = 3
TIER_LEGEND = 4

TIER_NAMES = {
    TIER_NONE: "None",
    TIER_BRONZE: "Bronze",
    TIER_SILVER: "Silver",
    TIER_GOLD: "Gold",
    TIER_LEGEND: "Legend",
}

FAILURE_PENALTIES = {
    TIER_NONE: 0.965,
    TIER_BRONZE: 0.97,
    TIER_SILVER: 0.98,
    TIER_GOLD: 0.99,
    TIER_LEGEND: 0.99,
}

TIER_CRITERIA = {
    TIER_BRONZE: {"ema": 0.92, "quality": 0.60, "fail_rate": 0.15, "packages": 200},
    TIER_SILVER: {"ema": 0.95, "quality": 0.75, "fail_rate": 0.08, "packages": 500},
    TIER_GOLD: {"ema": 0.97, "quality": 0.85, "fail_rate": 0.03, "packages": 1500},
}

LEGEND_EMA_MIN = 0.999
LEGEND_CYCLES_CLEAN = 50

NURTURE_CYCLE_TIMEOUT = 900  # 15 min per specialist cycle

# ── Nurture Priority Scoring Weights ─────────────────────────────────────────
NURTURE_W_EMA        = 10.0   # Low EMA = high priority
NURTURE_W_FAIL        = 8.0    # High fail rate = high priority
NURTURE_W_STALENESS   = 0.5    # Days since last update
NURTURE_W_PACKAGES    = 3.0    # Few packages = high priority
NURTURE_PACKAGE_TARGET = 500   # Packages target for scoring normalization

# Minimum real Phase B cycles required for tier promotion
MIN_CYCLES_FOR_BRONZE = 3
MIN_CYCLES_FOR_SILVER = 10
MIN_CYCLES_FOR_GOLD = 25


def estimate_tokens(text: str) -> int:
    """Estimate token count from text. Roughly 1 token per 4 chars for English."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def check_ollama_vram() -> Optional[int]:
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                mem_raw = parts[3].upper()
                if 'GB' in mem_raw:
                    return int(float(mem_raw.replace('GB', '')) * 1024)
                if 'MB' in mem_raw:
                    return int(mem_raw.replace('MB', ''))
        return None
    except Exception as e:
        logger.debug(f"ollama ps failed: {e}")
        return None

from database.db_manager import get_db_manager
from llm_manager import LLMRunner
from web_scraper import ModernWebScraper, WebScraperError, RateLimitError
from metrics import MetricsCollector
from knowledge_ingestor import KnowledgeIngestor

from config.settings import (
    LOGS_DIR,
    WIKIDATA_DUMP_PATH,
    WIKIDATA_OUTPUT_DIR as TARGET_OUTPUT_DIR,
    WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
    SUBSPECIALIST_THRESHOLD,
    MAX_SUBSPECIALISTS,
    SUBSPECIALIST_CYCLE_INTERVAL,
    MAX_CHILDREN_PER_PARENT,
    MAX_CASCADE_ENTITIES,
    BLOCKLIST_LABELS,
    BLOCKLIST_LABEL_PREFIXES,
    WIKIDATA_ENTITY_API,
    WIKIDATA_SPARQL_ENDPOINT,
    WIKIDATA_API_USER_AGENT,
    WIKIDATA_LABEL_BATCH_SIZE,
)
from config.log_setup import setup_logging

log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
setup_logging(log_file=log_file)
logger = logging.getLogger(__name__)

SPECIALIST_REGISTRY = [
    {"domain": "SoftwareEngineering", "model": "qwen2.5-coder:3b", "root": "Q80993", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Mathematics", "model": "deepseek-r1:1.5b", "root": "Q395", "props": ["P31", "P279", "P2534", "P192"]},
    {"domain": "Medicine", "model": "phi4-mini:3.8b", "root": "Q11190", "props": ["P31", "P279", "P923", "P780", "P699"]},
    {"domain": "LegalSystem", "model": "llama3.2:3b", "root": "Q7748", "props": ["P31", "P279", "P1684", "P427"]},
    {"domain": "PhilosophyHistory", "model": "phi4-mini:3.8b", "root": "Q5891", "props": ["P31", "P279", "P61"]},
    {"domain": "FinanceEconomics", "model": "phi4-mini:3.8b", "root": "Q8134", "props": ["P31", "P279", "P2283", "P1441"]},
    {"domain": "Physics", "model": "deepseek-r1:1.5b", "root": "Q413", "props": ["P31", "P279", "P2067", "P2541"]},
    {"domain": "Cybersecurity", "model": "qwen2.5-coder:3b", "root": "Q3510521", "props": ["P31", "P279", "P2824"]},
    {"domain": "Bioinformatics", "model": "phi4-mini:3.8b", "root": "Q128570", "props": ["P31", "P279", "P685"]},
    {"domain": "Geopolitics", "model": "llama3.2:3b", "root": "Q159385", "props": ["P31", "P279", "P30"]},
    {"domain": "DataScience", "model": "qwen2.5-coder:3b", "root": "Q2374463", "props": ["P31", "P279", "P2078"]},
    {"domain": "Chemistry", "model": "phi4-mini:3.8b", "root": "Q2329", "props": ["P31", "P279", "P662", "P2067"]},
    {"domain": "ArtHistory", "model": "phi4-mini:3.8b", "root": "Q50637", "props": ["P31", "P279", "P170", "P136"]},
    {"domain": "Electronics", "model": "qwen2.5-coder:3b", "root": "Q11650", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Astronomy", "model": "phi4-mini:3.8b", "root": "Q333", "props": ["P31", "P279", "P2067"]}
]

# Derive WIKIDATA_SCHEMAS from single source of truth
WIKIDATA_SCHEMAS = {s["domain"]: {"root": s["root"], "props": list(s["props"])}
                     for s in SPECIALIST_REGISTRY}

SUPER_EXPERTS = {
    "LanguagesLinguistics": {
        "description": "Language, linguistics, NLP, philology, semiotics and communication theory",
        "members": {"DataScience": 0.25, "PhilosophyHistory": 0.25, "SoftwareEngineering": 0.15, "ArtHistory": 0.15, "LegalSystem": 0.10, "Mathematics": 0.10}
    },
    "VisualArts": {
        "description": "Painting, sculpture, architecture, photography, digital art, design, color theory and visual culture",
        "members": {"ArtHistory": 0.40, "PhilosophyHistory": 0.20, "SoftwareEngineering": 0.12, "Electronics": 0.10, "Chemistry": 0.06, "Physics": 0.06, "Medicine": 0.06}
    },
    "PerformingArts": {
        "description": "Music, dance, theater, opera, film, performance, acoustics and stagecraft",
        "members": {"ArtHistory": 0.25, "PhilosophyHistory": 0.20, "Electronics": 0.20, "SoftwareEngineering": 0.12, "Physics": 0.10, "Medicine": 0.08, "DataScience": 0.05}
    },
    "EconomyFinance": {
        "description": "Financial systems, markets, economic policy and cross-border regulation",
        "members": {"FinanceEconomics": 0.35, "LegalSystem": 0.20, "DataScience": 0.20, "Geopolitics": 0.15, "PhilosophyHistory": 0.10}
    },
    "ArtificialIntelligence": {
        "description": "Machine learning, LLMs, neural networks, AI safety and intelligent systems",
        "members": {"DataScience": 0.30, "SoftwareEngineering": 0.25, "Mathematics": 0.20, "PhilosophyHistory": 0.10, "Electronics": 0.10, "Cybersecurity": 0.05}
    },
    "BiotechnologyHealth": {
        "description": "Bioinformatics, medicine, drug discovery, genomics and healthcare technology",
        "members": {"Bioinformatics": 0.30, "Medicine": 0.25, "Chemistry": 0.20, "DataScience": 0.15, "SoftwareEngineering": 0.10}
    },
    "QuantumPhysics": {
        "description": "Quantum mechanics, particle physics, cosmology and fundamental science",
        "members": {"Physics": 0.35, "Mathematics": 0.25, "Chemistry": 0.15, "Electronics": 0.15, "Astronomy": 0.10}
    },
    "CybersecurityDefense": {
        "description": "Cyber threats, defense strategy, cryptography, compliance and national security",
        "members": {"Cybersecurity": 0.35, "SoftwareEngineering": 0.20, "Electronics": 0.15, "LegalSystem": 0.15, "Mathematics": 0.10, "FinanceEconomics": 0.05}
    },
    "ClimateEnvironment": {
        "description": "Climate change, environmental science, sustainability, green policy and energy transition",
        "members": {"Chemistry": 0.20, "Physics": 0.20, "DataScience": 0.15, "Geopolitics": 0.15, "FinanceEconomics": 0.10, "LegalSystem": 0.10, "Medicine": 0.05, "Astronomy": 0.05}
    },
    "SpaceExploration": {
        "description": "Astronomy, space technology, orbital mechanics, planetary science and satellite systems",
        "members": {"Astronomy": 0.30, "Physics": 0.25, "Electronics": 0.15, "SoftwareEngineering": 0.10, "Mathematics": 0.10, "Chemistry": 0.10}
    },
    "DataPrivacyEthics": {
        "description": "Data protection, privacy regulation, digital ethics, GDPR and responsible AI",
        "members": {"LegalSystem": 0.30, "Cybersecurity": 0.25, "PhilosophyHistory": 0.20, "DataScience": 0.15, "SoftwareEngineering": 0.10}
    },
    "CulturalHeritage": {
        "description": "Art history, cultural preservation, digital archives, museology and conservation",
        "members": {"ArtHistory": 0.30, "PhilosophyHistory": 0.25, "DataScience": 0.15, "SoftwareEngineering": 0.10, "Chemistry": 0.10, "LegalSystem": 0.10}
    },
    "EnergySustainability": {
        "description": "Renewable energy, power systems, battery tech, energy economics and grid modernization",
        "members": {"Physics": 0.25, "Chemistry": 0.20, "Electronics": 0.15, "FinanceEconomics": 0.15, "Geopolitics": 0.10, "DataScience": 0.10, "LegalSystem": 0.05}
    },
    "CryptocurrencyBlockchain": {
        "description": "Cryptocurrencies, blockchain protocols, DeFi, tokenomics, smart contracts and Web3",
        "members": {"FinanceEconomics": 0.25, "Cybersecurity": 0.20, "SoftwareEngineering": 0.20, "DataScience": 0.15, "LegalSystem": 0.10, "Mathematics": 0.05, "PhilosophyHistory": 0.05}
    },
    "EducationTechnology": {
        "description": "Learning systems, educational technology, pedagogy, learning analytics and LMS",
        "members": {"PhilosophyHistory": 0.25, "DataScience": 0.25, "SoftwareEngineering": 0.20, "Mathematics": 0.15, "ArtHistory": 0.10, "Electronics": 0.05}
    },
    "ManufacturingIndustry": {
        "description": "Industry 4.0, automation, robotics, supply chain, smart manufacturing and IoT",
        "members": {"Electronics": 0.25, "SoftwareEngineering": 0.20, "Physics": 0.15, "DataScience": 0.15, "Mathematics": 0.10, "Chemistry": 0.10, "FinanceEconomics": 0.05}
    },
    "Telecommunications": {
        "description": "Communication networks, 5G/6G, signal processing, satellite comms and internet infrastructure",
        "members": {"Electronics": 0.30, "Physics": 0.20, "SoftwareEngineering": 0.20, "DataScience": 0.10, "Mathematics": 0.10, "Astronomy": 0.10}
    },
    "MaterialsScience": {
        "description": "New materials, nanotechnology, polymers, composites, semiconductors and metamaterials",
        "members": {"Chemistry": 0.35, "Physics": 0.25, "Electronics": 0.15, "Mathematics": 0.10, "DataScience": 0.10, "SoftwareEngineering": 0.05}
    },
    "UrbanPlanningSmartCities": {
        "description": "Urban development, smart infrastructure, mobility, civic tech and sustainable cities",
        "members": {"Geopolitics": 0.20, "DataScience": 0.20, "Electronics": 0.15, "FinanceEconomics": 0.15, "LegalSystem": 0.10, "SoftwareEngineering": 0.10, "PhilosophyHistory": 0.05, "ArtHistory": 0.05}
    },
    "DefenseStrategy": {
        "description": "Military strategy, international security, arms control, defense tech and geopolitical risk",
        "members": {"Geopolitics": 0.30, "LegalSystem": 0.15, "Cybersecurity": 0.15, "Physics": 0.10, "Electronics": 0.10, "FinanceEconomics": 0.10, "PhilosophyHistory": 0.10}
    },
    "NeuroscienceCognition": {
        "description": "Brain science, cognitive science, consciousness, neural interfaces and neurotechnology",
        "members": {"Medicine": 0.25, "Bioinformatics": 0.20, "DataScience": 0.15, "Physics": 0.10, "Chemistry": 0.10, "SoftwareEngineering": 0.10, "PhilosophyHistory": 0.10}
    },
    "GeneralKnowledge": {
        "description": "Cross-domain synthesis — all specialists contributing proportionally by packages absorbed",
        "members": {"SoftwareEngineering": 0.08, "Mathematics": 0.07, "Medicine": 0.08, "LegalSystem": 0.06, "PhilosophyHistory": 0.08, "FinanceEconomics": 0.06, "Physics": 0.10, "Cybersecurity": 0.06, "Bioinformatics": 0.06, "Geopolitics": 0.05, "DataScience": 0.08, "Chemistry": 0.07, "ArtHistory": 0.06, "Electronics": 0.04, "Astronomy": 0.06}
    }
}

from dissect_wikidata import WikidataStreamingExtractor


def validate_paths() -> bool:
    all_valid = True
    if not WIKIDATA_DUMP_PATH.exists():
        logger.critical(f"Wikidata dump not found: {WIKIDATA_DUMP_PATH}")
        all_valid = False
    else:
        logger.info(f"Wikidata dump found: {WIKIDATA_DUMP_PATH}")
    try:
        TARGET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ready: {TARGET_OUTPUT_DIR}")
    except Exception as e:
        logger.critical(f"Cannot create output directory {TARGET_OUTPUT_DIR}: {e}")
        all_valid = False
    return all_valid


def _domain_to_keywords(domain: str) -> str:
    """Convert CamelCase domain name to lowercase space-separated keywords."""
    words = re.sub(r'([A-Z])', r' \1', domain).strip().split()
    return ' '.join(w.lower() for w in words)


class PipelineController:
    def __init__(self, sample_size: Optional[int] = None, cycles_per_specialist: int = 3):
        self.db_manager = get_db_manager()
        self.llm_runner = LLMRunner()
        self.web_scraper = ModernWebScraper()
        self.metrics = MetricsCollector()
        self.ingestor = KnowledgeIngestor(
            packages_dir=Path('storage/packages'),
            reports_dir=Path('storage/reports'),
        )
        self._sample_size = sample_size
        self._cycles_per_specialist = cycles_per_specialist
        self._start_time = 0
        self._ensure_activity_table()

    def _ensure_activity_table(self):
        try:
            self.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT DEFAULT 'INFO',
                    message TEXT NOT NULL
                )
            """)
            self.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS cycle_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    specialist_id INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    quality REAL DEFAULT 0.0,
                    ema_before REAL,
                    ema_after REAL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                )
            """)
        except Exception as e:
            logger.debug(f"Activity table init: {e}")

    def _log_activity(self, message: str, level: str = 'INFO'):
        try:
            self.db_manager.execute_query(
                "INSERT INTO activity_log (level, message) VALUES (?, ?)",
                (level, message[:500])
            )
        except Exception as e:
            logger.warning(f"Failed to log activity: {e}")

    def _create_cascade_tables(self):
        self.db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS cascade_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_num INTEGER NOT NULL,
                entities_processed INTEGER NOT NULL,
                total_matches INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS qid_expansions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                specialist_id INTEGER NOT NULL,
                qid TEXT NOT NULL,
                discovered_at_checkpoint INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
                UNIQUE(specialist_id, qid)
            )
        """)
        self.db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS pipeline_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                current_specialist TEXT DEFAULT '',
                current_model TEXT DEFAULT '',
                current_cycle INTEGER DEFAULT 0,
                total_cycles INTEGER DEFAULT 0,
                phase TEXT DEFAULT '',
                status TEXT DEFAULT 'IDLE',
                elapsed_seconds REAL DEFAULT 0,
                cascade_entities INTEGER DEFAULT 0,
                cascade_max INTEGER DEFAULT 0,
                cascade_checkpoint INTEGER DEFAULT 0,
                start_epoch REAL DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


    def initialize_specialists(self) -> bool:
        try:
            if not self.db_manager.initialize_specialist_tables():
                logger.error("Failed to initialize specialist tables")
                return False
            self._create_cascade_tables()

            for specialist in SPECIALIST_REGISTRY:
                try:
                    self.db_manager.execute_query(
                        """INSERT OR IGNORE INTO specialist_registry 
                           (domain, model, root_qid, properties, ema_score, tier, status, parent_id, qid_path)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (specialist['domain'], specialist['model'], specialist['root'],
                         json.dumps(specialist['props']), 0.10, TIER_NONE, 'IDLE', None, None)
                    )
                    self.db_manager.execute_query(
                        """UPDATE specialist_registry 
                           SET model = ?, root_qid = ?, properties = ?
                           WHERE domain = ?""",
                        (specialist['model'], specialist['root'], json.dumps(specialist['props']), specialist['domain'])
                    )
                    logger.info(f"Initialized specialist: {specialist['domain']}")
                except Exception as e:
                    logger.error(f"Failed to insert specialist {specialist['domain']}: {e}")

            self.db_manager.execute_query("UPDATE specialist_registry SET status = 'IDLE'")
            logger.info("Specialist registry initialized (EMA preserved)")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize specialists: {e}")
            return False

    def get_specialists(self) -> List[Dict]:
        try:
            specialists = self.db_manager.execute_query(
                "SELECT id, domain, model, root_qid, properties, ema_score, status FROM specialist_registry ORDER BY ema_score ASC",
                fetch=True
            )
            return specialists if specialists else []
        except Exception as e:
            logger.error(f"Failed to fetch specialists: {e}")
            return []

    def _load_qid_expansions(self) -> Dict[str, Set[int]]:
        expansions: Dict[str, Set[int]] = {}
        try:
            rows = self.db_manager.execute_query(
                "SELECT specialist_id, qid FROM qid_expansions", fetch=True
            )
            if rows:
                for row in rows:
                    expansions.setdefault(row['qid'], set()).add(row['specialist_id'])
                logger.info(f"Loaded {len(rows)} QID expansions from previous runs")
        except Exception as e:
            logger.warning(f"Failed to load QID expansions: {e}")
        return expansions

    def handle_extraction_failure(self, specialist_id: int):
        try:
            self.db_manager.execute_query(
                "UPDATE cartridge_offsets SET status = 'FALLBACK_TRIGGERED' WHERE specialist_id = ?",
                (specialist_id,)
            )
        except Exception as e:
            logger.error(f"Failed to register fallback: {e}")

    def _update_pipeline_status(self, specialist='', model='', cycle=0, total_cycles=0,
                                 phase='', status='IDLE', cascade_entities=0,
                                 cascade_max=0, cascade_checkpoint=0):
        try:
            now = time.time()
            self.db_manager.execute_query(
                "INSERT INTO pipeline_status (id, status, start_epoch) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status",
                (status, now)
            )
            elapsed = now - self._start_time if self._start_time else 0
            self.db_manager.execute_query(
                """UPDATE pipeline_status SET
                   current_specialist=?, current_model=?, current_cycle=?, total_cycles=?,
                   phase=?, status=?, elapsed_seconds=?, start_epoch=?,
                   cascade_entities=?, cascade_max=?, cascade_checkpoint=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=1""",
                (specialist, model, cycle, total_cycles, phase, status, elapsed, self._start_time,
                 cascade_entities, cascade_max, cascade_checkpoint)
            )
        except Exception as e:
            logger.debug(f"Status update failed: {e}")

    def _compute_tier(self, specialist_id: int, ema: float, current_tier: int) -> int:
        try:
            row = self.db_manager.execute_query(
                "SELECT weighted_success, weighted_fail, packages_absorbed FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not row:
                return TIER_NONE
            ws = row[0].get('weighted_success', 0.0) or 0.0
            wf = row[0].get('weighted_fail', 0.0) or 0.0
            packages = row[0].get('packages_absorbed', 0) or 0

            ch = self.db_manager.execute_query(
                """SELECT COUNT(*) as total,
                          COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END), 0) as fails,
                          COALESCE(AVG(CASE WHEN success=1 THEN quality ELSE NULL END), 0) as avg_q
                   FROM cycle_history WHERE specialist_id = ?""",
                (specialist_id,), fetch=True
            )

            if ch and ch[0]['total'] > 0:
                total_cycles = ch[0]['total']
                failures = ch[0]['fails']
                avg_quality = ch[0]['avg_q'] or 0.0
            else:
                ema_count = self.db_manager.execute_query(
                    "SELECT COUNT(*) as cnt FROM ema_history WHERE specialist_id = ?",
                    (specialist_id,), fetch=True
                )
                total_cycles = ema_count[0]['cnt'] if ema_count else max(int(wf + ws), 1)
                failures = int(wf)
                successes = max(total_cycles - failures, 1)
                avg_quality = ws / successes

            fail_rate = failures / max(1, total_cycles)

            if current_tier == TIER_LEGEND:
                if ema >= LEGEND_EMA_MIN:
                    clean = self._clean_cycle_count(specialist_id)
                    if clean >= LEGEND_CYCLES_CLEAN:
                        return TIER_LEGEND
                return TIER_GOLD

            # Minimum real Phase B cycles required for tier promotion
            if ema >= TIER_CRITERIA[TIER_GOLD]["ema"] and avg_quality >= TIER_CRITERIA[TIER_GOLD]["quality"] and fail_rate < TIER_CRITERIA[TIER_GOLD]["fail_rate"] and packages >= TIER_CRITERIA[TIER_GOLD]["packages"] and total_cycles >= MIN_CYCLES_FOR_GOLD:
                return TIER_GOLD
            if ema >= TIER_CRITERIA[TIER_SILVER]["ema"] and avg_quality >= TIER_CRITERIA[TIER_SILVER]["quality"] and fail_rate < TIER_CRITERIA[TIER_SILVER]["fail_rate"] and packages >= TIER_CRITERIA[TIER_SILVER]["packages"] and total_cycles >= MIN_CYCLES_FOR_SILVER:
                return TIER_SILVER
            if ema >= TIER_CRITERIA[TIER_BRONZE]["ema"] and avg_quality >= TIER_CRITERIA[TIER_BRONZE]["quality"] and fail_rate < TIER_CRITERIA[TIER_BRONZE]["fail_rate"] and packages >= TIER_CRITERIA[TIER_BRONZE]["packages"] and total_cycles >= MIN_CYCLES_FOR_BRONZE:
                return TIER_BRONZE
            return TIER_NONE
        except Exception as e:
            logger.error(f"Tier computation failed for {specialist_id}: {e}")
            return TIER_NONE

    def _get_racha_25(self, specialist_id: int) -> float:
        try:
            rows = self.db_manager.execute_query(
                "SELECT success FROM cycle_history WHERE specialist_id = ? ORDER BY id DESC LIMIT 25",
                (specialist_id,), fetch=True
            )
            if not rows or len(rows) == 0:
                return 0.0
            successes = sum(1 for r in rows if r['success'])
            return successes / len(rows)
        except Exception as e:
            logger.debug(f"Racha 25 failed: {e}")
            return 0.0

    def _clean_cycle_count(self, specialist_id: int) -> int:
        try:
            rows = self.db_manager.execute_query(
                "SELECT success FROM cycle_history WHERE specialist_id = ? ORDER BY id DESC LIMIT ?",
                (specialist_id, LEGEND_CYCLES_CLEAN), fetch=True
            )
            if not rows:
                return 0
            count = 0
            for r in rows:
                if r['success']:
                    count += 1
                else:
                    break
            return count
        except Exception as e:
            logger.debug(f"Clean cycle count failed: {e}")
            return 0

    def update_ema_score(self, specialist_id: int, success: bool, content_length: int = 0,
                         trust_score: int = 50, contents_count: int = 0, packages_saved: int = 0,
                         is_feed: bool = False):
        try:
            result = self.db_manager.execute_query(
                "SELECT ema_score, weighted_success, weighted_fail, tier FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not result:
                return
            row = result[0]
            current_ema = row['ema_score']
            ws = row.get('weighted_success', 0.0) or 0.0
            wf = row.get('weighted_fail', 0.0) or 0.0
            current_tier = row.get('tier', TIER_NONE) or TIER_NONE

            if success:
                if content_length > 0 and contents_count > 0:
                    size_factor = 1.0 - math.exp(-content_length / 5000)
                    coverage_factor = min(contents_count / 10.0, 1.0)
                    trust_factor = trust_score / 100.0
                    efficiency = min(packages_saved / max(contents_count, 1), 1.0)
                    quality = 0.25 * size_factor + 0.25 * coverage_factor + 0.25 * trust_factor + 0.25 * efficiency
                else:
                    quality = 0.1
                # Feed updates: do NOT increment weighted_success (tier criteria)
                if not is_feed:
                    ws += quality
                alpha = 0.08
                new_ema = current_ema + alpha * quality * (1.0 - current_ema)
            else:
                quality = 0.0
                wf += 1.0
                penalty = FAILURE_PENALTIES.get(current_tier, 0.94)
                new_ema = current_ema * penalty

            self.db_manager.execute_query(
                "UPDATE specialist_registry SET ema_score=?, weighted_success=?, weighted_fail=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_ema, ws, wf, specialist_id)
            )
            self.db_manager.execute_query(
                "INSERT INTO ema_history (specialist_id, ema_score) VALUES (?, ?)",
                (specialist_id, new_ema)
            )
            self.db_manager.execute_query(
                "INSERT INTO cycle_history (specialist_id, success, quality, ema_before, ema_after) VALUES (?, ?, ?, ?, ?)",
                (specialist_id, 1 if success else 0, quality, current_ema, new_ema)
            )

            new_tier = self._compute_tier(specialist_id, new_ema, current_tier)
            if new_tier != current_tier:
                self.db_manager.execute_query(
                    "UPDATE specialist_registry SET tier = ? WHERE id = ?",
                    (new_tier, specialist_id)
                )
                tier_change = f" TIER: {TIER_NAMES[current_tier]} -> {TIER_NAMES[new_tier]}"
                if new_tier < current_tier:
                    logger.warning(f"TIER DOWN: specialist {specialist_id} {TIER_NAMES[current_tier]} -> {TIER_NAMES[new_tier]}")
            else:
                tier_change = ""

            if new_tier == TIER_LEGEND:
                display_ema = 100000
            else:
                display_ema = int(new_ema * 100000)
            racha = self._get_racha_25(specialist_id)
            logger.info(
                f"EMA {specialist_id}: {current_ema:.4f} -> {new_ema:.4f} "
                f"({display_ema:,}/100.000) [{TIER_NAMES[new_tier]}] "
                f"racha_25:{racha*100:.1f}% quality:{quality:.2f}{tier_change}"
            )

            drop_ratio = (new_ema - current_ema) / max(current_ema, 0.001)
            if drop_ratio < -0.10:
                logger.critical(f"EMA DROP >10%: specialist {specialist_id} {current_ema:.4f} -> {new_ema:.4f}")
        except Exception as e:
            logger.error(f"Failed to update EMA: {e}")

    def _batch_resolve_labels(self, qids: List[str]) -> Dict[str, str]:
        """Resolve English labels for a batch of QIDs via Wikidata API.
        Falls back to raw QID if API fails or label not found."""
        if not qids:
            return {}
        result = {}
        cached = getattr(self, '_label_cache', {})
        uncached = [q for q in qids if q not in cached]
        result.update({q: cached[q] for q in qids if q in cached})

        for i in range(0, len(uncached), WIKIDATA_LABEL_BATCH_SIZE):
            batch = uncached[i:i + WIKIDATA_LABEL_BATCH_SIZE]
            try:
                ids_str = '|'.join(batch)
                resp = requests.get(
                    WIKIDATA_ENTITY_API,
                    params={
                        'action': 'wbgetentities',
                        'ids': ids_str,
                        'props': 'labels',
                        'format': 'json',
                        'languages': 'en',
                    },
                    headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                if 'entities' in data:
                    for qid, entity in data['entities'].items():
                        label = entity.get('labels', {}).get('en', {}).get('value', qid)
                        cached[qid] = label
                        result[qid] = label
            except Exception as e:
                logger.warning(f"Label resolution failed for batch starting at {batch[0]}: {e}")
                for qid in batch:
                    if qid not in result:
                        result[qid] = qid
                        cached[qid] = qid

        if len(cached) > 100000:
            cached = {}
        self._label_cache = cached
        return result

    def _is_blocklisted_label(self, label: str) -> bool:
        """Check if a label matches the generic blocklist (meta-categories, etc.)."""
        label_lower = label.strip().lower()
        if label_lower in BLOCKLIST_LABELS:
            return True
        for prefix in BLOCKLIST_LABEL_PREFIXES:
            if label_lower.startswith(prefix):
                return True
        return False

    def _validate_qid_for_spawning(self, qids: List[str], root_qid: str) -> Set[str]:
        """Validate candidate QIDs by checking P279 parent-sharing with root.
        A QID is valid if its P279 includes the root QID (direct subclass)
        OR shares at least one P279 parent with the root QID (sibling subclass)."""
        if not qids:
            return set()
        try:
            # Shortcut: early return for small batches already cached
            cache = getattr(self, '_p279_cache', {})
            if len(cache) > 100000:
                cache = dict(list(cache.items())[-50000:])
            target_root_p279 = self._fetch_p279_parents(root_qid, cache)

            if not target_root_p279:
                # Root has no P279 parents — only direct children qualify
                all_qids = list(set(qids + [root_qid]))
                self._batch_fetch_p279(all_qids, cache)
                self._p279_cache = cache
                return {q for q in qids if root_qid in cache.get(q, set())}

            # Batch-fetch P279 for all candidates
            all_candidates = [q for q in qids if q not in cache]
            if all_candidates:
                self._batch_fetch_p279(all_candidates, cache)
            self._p279_cache = cache

            valid = set()
            for qid in qids:
                cand_p279 = cache.get(qid, set())
                if root_qid in cand_p279:
                    valid.add(qid)
                elif cand_p279 & target_root_p279:
                    valid.add(qid)
            return valid
        except Exception as e:
            logger.warning(f"P279 validation failed for {len(qids)} QIDs: {e}")
            return set()

    def _fetch_p279_parents(self, qid: str, cache: dict) -> Set[str]:
        """Fetch P279 (subclass of) parents for a QID, using cache."""
        if qid in cache:
            return cache[qid]
        try:
            resp = requests.get(
                WIKIDATA_ENTITY_API,
                params={'action': 'wbgetentities', 'ids': qid, 'props': 'claims', 'format': 'json'},
                headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            entity = data.get('entities', {}).get(qid, {})
            p279 = set()
            for claim in entity.get('claims', {}).get('P279', []):
                try:
                    p279.add(claim['mainsnak']['datavalue']['value']['id'])
                except (KeyError, TypeError):
                    pass
            cache[qid] = p279
            return p279
        except Exception as e:
            logger.warning(f"Failed to fetch P279 for {qid}: {e}")
            cache[qid] = set()
            return set()

    def _batch_fetch_p279(self, qids: List[str], cache: dict):
        """Batch-fetch P279 parents for multiple QIDs via single API call."""
        uncached = [q for q in qids if q not in cache]
        if not uncached:
            return
        for i in range(0, len(uncached), WIKIDATA_LABEL_BATCH_SIZE):
            batch = uncached[i:i + WIKIDATA_LABEL_BATCH_SIZE]
            try:
                ids_str = '|'.join(batch)
                resp = requests.get(
                    WIKIDATA_ENTITY_API,
                    params={'action': 'wbgetentities', 'ids': ids_str, 'props': 'claims', 'format': 'json'},
                    headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                for qid, entity in data.get('entities', {}).items():
                    if qid not in cache:
                        p279 = set()
                        for claim in entity.get('claims', {}).get('P279', []):
                            try:
                                p279.add(claim['mainsnak']['datavalue']['value']['id'])
                            except (KeyError, TypeError):
                                pass
                        cache[qid] = p279
            except Exception as e:
                logger.warning(f"Batch P279 fetch failed for batch: {e}")
                for qid in batch:
                    if qid not in cache:
                        cache[qid] = set()

    def _check_subspecialist_spawning(self, specialist_id: int):
        """Evaluate a single specialist for sub-specialist spawning with validation pipeline."""
        try:
            parent = self.db_manager.execute_query(
                "SELECT id, domain, model, root_qid, properties, packages_absorbed FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not parent:
                return
            parent = parent[0]

            total_children = self.db_manager.execute_query(
                "SELECT COUNT(*) as cnt FROM specialist_registry WHERE parent_id IS NOT NULL", fetch=True
            )
            current_children = total_children[0]['cnt'] if total_children else 0
            if current_children >= MAX_SUBSPECIALISTS:
                return

            children_count = self.db_manager.execute_query(
                "SELECT COUNT(*) as cnt FROM specialist_registry WHERE parent_id = ?",
                (parent['id'],), fetch=True
            )
            existing_children = children_count[0]['cnt'] if children_count else 0
            if existing_children >= MAX_CHILDREN_PER_PARENT:
                return

            expansions = self.db_manager.execute_query(
                "SELECT qid FROM qid_expansions WHERE specialist_id = ? ORDER BY discovered_at_checkpoint ASC",
                (parent['id'],), fetch=True
            )
            if not expansions or len(expansions) < 3:
                return
            if parent['packages_absorbed'] < SUBSPECIALIST_THRESHOLD:
                return

            root_qid = parent['root_qid']

            # Filter candidates: pre-existing children first
            unspawned = []
            for exp in expansions:
                qid = exp['qid']
                existing = self.db_manager.execute_query(
                    "SELECT id FROM specialist_registry WHERE root_qid = ? AND parent_id = ?",
                    (qid, parent['id']), fetch=True
                )
                if not existing:
                    unspawned.append(qid)
            if not unspawned:
                return

            # Resolve labels for remaining candidates (cached internally)
            labels = self._batch_resolve_labels(unspawned)

            # Validate via P279 parent-sharing with root QID
            valid_qids = self._validate_qid_for_spawning(unspawned, root_qid)

            spawned_this_cycle = 0
            for qid in unspawned:
                if spawned_this_cycle >= MAX_CHILDREN_PER_PARENT:
                    break
                if current_children + spawned_this_cycle >= MAX_SUBSPECIALISTS:
                    break

                label = labels.get(qid, qid)

                # 1. Blocklist heuristic check
                if self._is_blocklisted_label(label):
                    logger.info(f"BLOCKED (blocklist label): {qid} -> '{label}' for {parent['domain']}")
                    self._log_activity(f"Bloqueado {parent['domain']}/{label} (QID {qid}) — etiqueta genérica", 'WARNING')
                    continue

                # 2. P279 parent-sharing validation
                if qid not in valid_qids:
                    branch_label = f"{parent['domain']}/{label}"
                    logger.info(f"BLOCKED (P279): {qid} -> '{label}' not a subclass of {root_qid}")
                    self._log_activity(f"Rama externa {branch_label} (QID {qid}) — no emparenta con {parent['domain']}", 'WARNING')
                    continue

                # 3. Passes all checks — spawn
                child_domain = f"{parent['domain']}/{label}"
                parent_path = parent.get('qid_path') or parent['domain']
                child_path = f"{parent_path}/{label}"

                self.db_manager.execute_query(
                    """INSERT INTO specialist_registry 
                       (domain, model, root_qid, properties, ema_score, tier, status, parent_id, qid_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (child_domain, parent['model'], qid, parent['properties'], 0.10, TIER_NONE, 'IDLE', parent['id'], child_path)
                )
                spawned_this_cycle += 1
                logger.info(f"SPAWNED sub-specialist: {child_domain} (QID: {qid}, parent: {parent['domain']})")
                self._log_activity(f"Germinado {child_domain} de {parent['domain']} (QID {qid})")

        except Exception as e:
            logger.error(f"Subspecialist spawning check failed for specialist {specialist_id}: {e}")

    def _check_subspecialist_expansion(self, specialist_id: int):
        """Check if a specialist has unspawned QID expansions and create sub-specialists."""
        try:
            parent = self.db_manager.execute_query(
                "SELECT id, domain, model, root_qid, packages_absorbed FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not parent:
                return
            parent = parent[0]

            total_children = self.db_manager.execute_query(
                "SELECT COUNT(*) as cnt FROM specialist_registry WHERE parent_id IS NOT NULL", fetch=True
            )
            current_children = total_children[0]['cnt'] if total_children else 0
            if current_children >= MAX_SUBSPECIALISTS:
                return

            children_count = self.db_manager.execute_query(
                "SELECT COUNT(*) as cnt FROM specialist_registry WHERE parent_id = ?",
                (parent['id'],), fetch=True
            )
            existing_children = children_count[0]['cnt'] if children_count else 0
            if existing_children >= MAX_CHILDREN_PER_PARENT:
                return

            if parent['packages_absorbed'] < SUBSPECIALIST_THRESHOLD:
                return

            expansions = self.db_manager.execute_query(
                "SELECT qid FROM qid_expansions WHERE specialist_id = ? ORDER BY discovered_at_checkpoint ASC",
                (parent['id'],), fetch=True
            )
            if not expansions or len(expansions) < 3:
                return

            root_qid = parent['root_qid']
            unspawned = []
            for exp in expansions:
                qid = exp['qid']
                existing = self.db_manager.execute_query(
                    "SELECT id FROM specialist_registry WHERE root_qid = ? AND parent_id = ?",
                    (qid, parent['id']), fetch=True
                )
                if not existing:
                    unspawned.append(qid)
            if not unspawned:
                return

            labels = self._batch_resolve_labels(unspawned)
            valid_qids = self._validate_qid_for_spawning(unspawned, root_qid)

            spawned = 0
            for qid in unspawned:
                if spawned >= MAX_CHILDREN_PER_PARENT:
                    break
                if current_children + spawned >= MAX_SUBSPECIALISTS:
                    break

                label = labels.get(qid, qid)
                if self._is_blocklisted_label(label):
                    continue
                if qid not in valid_qids:
                    continue

                child_domain = f"{parent['domain']}/{label}"
                parent_path = parent.get('qid_path') or parent['domain']
                child_path = f"{parent_path}/{label}"

                self.db_manager.execute_query(
                    """INSERT INTO specialist_registry
                       (domain, model, root_qid, properties, ema_score, tier, status, parent_id, qid_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (child_domain, parent['model'], qid, '{}', 0.10, TIER_NONE, 'IDLE', parent['id'], child_path)
                )
                spawned += 1
                logger.info(f"EXPANDED sub-specialist: {child_domain} (QID: {qid}, parent: {parent['domain']})")
                self._log_activity(f"Expandido {child_domain} de {parent['domain']} (QID {qid})")

            if spawned > 0:
                logger.info(f"Expanded {spawned} sub-specialists for {parent['domain']}")

        except Exception as e:
            logger.error(f"Sub-specialist expansion failed for {specialist_id}: {e}")

    # ── Super-Expert Methods ──────────────────────────────────────────────────

    def _create_super_expert_tables(self):
        self.db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS super_experts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS super_expert_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                super_expert_id INTEGER NOT NULL,
                specialist_id INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 0.1,
                FOREIGN KEY (super_expert_id) REFERENCES super_experts(id),
                FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
                UNIQUE(super_expert_id, specialist_id)
            )
        """)
        logger.info("Super-expert tables ready")

    def initialize_super_experts(self):
        """Seed super_experts and super_expert_members from SUPER_EXPERTS config."""
        self._create_super_expert_tables()
        # Build a domain->id lookup for specialist_registry
        specialists = self.db_manager.execute_query(
            "SELECT id, domain FROM specialist_registry WHERE parent_id IS NULL", fetch=True
        ) or []
        domain_to_id = {s['domain']: s['id'] for s in specialists}

        for se_domain, se_config in SUPER_EXPERTS.items():
            try:
                existing = self.db_manager.execute_query(
                    "SELECT id FROM super_experts WHERE domain = ?", (se_domain,), fetch=True
                )
                if existing and existing[0]['id']:
                    se_id = existing[0]['id']
                else:
                    self.db_manager.execute_query(
                        "INSERT INTO super_experts (domain, description) VALUES (?, ?)",
                        (se_domain, se_config['description'])
                    )
                    se_id = self.db_manager.execute_query(
                        "SELECT last_insert_rowid()", fetch=True
                    )[0]['last_insert_rowid()']

                # Remove stale members, insert current
                self.db_manager.execute_query(
                    "DELETE FROM super_expert_members WHERE super_expert_id = ?", (se_id,)
                )
                for spec_domain, weight in se_config['members'].items():
                    sid = domain_to_id.get(spec_domain)
                    if sid is None:
                        logger.warning(f"Super-expert {se_domain}: specialist {spec_domain} not found in DB")
                        continue
                    self.db_manager.execute_query(
                        "INSERT OR IGNORE INTO super_expert_members (super_expert_id, specialist_id, weight) VALUES (?, ?, ?)",
                        (se_id, sid, weight)
                    )
                logger.info(f"Super-expert '{se_domain}' initialized with {len(se_config['members'])} members")
            except Exception as e:
                logger.error(f"Failed to initialize super-expert '{se_domain}': {e}")

    def get_super_expert_members(self, se_domain: str) -> List[Dict]:
        """Return members of a super-expert with current EMA and packages."""
        try:
            rows = self.db_manager.execute_query("""
                SELECT se.domain AS se_domain, se.description,
                       s.id, s.domain, s.ema_score, s.packages_absorbed, sem.weight
                FROM super_experts se
                JOIN super_expert_members sem ON sem.super_expert_id = se.id
                JOIN specialist_registry s ON s.id = sem.specialist_id
                WHERE se.domain = ?
                ORDER BY sem.weight DESC
            """, (se_domain,), fetch=True)
            return rows if rows else []
        except Exception as e:
            logger.error(f"Failed to get super-expert {se_domain}: {e}")
            return []

    def get_all_super_experts(self) -> List[Dict]:
        """Return all super-experts with aggregated info."""
        try:
            rows = self.db_manager.execute_query("""
                SELECT se.id, se.domain, se.description,
                       COUNT(sem.id) AS member_count,
                       AVG(s.ema_score) AS avg_ema,
                       SUM(s.packages_absorbed * sem.weight) / SUM(sem.weight) AS weighted_ema,
                       SUM(s.packages_absorbed) AS total_packages
                FROM super_experts se
                LEFT JOIN super_expert_members sem ON sem.super_expert_id = se.id
                LEFT JOIN specialist_registry s ON s.id = sem.specialist_id
                GROUP BY se.id
                ORDER BY se.domain
            """, fetch=True)
            return rows if rows else []
        except Exception as e:
            logger.error(f"Failed to get all super-experts: {e}")
            return []

    def query_super_expert(self, se_domain: str, question: str, top_k: int = 5) -> List[Dict]:
        """Synthesize knowledge from member specialists weighted by relevance.
        Returns ranked knowledge packages."""
        members = self.get_super_expert_members(se_domain)
        if not members:
            return []

        # Extract keywords from question for relevance scoring
        question_lower = question.lower()
        keywords = [w for w in re.split(r'\W+', question_lower) if len(w) > 3]

        results = []
        for m in members:
            try:
                pkgs = self.db_manager.execute_query("""
                    SELECT topic, structured_knowledge, source_url, created_at
                    FROM knowledge_packages
                    WHERE domain = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (m['domain'], top_k * 2), fetch=True) or []
                for pkg in pkgs:
                    # Keyword relevance scoring
                    text = (pkg.get('topic', '') + ' ' + pkg.get('structured_knowledge', '')).lower()
                    relevance = sum(1 for kw in keywords if kw in text) / max(len(keywords), 1)
                    results.append({
                        'specialist': m['domain'],
                        'weight': m['weight'],
                        'ema': m['ema_score'],
                        'relevance': relevance,
                        'topic': pkg['topic'],
                        'knowledge': pkg['structured_knowledge'],
                        'source': pkg['source_url'],
                        'timestamp': pkg['created_at'],
                    })
            except Exception as e:
                logger.debug(f"Query super-expert member {m['domain']}: {e}")

        # Sort by relevance * weight * EMA
        results.sort(key=lambda r: (r['relevance'] * r['weight'] * r['ema']), reverse=True)
        return results[:top_k]

    @staticmethod
    def _make_schema_matcher(schema: Dict) -> Callable[[Dict], bool]:
        root_qid = schema['root']
        def matches_schema(entity: Dict) -> bool:
            for prop in ('P31', 'P279'):
                for claim in entity.get('claims', {}).get(prop, []):
                    try:
                        if claim['mainsnak']['datavalue']['value']['id'] == root_qid:
                            return True
                    except (KeyError, TypeError):
                        continue
            return False
        return matches_schema

    async def run_phase_a_cascade(self, specialists: List[Dict], max_entities: int = MAX_CASCADE_ENTITIES) -> Dict[int, bool]:
        """Cascade Phase A: scan dump once with progressive checkpoints and QID expansion."""
        results = {s['id']: False for s in specialists}
        specialist_matchers = {}

        for s in specialists:
            sid, domain = s['id'], s['domain']
            schema = WIKIDATA_SCHEMAS.get(domain)
            if not schema:
                logger.warning(f"No schema for {domain}")
                continue
            specialist_matchers[sid] = {'domain': domain, 'root_qid': schema['root']}
            results[sid] = False
            try:
                existing_cart = self.db_manager.execute_query(
                    "SELECT status FROM cartridge_offsets WHERE specialist_id = ?", (sid,), fetch=True
                )
                if not existing_cart or existing_cart[0]['status'] != 'COMPLETED':
                    self.db_manager.execute_query(
                        """INSERT OR REPLACE INTO cartridge_offsets (qid, cartridge_name, specialist_id, status)
                           VALUES (?, ?, ?, ?)""",
                        (f"specialist_{sid}", f"cartridge_{domain}.json.gz", sid, "PROCESSING: 0%")
                    )
            except Exception as e:
                logger.error(f"Failed to init cartridge for {domain}: {e}")

        if not specialist_matchers:
            logger.error("No valid specialists")
            return results

        loaded_expansions = self._load_qid_expansions()
        logger.info(f"Loaded {sum(len(v) for v in loaded_expansions.values())} QID expansions from DB")

        self._update_pipeline_status(
            phase=f'Phase A: Cascade (0/{max_entities:,})',
            status='ACTIVE', cascade_entities=0, cascade_max=max_entities
        )

        def checkpoint_callback(cp_num, entities_processed, matches_per_specialist,
                                 expansions_per_specialist, elapsed):
            try:
                total_matches = sum(matches_per_specialist.values())
                self.db_manager.execute_query(
                    """INSERT INTO cascade_checkpoints (checkpoint_num, entities_processed, total_matches, elapsed_seconds)
                       VALUES (?, ?, ?, ?)""",
                    (cp_num, entities_processed, total_matches, elapsed)
                )
                # Save QID expansions
                for sid, qids in expansions_per_specialist.items():
                    for qid in qids:
                        try:
                            self.db_manager.execute_query(
                                "INSERT OR IGNORE INTO qid_expansions (specialist_id, qid, discovered_at_checkpoint) VALUES (?, ?, ?)",
                                (sid, qid, cp_num)
                            )
                        except Exception as e:
                            logger.warning(f"Failed to save QID expansion: {e}")
                logger.info(f"=== CHECKPOINT {cp_num}: {entities_processed:,} entities, {total_matches} matches ===")
                self._update_pipeline_status(
                    phase=f'Phase A: Cascade (cp {cp_num})',
                    cascade_entities=entities_processed, cascade_max=max_entities,
                    cascade_checkpoint=cp_num
                )
            except Exception as e:
                logger.error(f"Checkpoint callback failed: {e}")

        def progress_callback(entities_processed, elapsed, rate):
            try:
                self._update_pipeline_status(
                    phase=f'Phase A: {entities_processed:,} ent ({rate:.0f}/s)',
                    cascade_entities=entities_processed, cascade_max=max_entities,
                )
            except Exception:
                pass

        hierarchy_cache = ClassHierarchyCache(
            {sid: info['root_qid'] for sid, info in specialist_matchers.items()}
        )
        extractor = BatchWikidataExtractor(
            input_path=WIKIDATA_DUMP_PATH,
            output_dir=TARGET_OUTPUT_DIR,
            specialist_matchers=specialist_matchers,
            checkpoint_callback=checkpoint_callback,
            progress_callback=progress_callback,
            hierarchy_cache=hierarchy_cache,
        )

        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE A: CASCADE — scanning up to {max_entities:,} entities")
        logger.info(f"Checkpoints every {CHECKPOINT_INTERVAL:,}, QID expansion active")
        logger.info(f"{'='*80}\n")

        success = extractor.extract_with_timeout(
            timeout_hours=WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
            sample_size=max_entities,
            loaded_expansions=loaded_expansions,
        )

        for sid, info in specialist_matchers.items():
            results[sid] = success
            matched = extractor.matched_counts.get(sid, 0)
            self.metrics.record_phase_a(
                specialist_id=sid, domain=info['domain'], success=success,
                entities_processed=extractor.entities_processed, entities_matched=matched
            )
            if success:
                self.db_manager.execute_query(
                    "UPDATE cartridge_offsets SET status='COMPLETED' WHERE specialist_id=?", (sid,)
                )

        if not success:
            for sid in specialist_matchers:
                self.handle_extraction_failure(sid)

        return results

    async def run_phase_b(self, specialist: Dict, cycle: int = 1) -> Dict:
        sid, domain, model = specialist['id'], specialist['domain'], specialist['model']
        result = {'success': False, 'contents_count': 0, 'total_length': 0, 'avg_trust': 50.0, 'packages_saved': 0}

        self._log_activity(f"Iniciando {domain} (ciclo {cycle}) con {model}")

        # Vary queries per cycle for diverse knowledge
        keywords = _domain_to_keywords(domain)
        cycle_queries = {
            1: [f"{keywords} latest research 2026", f"{keywords} best practices",
                f"{keywords} state of the art", f"{keywords} key concepts",
                f"{keywords} fundamentals explained", f"{keywords} modern approaches",
                f"{keywords} essential knowledge", f"{keywords} introduction"],
            2: [f"{keywords} current trends", f"{keywords} challenges and solutions",
                f"{keywords} future directions", f"{keywords} innovations",
                f"{keywords} cutting edge research", f"{keywords} expert insights",
                f"{keywords} case studies", f"{keywords} overview"],
            3: [f"{keywords} tools and frameworks", f"{keywords} implementations",
                f"{keywords} best tools 2026", f"{keywords} comparison",
                f"{keywords} practical guide", f"{keywords} tutorial",
                f"{keywords} advanced concepts", f"{keywords} deep dive"],
        }
        queries = cycle_queries.get(cycle, cycle_queries[1])

        try:
            self._log_activity(f"Cargando modelo {model} para {domain}")
            model_loaded = await self.llm_runner.ensure_model_loaded(model)
            if not model_loaded:
                logger.error(f"Failed to load model: {model}")
                self._log_activity(f"ERROR: modelo {model} no disponible", 'ERROR')
                return result

            self._log_activity(f"Modelo {model} listo — iniciando {domain}")
            self.db_manager.execute_query("UPDATE specialist_registry SET status='ACTIVE' WHERE id=?", (sid,))

            total_c, total_l, trusts, pkgs_saved = 0, 0, [], 0

            for query in queries:
                self._log_activity(f"{domain} > Buscando: \"{query[:60]}\"")
                try:
                    results = await asyncio.wait_for(
                        self.web_scraper.search_and_extract(query=query, max_results=5, domain=domain),
                        timeout=120,
                    )
                    total_c += len(results)
                    self._log_activity(f"{domain} > {len(results)} resultados para \"{query[:40]}\"")
                    for content in results:
                        ct = content.get('content', '')
                        if not ct or len(ct.strip()) < 200:
                            continue
                        # Reject garbage content before distilling
                        ct_lower = ct.lower()
                        if any(p in ct_lower for p in ['cookie', 'sign in', 'javascript is disabled', 'captcha', 'loading spinner']):
                            continue
                        total_l += estimate_tokens(ct)
                        trust = content.get('trust_score', 50)
                        trusts.append(trust)
                        url = content.get('url', '') or content.get('source', '')
                        self._log_activity(f"{domain} > Destilando: {url[:60]}...")
                        system_ctx = self.ingestor.get_system_context(domain=domain, max_chars=2000)
                        try:
                            if system_ctx:
                                prompt = f"{system_ctx}\n\nSummarize the following {domain} knowledge in 3 bullet points:\n\n{ct[:2000]}"
                            else:
                                prompt = f"Summarize the following {domain} knowledge in 3 bullet points:\n\n{ct[:2000]}"
                            dist = await asyncio.wait_for(self.llm_runner.query_llm(model_name=model, prompt=prompt), timeout=LLM_QUERY_TIMEOUT)
                            logger.debug(f"Distill: {dist[:100]}...")
                        except Exception as e:
                            logger.warning(f"Distill failed for {url[:60]}: {e}")
                            continue
                        if not domain:
                            continue
                        # Quality gate: reject empty or too short distillations
                        if not dist or len(dist.strip()) < 10:
                            logger.debug(f"Distill too short ({len(dist or '')} chars), skipping")
                            continue
                        # Save knowledge package (DB + file)
                        if dist and url:
                            try:
                                self.db_manager.execute_query(
                                    """INSERT INTO knowledge_packages (topic, source_url, domain, qid, structured_knowledge)
                                       VALUES (?, ?, ?, ?, ?)""",
                                    (query[:100], url, domain, None, dist[:500])
                                )
                                pkgs_saved += 1
                                self._log_activity(f"{domain} > Package guardado: {query[:40]}")
                                # Save as .md file for KnowledgeIngestor
                                pkg_dir = Path('storage/packages') / domain
                                pkg_dir.mkdir(parents=True, exist_ok=True)
                                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                                slug = ''.join(c if c.isalnum() or c in ' _-' else '' for c in query[:40]).strip()
                                pkg_path = pkg_dir / f'{ts}_{slug}.md'
                                pkg_path.write_text(
                                    f"# {domain}: {query[:80]}\n\n"
                                    f"**Source:** {url}\n\n"
                                    f"**Distilled:**\n{dist[:1000]}\n",
                                    encoding='utf-8'
                                )
                            except Exception as e:
                                logger.debug(f"Failed to save package: {e}")
                except (RateLimitError, WebScraperError) as e:
                    logger.warning(f"Search failed '{query}': {e}")

            # Update packages_absorbed count
            if pkgs_saved > 0:
                self.db_manager.execute_query(
                    "UPDATE specialist_registry SET packages_absorbed = packages_absorbed + ? WHERE id = ?",
                    (pkgs_saved, sid)
                )

            self.metrics.record_phase_b(specialist_id=sid, domain=domain, success=total_c > 0, contents_count=total_c)
            avg_t = sum(trusts) / len(trusts) if trusts else 50.0
            logger.info(f"Phase B complete for {domain} (cycle {cycle}): {total_c} contents, {pkgs_saved} packages")
            self._log_activity(f"{domain} completado — {pkgs_saved} paquetes en ciclo {cycle}")
            result.update(success=total_c > 0, contents_count=total_c, total_length=total_l, avg_trust=avg_t, packages_saved=pkgs_saved)
            return result
        except Exception as e:
            logger.error(f"Phase B failed for {domain}: {e}")
            return result
        finally:
            self.db_manager.execute_query("UPDATE specialist_registry SET status='IDLE' WHERE id=?", (sid,))

    async def _generate_report(self, elapsed_seconds: float):
        """Generate EMA evolution report with chart, saved to storage/reports/."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        report_dir = Path('storage/reports')
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        specialists = self.db_manager.execute_query(
            "SELECT id, domain, model, ema_score, packages_absorbed, tier FROM specialist_registry ORDER BY ema_score DESC",
            fetch=True
        ) or []

        history = self.db_manager.execute_query(
            "SELECT specialist_id, ema_score, timestamp FROM ema_history ORDER BY id",
            fetch=True
        ) or []

        # Build time-aligned series per specialist
        from collections import defaultdict
        series_raw = defaultdict(list)
        time_labels = []
        for row in history:
            sid = row['specialist_id']
            t = row['timestamp'][:16] if row['timestamp'] else ''
            series_raw[sid].append((t, row['ema_score']))
        for sid, pts in series_raw.items():
            time_labels = [p[0] for p in pts]

        # Chart: combined EMA evolution (×100.000 scale)
        plt.figure(figsize=(14, 8))
        colors = plt.cm.tab20.colors + plt.cm.tab20b.colors
        for i, s in enumerate(specialists):
            sid = s['id']
            pts = series_raw.get(sid, [])
            if len(pts) < 2:
                continue
            times = [p[0] for p in pts]
            vals = [p[1] * 100000 for p in pts]
            tier_val = s['tier'] or TIER_NONE
            display_pts = "100.000" if tier_val == TIER_LEGEND else f"{int(s['ema_score']*100000):,}"
            label = f"{s['domain']} ({display_pts}) [{TIER_NAMES.get(tier_val, '?')}]"
            plt.plot(range(len(vals)), vals, color=colors[i % len(colors)],
                     marker='o', markersize=3, linewidth=1.2, label=label)

        plt.title(f'Puntuación EMA — {ts}', fontsize=14)
        plt.xlabel('Ciclo #')
        plt.ylabel('Puntuación /100.000')
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=7)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        chart_path = report_dir / f'ema_evolution_{ts}.png'
        plt.savefig(chart_path, dpi=150)
        plt.close()

        # Markdown report
        lines = [f"# Pipeline Report — {ts}\n"]
        lines.append(f"**Elapsed:** {elapsed_seconds/3600:.2f}h ({elapsed_seconds/60:.1f} min)\n")
        lines.append(f"**Total history records:** {len(history)}\n")
        lines.append(f"\n## Puntuaciones\n")
        lines.append(f"| # | Domain | Model | Puntuación | Tier | Racha 25 | Paquetes |")
        lines.append(f"|---|--------|-------|------------|------|----------|----------|")
        for i, s in enumerate(specialists, 1):
            sid = s['id']
            tier_val = s['tier'] or TIER_NONE
            if tier_val == TIER_LEGEND:
                pts_str = "100.000"
            else:
                pts_str = f"{int(s['ema_score'] * 100000):,}/100.000"
            racha = self._get_racha_25(sid)
            tier_name = TIER_NAMES.get(tier_val, 'None')
            racha_str = f"{racha*100:.1f}%" if racha > 0 else "-"
            lines.append(f"| {i} | {s['domain']} | {s['model']} | {pts_str} | {tier_name} | {racha_str} | {s['packages_absorbed']} |")

        lines.append(f"\n## Charts\n")
        lines.append(f"![EMA Evolution](ema_evolution_{ts}.png)\n")

        report_path = report_dir / f'report_{ts}.md'
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        logger.info(f"Report saved: {report_path}")

    def _compute_nurture_priority(self, specialist: dict) -> float:
        """Compute nurture priority score for a specialist. Higher = more urgent."""
        ema = specialist.get('ema_score', 0.5)
        packages = specialist.get('packages_absorbed', 0)
        updated_at = specialist.get('updated_at', '')
        weighted_success = specialist.get('weighted_success', 0.0)
        weighted_fail = specialist.get('weighted_fail', 0.0)

        total_ws_wf = weighted_success + weighted_fail
        fail_rate = weighted_fail / total_ws_wf if total_ws_wf > 0 else 0.0

        staleness_days = 0.0
        if updated_at:
            try:
                from datetime import datetime
                last_update = datetime.strptime(str(updated_at), '%Y-%m-%d %H:%M:%S')
                staleness_days = (datetime.now() - last_update).total_seconds() / 86400
            except (ValueError, TypeError):
                staleness_days = 7.0

        score = (
            (1.0 - ema) * NURTURE_W_EMA
            + fail_rate * NURTURE_W_FAIL
            + staleness_days * NURTURE_W_STALENESS
            + max(0, 1.0 - packages / NURTURE_PACKAGE_TARGET) * NURTURE_W_PACKAGES
        )
        return round(score, 4)

    async def _run_nurture_mode(self, all_specialists: list, pipeline_start: float,
                                 min_duration_hours: float, max_duration_hours: float,
                                 max_cycles: int, report_interval_minutes: int):
        logger.info("=" * 80)
        logger.info("NURTURE MODE — Maintenance + Growth (priority scoring, continuous recycling, sub-specialist expansion)")
        logger.info("=" * 80)

        global_cycle = 0
        last_report_time = 0.0

        while True:
            if _shutdown_event.is_set():
                logger.info("Shutdown signal received. Stopping nurture.")
                break

            elapsed = time.time() - pipeline_start
            if elapsed >= min_duration_hours * 3600:
                logger.info(f"Minimum duration reached ({min_duration_hours}h). Finishing nurture...")
                break

            if max_cycles > 0 and global_cycle >= max_cycles:
                logger.info(f"Max cycles reached ({max_cycles}). Stopping nurture.")
                break

            if max_duration_hours > 0 and elapsed >= max_duration_hours * 3600:
                logger.info(f"Hard max duration reached ({max_duration_hours}h). Stopping nurture.")
                break

            # ── Pillar 1: Score ALL parent specialists by priority ──
            parents = self.db_manager.execute_query(
                "SELECT id, domain, model, ema_score, weighted_success, weighted_fail, "
                "packages_absorbed, updated_at FROM specialist_registry "
                "WHERE parent_id IS NULL ORDER BY domain",
                fetch=True
            )
            if not parents:
                logger.info("No specialists found — nurture complete!")
                break

            scored = []
            for p in parents:
                score = self._compute_nurture_priority(p)
                scored.append((score, p))
            scored.sort(key=lambda x: x[0], reverse=True)

            top_score, target_spec = scored[0]
            sid = target_spec['id']
            domain = target_spec['domain']
            model = target_spec['model']
            current_ema = target_spec.get('ema_score', 0.0)

            # ── Pillar 3: Check sub-specialist expansion before processing ──
            self._check_subspecialist_expansion(sid)

            global_cycle += 1
            effective_cycle = ((global_cycle - 1) % 3) + 1

            self._update_pipeline_status(
                specialist=domain, model=model, cycle=global_cycle, total_cycles=999,
                phase=f'Nurture: {domain} (score={top_score:.2f}, EMA={current_ema:.4f})', status='ACTIVE'
            )
            logger.info(f"Nurture cycle {global_cycle}: {domain} (priority={top_score:.2f}, EMA={current_ema:.4f}, model={model})")

            spec_row = self.db_manager.execute_query(
                "SELECT * FROM specialist_registry WHERE id=?", (sid,), fetch=True
            )
            if not spec_row:
                continue
            specialist = spec_row[0]

            model_ready = await self.llm_runner.ensure_model_ready(model)
            if not model_ready:
                logger.error(f"Model {model} unavailable for {domain} — skipping")
                await asyncio.sleep(30)
                continue

            # ── Pillar 2: Execute Phase B (continuous recycling) ──
            try:
                phase_b = await asyncio.wait_for(
                    self.run_phase_b(specialist, effective_cycle),
                    timeout=NURTURE_CYCLE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning(f"Nurture cycle timed out for {domain} — retrying without penalty")
                continue
            except Exception as e:
                logger.error(f"Nurture cycle failed for {domain}: {e}")
                self.update_ema_score(sid, False)
                continue

            ok = phase_b.get('success', False)
            self.update_ema_score(
                sid, ok,
                phase_b.get('total_length', 0),
                phase_b.get('avg_trust', 50),
                phase_b.get('contents_count', 0),
                phase_b.get('packages_saved', 0),
            )

            after = self.db_manager.execute_query(
                "SELECT ema_score FROM specialist_registry WHERE id=?", (sid,), fetch=True
            )
            new_ema = after[0]['ema_score'] if after else current_ema
            logger.info(f"Nurture progress: {domain} EMA {current_ema:.4f} → {new_ema:.4f}")

            new_elapsed = time.time() - pipeline_start
            if new_elapsed - last_report_time >= report_interval_minutes * 60:
                await self._generate_report(new_elapsed)
                last_report_time = new_elapsed

    async def _run_wikidata_feed(self, all_specialists: list):
        logger.info("=" * 80)
        logger.info("WIKIDATA FEED MODE — absorbing pending Wikidata packages")
        logger.info("=" * 80)

        total_absorbed = 0
        for specialist in all_specialists:
            sid = specialist['id']
            domain = specialist['domain']

            pending = self.db_manager.execute_query(
                """SELECT COUNT(*) AS cnt
                   FROM knowledge_packages
                   WHERE domain = ? AND qid IS NOT NULL AND absorbed_at IS NULL""",
                (domain,), fetch=True
            )
            cnt = pending[0]['cnt'] if pending else 0
            if cnt == 0:
                logger.info(f"[Feed] {domain}: no pending packages")
                continue

            try:
                self.db_manager.execute_query(
                    """UPDATE knowledge_packages
                       SET absorbed_at = CURRENT_TIMESTAMP
                       WHERE domain = ? AND qid IS NOT NULL AND absorbed_at IS NULL""",
                    (domain,)
                )

                self.db_manager.execute_query(
                    """UPDATE specialist_registry
                       SET feed_packages = feed_packages + ?,
                           last_wikidata_feed = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (cnt, sid)
                )

                # Feed mode: update EMA but do NOT count toward weighted_success (tier criteria)
                effective_cnt = max(cnt, 10)
                self.update_ema_score(
                    specialist_id=sid, success=True,
                    content_length=10000, trust_score=95,
                    contents_count=effective_cnt, packages_saved=effective_cnt,
                    is_feed=True,
                )

                total_absorbed += cnt
                logger.info(f"[Feed] {domain}: absorbed {cnt} packages, EMA updated")
            except Exception as e:
                logger.error(f"[Feed] {domain}: error {e}")

        logger.info(f"Feed complete: {total_absorbed} packages absorbed")
        if total_absorbed == 0:
            logger.info("No pending packages — nothing to do")

    async def run_pipeline(self, sample_size: Optional[int] = None,
                           min_duration_hours: float = 5.0,
                           report_interval_minutes: int = 30,
                           phase: str = 'full',
                           specialist_filter: str = 'all',
                           model_filter: str = 'all',
                           max_duration_hours: float = 0,
                           max_cycles: int = 0) -> None:
        logger.info("=" * 80)
        logger.info("CORAL THOUGHT ORCHESTRATOR - PIPELINE")
        logger.info(f"Phase: {phase} | Specialist: {specialist_filter} | Model: {model_filter}")
        logger.info(f"Min duration: {min_duration_hours}h | Report every {report_interval_minutes}min")
        if max_duration_hours > 0:
            logger.info(f"Hard max duration: {max_duration_hours}h")
        if max_cycles > 0:
            logger.info(f"Max Phase B cycles: {max_cycles}")
        logger.info("=" * 80 + "\n")

        self._start_time = time.time()
        self._update_pipeline_status(status='INIT', phase='Initializing...')

        # Snapshot EMA before pipeline to detect massive drops
        ema_rows = self.db_manager.execute_query(
            "SELECT id, ema_score FROM specialist_registry", fetch=True
        ) or []
        self._ema_snapshot = {r['id']: r['ema_score'] for r in ema_rows}

        if not validate_paths():
            self._update_pipeline_status(status='ERROR', phase='Path validation failed')
            return
        if not self.initialize_specialists():
            self._update_pipeline_status(status='ERROR', phase='Init failed')
            return
        self.initialize_super_experts()

        all_specialists = self.get_specialists()
        if not all_specialists:
            return

        # Apply filters
        if specialist_filter != 'all':
            all_specialists = [s for s in all_specialists if s['domain'] == specialist_filter]
        if model_filter != 'all':
            all_specialists = [s for s in all_specialists if s['model'] == model_filter]
        if not all_specialists:
            logger.warning(f"No specialists match filter (specialist={specialist_filter}, model={model_filter})")
            self._update_pipeline_status(status='COMPLETED', phase='No specialists matched filter')
            return

        domains_str = ', '.join(s['domain'] for s in all_specialists)
        logger.info(f"Selected specialists ({len(all_specialists)}): {domains_str}")

        max_entities = sample_size or MAX_CASCADE_ENTITIES
        model_groups = defaultdict(list)
        for specialist in all_specialists:
            model_groups[specialist['model']].append(specialist)
        sorted_models = sorted(model_groups.keys())

        try:
            # Phase A: Cascade
            phase_a_results = {s['id']: True for s in all_specialists}
            if phase in ('full', 'cascade'):
                existing = self.db_manager.execute_query(
                    "SELECT COUNT(*) as cnt FROM cascade_checkpoints", fetch=True
                )
                has_checkpoints = existing and existing[0]['cnt'] > 0
                if has_checkpoints:
                    logger.info(f"Checkpoints exist ({existing[0]['cnt']}), SKIPPING Phase A cascade")
                    self._update_pipeline_status(phase='Phase A: SKIPPED (checkpoints exist)', status='ACTIVE')
                else:
                    phase_a_results = await self.run_phase_a_cascade(all_specialists, max_entities)
            else:
                logger.info("Phase A skipped (--phase=web)")

            # Phase: Feed mode (consume pending Wikidata packages)
            if phase == 'feed':
                await self._run_wikidata_feed(all_specialists)

            # Phase B: Nurture mode (one by one)
            if phase == 'nurture':
                pipeline_start = time.time()
                await self._run_nurture_mode(
                    all_specialists, pipeline_start,
                    min_duration_hours=min_duration_hours,
                    max_duration_hours=max_duration_hours,
                    max_cycles=max_cycles,
                    report_interval_minutes=report_interval_minutes,
                )

            # Phase B: Continuous loop
            if phase in ('full', 'web'):
                loaded_vram_mb = check_ollama_vram()
                if loaded_vram_mb is not None and loaded_vram_mb > VRAM_WARN_THRESHOLD_MB:
                    logger.warning(f"ollama VRAM high ({loaded_vram_mb}MB > {VRAM_WARN_THRESHOLD_MB}MB) — potential OOM risk")

                pipeline_start = time.time()
                last_report_time = 0.0
                global_cycle = 0

                while True:
                    if _shutdown_event.is_set():
                        logger.info("Shutdown signal received. Stopping pipeline.")
                        break

                    elapsed = time.time() - pipeline_start
                    if elapsed >= min_duration_hours * 3600:
                        logger.info(f"Minimum duration reached ({min_duration_hours}h). Finishing...")
                        break

                    if max_cycles > 0 and global_cycle >= max_cycles:
                        logger.info(f"Max cycles reached ({max_cycles}). Stopping.")
                        break

                    if max_duration_hours > 0 and elapsed >= max_duration_hours * 3600:
                        logger.info(f"Hard max duration reached ({max_duration_hours}h). Stopping.")
                        break

                    global_cycle += 1
                    effective_cycle = ((global_cycle - 1) % 3) + 1

                    for model_name in sorted_models:
                        elapsed = time.time() - pipeline_start
                        if elapsed >= min_duration_hours * 3600:
                            logger.info(f"Time limit reached mid-cycle. Stopping further groups.")
                            break
                        if max_duration_hours > 0 and elapsed >= max_duration_hours * 3600:
                            logger.info(f"Hard max duration reached mid-cycle. Stopping.")
                            break

                        group = model_groups[model_name]
                        if global_cycle == 1:
                            self._update_pipeline_status(status='CHECKING_MODEL', phase=f'Verifying model: {model_name}')
                            model_ready = await self.llm_runner.ensure_model_ready(model_name)
                            if not model_ready:
                                self._update_pipeline_status(status='SKIPPED', phase=f'Model unavailable: {model_name}')
                                for specialist in group:
                                    self.update_ema_score(specialist['id'], False)
                                model_groups[model_name] = []
                                continue

                        if not group:
                            continue

                        domains = [s['domain'] for s in group]
                        self._update_pipeline_status(
                            specialist=', '.join(domains[:3]) + ('...' if len(domains) > 3 else ''),
                            model=model_name, cycle=global_cycle, total_cycles=999,
                            phase=f'Phase B: Web + LLM ({len(group)} paralelo)', status='ACTIVE'
                        )
                        tasks = [asyncio.wait_for(self.run_phase_b(s, effective_cycle), timeout=PHASE_B_PER_SPECIALIST_TIMEOUT) for s in group]
                        phase_b_results = await asyncio.gather(*tasks, return_exceptions=True)

                        for specialist, phase_b in zip(group, phase_b_results):
                            sid, domain = specialist['id'], specialist['domain']
                            if isinstance(phase_b, Exception):
                                logger.error(f"Phase B failed for {domain}: {phase_b}")
                                self.update_ema_score(sid, False)
                                continue
                            ok = phase_a_results.get(sid, False) or phase_b.get('success', False)
                            self.update_ema_score(
                                sid, ok,
                                phase_b.get('total_length', 0),
                                phase_b.get('avg_trust', 50),
                                phase_b.get('contents_count', 0),
                                phase_b.get('packages_saved', 0),
                            )

                        # Auto-spawning disabled — use manual spawn tool (tools/spawn_specialist.py)

                    new_elapsed = time.time() - pipeline_start
                    if new_elapsed - last_report_time >= report_interval_minutes * 60:
                        await self._generate_report(new_elapsed)
                        last_report_time = new_elapsed

                    if global_cycle == 1:
                        all_specialists = self.get_specialists()
                        if specialist_filter != 'all':
                            all_specialists = [s for s in all_specialists if s['domain'] == specialist_filter]
                        if model_filter != 'all':
                            all_specialists = [s for s in all_specialists if s['model'] == model_filter]
                        if not all_specialists:
                            logger.warning("No specialists match filter after re-fetch, ending Phase B")
                            break
                        model_groups = defaultdict(list)
                        for specialist in all_specialists:
                            model_groups[specialist['model']].append(specialist)
                        sorted_models = sorted(model_groups.keys())
            else:
                logger.info("Phase B skipped (--phase=cascade)")

        finally:
            await self.llm_runner.cleanup()
            self.web_scraper.cleanup()

        # Check for massive EMA drops — auto-rollback safeguard
        if hasattr(self, '_ema_snapshot'):
            ema_rows = self.db_manager.execute_query(
                "SELECT id, ema_score FROM specialist_registry", fetch=True
            ) or []
            for r in ema_rows:
                sid = r['id']
                if sid in self._ema_snapshot:
                    prev = self._ema_snapshot[sid]
                    curr = r['ema_score']
                    if curr < prev * 0.85:
                        logger.critical(f"AUTO-ROLLBACK: specialist {sid} dropped {prev:.4f} -> {curr:.4f}")
                        self.db_manager.execute_query(
                            "UPDATE specialist_registry SET ema_score=? WHERE id=?",
                            (prev, sid)
                        )

        final_elapsed = time.time() - self._start_time
        await self._generate_report(final_elapsed)
        self.metrics.print_summary()
        self._update_pipeline_status(status='COMPLETED', phase='Pipeline finalizado')
        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 80)


def parse_args():
    parser = argparse.ArgumentParser(description='Expertia Pipeline Orchestrator')
    parser.add_argument('--phase', choices=['full', 'cascade', 'web', 'nurture', 'feed'], default='full',
                        help='Pipeline phase: full=cascade+web+nurture, nurture=maintenance+growth mode (default: full)')
    parser.add_argument('--specialist', type=str, default='all',
                        help='Run only this specialist domain (default: all)')
    parser.add_argument('--model', type=str, default='all',
                        help='Run only specialists using this model (default: all)')
    parser.add_argument('--duration', type=float, default=5.0,
                        help='Minimum duration in hours for Phase B (default: 5.0)')
    parser.add_argument('--max-duration', type=float, default=0,
                        help='Hard max duration in hours (0 = no limit)')
    parser.add_argument('--max-cycles', type=int, default=0,
                        help='Hard max Phase B cycles (0 = use MAX_PHASE_B_CYCLES)')
    return parser.parse_args()


def _signal_handler(signum, frame):
    _shutdown_event.set()
    threading.Timer(5.0, os._exit, [0]).start()


async def main(sample_size: Optional[int] = None, min_duration_hours: float = 5.0,
               report_interval_minutes: int = 30,
               phase: str = 'full', specialist_filter: str = 'all',
               model_filter: str = 'all',
               max_duration_hours: float = 0,
               max_cycles: int = 0):
    crash_log = LOGS_DIR / 'crash.log'
    if PHASE_B_PER_SPECIALIST_TIMEOUT < 600:
        logger.warning(f"PHASE_B_PER_SPECIALIST_TIMEOUT={PHASE_B_PER_SPECIALIST_TIMEOUT}s es muy bajo — usar >= 600s")

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _signal_handler)
    try:
        if phase == 'nurture':
            max_cycles = 0  # nurture runs indefinitely (maintenance + growth mode)
        if phase == 'feed':
            max_cycles = 1  # feed is a single pass, not a loop
            if min_duration_hours >= 5.0:
                min_duration_hours = 0.1  # don't wait 5 hours for nothing
        controller = PipelineController(sample_size=sample_size, cycles_per_specialist=3)
        await controller.run_pipeline(
            min_duration_hours=min_duration_hours,
            report_interval_minutes=report_interval_minutes,
            phase=phase, specialist_filter=specialist_filter,
            model_filter=model_filter,
            max_duration_hours=max_duration_hours,
            max_cycles=max_cycles,
        )
    except asyncio.CancelledError:
        return
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.critical(f"Pipeline CRASHED: {e}\n{tb}")
        with open(crash_log, 'a', encoding='utf-8') as f:
            f.write(f"\n=== {datetime.now()} ===\n{e}\n{tb}\n")


if __name__ == "__main__":
    args = parse_args()
    max_retries = 1
    retry_delay = 30
    for attempt in range(1, max_retries + 1):
        logger.info(f"Pipeline attempt {attempt}/{max_retries}")
        try:
            asyncio.run(main(
                min_duration_hours=args.duration,
                report_interval_minutes=30,
                phase=args.phase,
                specialist_filter=args.specialist,
                model_filter=args.model,
                max_duration_hours=args.max_duration,
                max_cycles=args.max_cycles if args.max_cycles > 0 else MAX_PHASE_B_CYCLES,
            ))
            break
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            with open(Path('logs') / 'crash.log', 'a', encoding='utf-8') as f:
                f.write(f"\n=== FATAL {datetime.now()} ===\n{e}\n{tb}\n")
            print(f"FATAL attempt {attempt}/{max_retries}: {e}", flush=True)
            if attempt < max_retries and not _shutdown_event.is_set():
                delay = retry_delay * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s...")
                time.sleep(delay)

    # Clean up PID file so watchdog knows exit was intentional
    pidfile = Path('logs') / 'orchestrator.pid'
    try:
        if pidfile.exists():
            pidfile.unlink()
            logger.info("PID file cleaned up — normal exit")
    except Exception:
        pass
