"""
Coral Thought Orchestrator - Production-Ready Pipeline
Phase A: Cascade Wikidata scanning with progressive QID expansion & checkpoints
Phase B: Web scraping + LLM distillation with EMA scoring
"""

import sys
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
from dissect_wikidata_mp import ParallelWikidataExtractor
from tools.update_wikidata import fetch_entities_batch, build_structured_knowledge

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
    TIER_SILVER: {"ema": 0.95, "quality": 0.70, "fail_rate": 0.08, "packages": 500},
    TIER_GOLD: {"ema": 0.97, "quality": 0.78, "fail_rate": 0.03, "packages": 1500},
}

LEGEND_EMA_MIN = 0.999
LEGEND_CYCLES_CLEAN = 50

NURTURE_CYCLE_TIMEOUT = 1800  # 30 min per specialist cycle
NURTURE_MAX_CYCLES_PER_TARGET = 30  # max cycles before forcing target switch

# ── Nurture Priority Scoring Weights ─────────────────────────────────────────
NURTURE_W_EMA        = 10.0   # Low EMA = high priority
NURTURE_W_FAIL        = 8.0    # High fail rate = high priority
NURTURE_W_STALENESS   = 0.5    # Days since last update
NURTURE_W_PACKAGES    = 3.0    # Few packages = high priority
NURTURE_PACKAGE_TARGET = 500   # Packages target for scoring normalization

# Domain stability: controls how urgently stale knowledge decays per domain
# 1.0 = very stable (Math), decays slowly — 0.3 = volatile (Geopolitics), decays fast
DOMAIN_STABILITY = {
    "Geopolitics": 0.3, "Cybersecurity": 0.4, "FinanceEconomics": 0.5,
    "Medicine": 0.5, "LegalSystem": 0.5,
    "DataScience": 0.6, "SoftwareEngineering": 0.6, "Electronics": 0.6,
    "Linguistics": 0.6, "Psychology": 0.5, "Sociology": 0.5,
    "EnvironmentalScience": 0.4,
    "Physics": 0.8, "Chemistry": 0.8, "Astronomy": 0.8,
    "PhilosophyHistory": 0.9, "ArtHistory": 0.9, "Mathematics": 1.0,
    "GeneralKnowledge": 0.7,
}

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
        logger.warning(f"ollama ps failed: {e}")
        return None

from database.db_manager import get_db_manager
from llm_manager import LLMRunner
from web_scraper import ModernWebScraper, WebScraperError, RateLimitError
from metrics import MetricsCollector
from knowledge_ingestor import KnowledgeIngestor

from config.settings import (
    LOGS_DIR,
    DATABASE_PATH,
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
    LANGUAGES,
)
from config.log_setup import setup_logging

log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
setup_logging(log_file=log_file)
logger = logging.getLogger(__name__)

SPECIALIST_REGISTRY = [
    {"domain": "SoftwareEngineering", "model": "qwen2.5-coder:3b", "root": "Q80993", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Mathematics", "model": "qwen2.5-coder:3b", "root": "Q395", "props": ["P31", "P279", "P2534", "P192"]},
    {"domain": "Medicine", "model": "phi4-mini:3.8b", "root": "Q11190", "props": ["P31", "P279", "P923", "P780", "P699"]},
    {"domain": "LegalSystem", "model": "llama3.2:3b", "root": "Q7748", "props": ["P31", "P279", "P1684", "P427"]},
    {"domain": "PhilosophyHistory", "model": "phi4-mini:3.8b", "root": "Q5891", "props": ["P31", "P279", "P61"]},
    {"domain": "FinanceEconomics", "model": "phi4-mini:3.8b", "root": "Q8134", "props": ["P31", "P279", "P2283", "P1441"]},
    {"domain": "Physics", "model": "phi4-mini:3.8b", "root": "Q413", "props": ["P31", "P279", "P2067", "P2541"]},
    {"domain": "Cybersecurity", "model": "qwen2.5-coder:3b", "root": "Q3510521", "props": ["P31", "P279", "P2824"]},
    {"domain": "Geopolitics", "model": "llama3.2:3b", "root": "Q159385", "props": ["P31", "P279", "P30"]},
    {"domain": "DataScience", "model": "qwen2.5-coder:3b", "root": "Q2374463", "props": ["P31", "P279", "P2078"]},
    {"domain": "Chemistry", "model": "phi4-mini:3.8b", "root": "Q2329", "props": ["P31", "P279", "P662", "P2067"]},
    {"domain": "ArtHistory", "model": "phi4-mini:3.8b", "root": "Q50637", "props": ["P31", "P279", "P170", "P136"]},
    {"domain": "Electronics", "model": "qwen2.5-coder:3b", "root": "Q11650", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Astronomy", "model": "phi4-mini:3.8b", "root": "Q333", "props": ["P31", "P279", "P2067"]},
    {"domain": "Linguistics", "model": "phi4-mini:3.8b", "root": "Q81798", "props": ["P31", "P279", "P2826", "P1990"]},
    {"domain": "Psychology", "model": "phi4-mini:3.8b", "root": "Q9418", "props": ["P31", "P279", "P921", "P659"]},
    {"domain": "EnvironmentalScience", "model": "phi4-mini:3.8b", "root": "Q188069", "props": ["P31", "P279", "P361", "P527"]},
    {"domain": "Sociology", "model": "llama3.2:3b", "root": "Q21201", "props": ["P31", "P279", "P2826", "P101"]}
]

# Derive WIKIDATA_SCHEMAS from single source of truth
WIKIDATA_SCHEMAS = {s["domain"]: {"root": s["root"], "props": list(s["props"])}
                     for s in SPECIALIST_REGISTRY}

SUPER_EXPERTS = {
    "LanguagesLinguistics": {
        "description": "Language, linguistics, NLP, philology, semiotics and communication theory",
        "members": {"Linguistics": 0.25, "PhilosophyHistory": 0.20, "DataScience": 0.15, "ArtHistory": 0.15, "SoftwareEngineering": 0.10, "LegalSystem": 0.10, "Mathematics": 0.05}
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
        "description": "Medicine, drug discovery, genomics, bioinformatics and healthcare technology",
        "members": {"Medicine": 0.40, "Chemistry": 0.20, "DataScience": 0.20, "SoftwareEngineering": 0.10, "LegalSystem": 0.10}
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
        "members": {"EnvironmentalScience": 0.20, "Chemistry": 0.15, "Physics": 0.15, "DataScience": 0.15, "Geopolitics": 0.15, "FinanceEconomics": 0.10, "LegalSystem": 0.05, "Medicine": 0.05}
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
        "members": {"Medicine": 0.25, "Psychology": 0.20, "DataScience": 0.15, "Physics": 0.10, "Chemistry": 0.10, "SoftwareEngineering": 0.10, "PhilosophyHistory": 0.10}
    },
    "SocietyAndCulture": {
        "description": "Social structures, cultural dynamics, institutions, inequality, demography and collective behavior",
        "members": {"Sociology": 0.25, "PhilosophyHistory": 0.20, "Geopolitics": 0.15, "ArtHistory": 0.15, "LegalSystem": 0.10, "FinanceEconomics": 0.10, "Psychology": 0.05}
    },
    "GeneralKnowledge": {
        "description": "Cross-domain synthesis — all specialists contributing proportionally by packages absorbed",
        "members": {"SoftwareEngineering": 0.08, "Mathematics": 0.07, "Medicine": 0.08, "LegalSystem": 0.06, "PhilosophyHistory": 0.08, "FinanceEconomics": 0.06, "Physics": 0.08, "Cybersecurity": 0.06, "Geopolitics": 0.05, "DataScience": 0.08, "Chemistry": 0.07, "ArtHistory": 0.06, "Electronics": 0.04, "Astronomy": 0.06, "Linguistics": 0.05, "Psychology": 0.04, "EnvironmentalScience": 0.04, "Sociology": 0.04}
    }
}


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
    # Circuit breaker for Ollama failures
    _ollama_consecutive_failures = 0
    _ollama_circuit_open = False
    _ollama_circuit_opened_at = 0.0
    _OLLAMA_FAILURE_THRESHOLD = 3
    _OLLAMA_CIRCUIT_AUTO_RESET_SECONDS = 60  # 1 min auto-reset

    # Cascade detection: prevents failure spirals that destroy EMA
    _cascaded_specialists = {}  # {sid: {'detected_at': float, 'original_ema': float}}

    def __init__(self, sample_size: Optional[int] = None, cycles_per_specialist: int = 3,
                 parallel_workers: int = 1):
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
        self.parallel_workers = parallel_workers
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
                CREATE INDEX IF NOT EXISTS idx_activity_log_level
                ON activity_log(level, id)
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
            CREATE INDEX IF NOT EXISTS idx_qid_expansions_specialist_checkpoint
            ON qid_expansions(specialist_id, discovered_at_checkpoint)
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
            logger.warning(f"Status update failed: {e}")

    def _compute_tier(self, specialist_id: int, ema: float, current_tier: int) -> int:
        try:
            row = self.db_manager.execute_query(
                "SELECT weighted_success, weighted_fail, packages_absorbed, wikidata_total_entities FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not row:
                return TIER_NONE
            ws = row[0].get('weighted_success', 0.0) or 0.0
            wf = row[0].get('weighted_fail', 0.0) or 0.0
            packages = row[0].get('packages_absorbed', 0) or 0
            wikidata_total = row[0].get('wikidata_total_entities', 0) or 0

            # Knowledge coverage: % of available Wikidata entities consumed
            if wikidata_total > 0:
                coverage = min(packages / wikidata_total, 1.0)
                effective_ema = ema * coverage
            else:
                coverage = 1.0  # sin datos de wikidata, no hay restriccion
                effective_ema = ema
            ema = effective_ema  # usar EMA efectivo para evaluar tiers

            # Rolling window: use last 25 cycles for avg_quality to reflect recent improvements faster
            ch = self.db_manager.execute_query(
                """SELECT COUNT(*) as total,
                          COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END), 0) as fails,
                          COALESCE(AVG(CASE WHEN success=1 THEN quality ELSE NULL END), 0) as avg_q
                   FROM (SELECT * FROM cycle_history WHERE specialist_id = ? ORDER BY id DESC LIMIT 25) recent""",
                (specialist_id,), fetch=True
            )
            total_cycles_all = self.db_manager.execute_query(
                "SELECT COUNT(*) as cnt FROM cycle_history WHERE specialist_id = ?",
                (specialist_id,), fetch=True
            )
            all_count = total_cycles_all[0]['cnt'] if total_cycles_all else 0

            if ch and ch[0]['total'] > 0:
                total_cycles = all_count
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
                # Check if Gold qualifies for Legend promotion
                if ema >= LEGEND_EMA_MIN:
                    clean = self._clean_cycle_count(specialist_id)
                    if clean >= LEGEND_CYCLES_CLEAN:
                        return TIER_LEGEND
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
            logger.warning(f"Racha 25 failed: {e}")
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
            logger.warning(f"Clean cycle count failed: {e}")
            return 0

    def _check_cascade(self, specialist_id: int, current_ema: float) -> bool:
        """Detect failure cascades and mitigate. Returns True if cascade was active."""
        cascade_info = PipelineController._cascaded_specialists.get(specialist_id)
        now = time.time()

        # If currently cascading, check if cooldown expired
        if cascade_info:
            cooldown = 300  # 5 min cooldown
            if now - cascade_info['detected_at'] > cooldown:
                # Recovery: restore a reasonable EMA
                recovered_ema = max(current_ema, cascade_info['original_ema'] * 0.5)
                if current_ema < recovered_ema:
                    self.db_manager.execute_query(
                        "UPDATE specialist_registry SET ema_score = ?, weighted_fail = 0 WHERE id = ?",
                        (recovered_ema, specialist_id)
                    )
                    logger.warning(f"CASCADE RECOVERED: specialist {specialist_id} restored to EMA={recovered_ema:.4f}")
                    self._log_activity(f"Cascade recuperado: specialist {specialist_id} restaurado a {recovered_ema:.4f}", 'WARNING')
                del PipelineController._cascaded_specialists[specialist_id]
                return False
            return True  # Still cascading

        # Detect: 100+ failures or EMA dropped >80% in one cycle
        recent = self.db_manager.execute_query(
            "SELECT COUNT(*) as total, COALESCE(SUM(CASE WHEN success=0 THEN 1 ELSE 0 END), 0) as fails "
            "FROM (SELECT success FROM cycle_history WHERE specialist_id = ? ORDER BY id DESC LIMIT 50)",
            (specialist_id,), fetch=True
        )
        if recent and recent[0]['total'] >= 20:
            fails_50 = recent[0]['fails']
            if fails_50 >= 20:
                logger.critical(f"CASCADE DETECTED: specialist {specialist_id} — {fails_50}/{recent[0]['total']} failures in last 50 cycles")
                PipelineController._cascaded_specialists[specialist_id] = {
                    'detected_at': now,
                    'original_ema': current_ema,
                }
                # Reset circuit breaker
                PipelineController._ollama_circuit_open = False
                PipelineController._ollama_consecutive_failures = 0
                # Clean spam cycles
                last_good = self.db_manager.execute_query(
                    "SELECT COALESCE(MAX(id), 0) FROM cycle_history WHERE specialist_id = ? AND success = 1",
                    (specialist_id,), fetch=True
                )
                lg_id = last_good[0][0] if last_good else 0
                if lg_id > 0:
                    deleted = self.db_manager.execute_query(
                        "SELECT COUNT(*) FROM cycle_history WHERE specialist_id = ? AND id > ? AND success = 0",
                        (specialist_id, lg_id), fetch=True
                    )
                    count = deleted[0][0] if deleted else 0
                    self.db_manager.execute_query(
                        "DELETE FROM cycle_history WHERE specialist_id = ? AND id > ? AND success = 0",
                        (specialist_id, lg_id)
                    )
                    self._log_activity(f"CASCADE: eliminados {count} ciclos de fallo de {specialist_id}", 'WARNING')
                self._log_activity(f"CASCADE DETECTED: specialist {specialist_id} — pausado 5 min", 'CRITICAL')
                return True
        return False

    def update_ema_score(self, specialist_id: int, success: bool, content_length: int = 0,
                         trust_score: int = 50, contents_count: int = 0, packages_saved: int = 0,
                         is_feed: bool = False):
        try:
            # Cascade detection: if specialist is in failure spiral, skip update entirely
            if not success and PipelineController._cascaded_specialists.get(specialist_id):
                logger.warning(f"CASCADE ACTIVE: skipping EMA update for specialist {specialist_id}")
                return
            result = self.db_manager.execute_query(
                "SELECT ema_score, weighted_success, weighted_fail, tier, updated_at FROM specialist_registry WHERE id = ?",
                (specialist_id,), fetch=True
            )
            if not result:
                return
            row = result[0]
            current_ema = row['ema_score'] or 0.0

            # EMA decay for inactivity >48h
            updated_at = row.get('updated_at', '')
            if updated_at:
                try:
                    last_update = datetime.strptime(str(updated_at)[:19], '%Y-%m-%d %H:%M:%S')
                    hours_since = (datetime.now() - last_update).total_seconds() / 3600
                    if hours_since > 48:
                        decay_factor = 1.0 - (0.0005 * (hours_since - 48))
                        decayed_ema = current_ema * max(decay_factor, 0.5)
                        if decayed_ema < current_ema:
                            logger.info(f"EMA decay for specialist {specialist_id}: {current_ema:.4f} -> {decayed_ema:.4f} (inactive {hours_since:.0f}h)")
                            current_ema = decayed_ema
                except (ValueError, TypeError):
                    pass
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

            # Auto-cascade detection: if EMA just collapsed or failures spike
            if new_ema < 0.01 and current_ema >= 0.10:
                if self._check_cascade(specialist_id, current_ema):
                    logger.critical(f"CASCADE TRIGGERED: specialist {specialist_id} EMA collapsed {current_ema:.4f} -> {new_ema:.4f}")
                    return  # Skip saving the bad state

            self.db_manager.execute_batch([
                ("UPDATE specialist_registry SET ema_score=?, weighted_success=?, weighted_fail=?, "
                 "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (new_ema, ws, wf, specialist_id)),
                ("INSERT INTO ema_history (specialist_id, ema_score) VALUES (?, ?)",
                 (specialist_id, new_ema)),
                ("INSERT INTO cycle_history (specialist_id, success, quality, ema_before, ema_after) VALUES (?, ?, ?, ?, ?)",
                 (specialist_id, 1 if success else 0, quality, current_ema, new_ema)),
            ])

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

    def _batch_resolve_labels(self, qids: List[str], languages: str = LANGUAGES) -> Dict[str, str]:
        """Resolve labels (in configured languages) for a batch of QIDs via Wikidata API.
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
                        'languages': languages,
                    },
                    headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
                if 'entities' in data:
                    for qid, entity in data['entities'].items():
                        label = self._pick_label(entity.get('labels', {}), languages, qid)
                        cached[qid] = label
                        result[qid] = label
            except Exception as e:
                logger.warning(f"Label resolution failed for batch starting at {batch[0]}: {e}")
                for qid in batch:
                    if qid not in result:
                        result[qid] = qid
                        cached[qid] = qid

        if len(cached) > 100000:
            # Evict oldest 50% to avoid thundering herd
            items = list(cached.items())
            cached = dict(items[len(items)//2:])
        self._label_cache = cached
        return result

    @staticmethod
    def _pick_label(labels: Dict, languages: str = LANGUAGES, fallback: str = '') -> str:
        """Pick the first available label from a language-keyed dict ordered by language preference."""
        if not labels:
            return fallback
        for lang in languages.split('|'):
            val = labels.get(lang, {}).get('value', '')
            if val:
                return val
        # fallback to any language
        for v in labels.values():
            val = v.get('value', '')
            if val:
                return val
        return fallback

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
            "SELECT id, domain FROM specialist_registry", fetch=True
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
                    text = ((pkg.get('topic') or '') + ' ' + (pkg.get('structured_knowledge') or '')).lower()
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

    async def run_phase_a_cascade(self, specialists: List[Dict], max_entities: int = MAX_CASCADE_ENTITIES, resume_offset: int = 0) -> Dict[int, bool]:
        """Cascade Phase A: scan dump once with progressive checkpoints and QID expansion.
        resume_offset: skip this many entities (reanudar desde checkpoint anterior)."""
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
                # Periodic WAL checkpoint to prevent WAL bloat (>1GB blocks API reads)
                if cp_num % 5 == 0:
                    try:
                        self.db_manager.execute_query("PRAGMA wal_checkpoint(PASSIVE)")
                    except Exception:
                        pass
                self._update_pipeline_status(
                    phase=f'Phase A: Cascade (cp {cp_num})',
                    cascade_entities=entities_processed, cascade_max=max_entities,
                    cascade_checkpoint=cp_num,
                    status='ACTIVE'
                )
            except Exception as e:
                logger.error(f"Checkpoint callback failed: {e}")

        def progress_callback(entities_processed, elapsed, rate):
            try:
                self._update_pipeline_status(
                    phase=f'Phase A: {entities_processed:,} ent ({rate:.0f}/s)',
                    cascade_entities=entities_processed, cascade_max=max_entities,
                    status='ACTIVE'
                )
            except Exception:
                pass

        hierarchy_cache = ClassHierarchyCache(
            {sid: info['root_qid'] for sid, info in specialist_matchers.items()}
        )

        # Boost write performance for cascade phase + WAL auto-checkpoint
        try:
            self.db_manager.execute_query("PRAGMA synchronous=OFF")
            self.db_manager.execute_query("PRAGMA cache_size=-256000")
            self.db_manager.execute_query("PRAGMA wal_autocheckpoint=1000")
        except Exception as e:
            logger.warning(f"Failed to set cascade pragmas: {e}")

        if self.parallel_workers > 1:
            logger.info(f"\n{'='*80}")
            logger.info(f"PHASE A: CASCADE (MULTI-CORE) — {self.parallel_workers} workers")
            logger.info(f"Scanning up to {max_entities:,} entities")
            logger.info(f"Checkpoints every {CHECKPOINT_INTERVAL:,}")
            logger.info(f"{'='*80}\n")
            extractor = ParallelWikidataExtractor(
                specialist_matchers=specialist_matchers,
                db_path=str(DATABASE_PATH),
                num_workers=self.parallel_workers,
                progress_callback=progress_callback,
                checkpoint_callback=checkpoint_callback,
            )
        else:
            extractor = BatchWikidataExtractor(
                input_path=WIKIDATA_DUMP_PATH,
                output_dir=TARGET_OUTPUT_DIR,
                specialist_matchers=specialist_matchers,
                checkpoint_callback=checkpoint_callback,
                progress_callback=progress_callback,
                hierarchy_cache=hierarchy_cache,
                db_manager=self.db_manager,
            )

            logger.info(f"\n{'='*80}")
            logger.info(f"PHASE A: CASCADE — scanning up to {max_entities:,} entities")
            logger.info(f"Checkpoints every {CHECKPOINT_INTERVAL:,}, QID expansion active")
            logger.info(f"{'='*80}\n")

        success = extractor.extract_with_timeout(
            timeout_hours=WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
            sample_size=max_entities,
            loaded_expansions=loaded_expansions,
            resume_offset=resume_offset,
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
                # Save total matched Wikidata entities for coverage calculation
                if matched > 0:
                    self.db_manager.execute_query(
                        "UPDATE specialist_registry SET wikidata_total_entities = ? WHERE id = ?",
                        (matched, sid)
                    )
                    logger.info(f"Wikidata total for {info['domain']}: {matched} entities")

        # Restore normal pragmas
        try:
            self.db_manager.execute_query("PRAGMA synchronous=NORMAL")
            self.db_manager.execute_query("PRAGMA cache_size=-64000")
        except Exception as e:
            logger.warning(f"Failed to restore pragmas: {e}")

        if not success:
            for sid in specialist_matchers:
                self.handle_extraction_failure(sid)

        # After Phase A: fetch matched QIDs via API and insert as knowledge_packages
        if success:
            await self._fetch_and_insert_from_qids()

        return results

    async def _fetch_and_insert_from_qids(self):
        """Fetch details for matched QIDs from Wikidata API and insert as knowledge_packages.
        Called after Phase A completes to process the QIDs collected in matched_qids table."""
        rows = self.db_manager.execute_query(
            "SELECT qid, specialist_id, domain FROM matched_qids WHERE processed = 0 ORDER BY specialist_id",
            fetch=True
        )
        if not rows:
            logger.info("No pending QIDs to fetch")
            return

        # Group QIDs by specialist
        qids_by_spec = {}
        for row in rows:
            sid = row['specialist_id']
            qids_by_spec.setdefault(sid, []).append(row['qid'])

        total_qids = len(rows)
        processed = 0
        total_inserted = 0

        logger.info(f"Fetching details for {total_qids} matched QIDs via Wikidata API...")

        for sid, qids in qids_by_spec.items():
            spec = self.db_manager.execute_query(
                "SELECT domain FROM specialist_registry WHERE id = ?", (sid,), fetch=True
            )
            domain = spec[0]['domain'] if spec else 'unknown'
            batch_size = WIKIDATA_LABEL_BATCH_SIZE

            for i in range(0, len(qids), batch_size):
                batch = qids[i:i + batch_size]
                try:
                    entities = fetch_entities_batch(batch)
                    packages = []
                    for qid in batch:
                        entity = entities.get(qid)
                        if not entity:
                            continue
                        structured = build_structured_knowledge(entity)
                        if not structured or len(structured.strip()) < 20:
                            continue
                        label = self._pick_label(entity.get('labels') or {}, LANGUAGES, qid)
                        topic = f'{label} — Wikidata entity'
                        source_url = f'https://www.wikidata.org/entity/{qid}'
                        packages.append((topic, source_url, domain, qid, structured))

                    if packages:
                        self.db_manager.execute_many(
                            """INSERT OR IGNORE INTO knowledge_packages
                               (topic, source_url, domain, qid, structured_knowledge, created_at)
                               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            packages
                        )
                        total_inserted += len(packages)
                except Exception as e:
                    logger.warning(f"Failed to fetch/insert batch for {domain} ({batch[0]}..{batch[-1]}): {e}")

                processed += len(batch)
                if processed % 1000 == 0:
                    logger.info(f"Wikidata API fetch: {processed}/{total_qids} QIDs procesados, {total_inserted} packages insertados")

            # Mark all QIDs for this specialist as processed
            self.db_manager.execute_query(
                "UPDATE matched_qids SET processed = 1 WHERE specialist_id = ?", (sid,)
            )

        logger.info(f"Wikidata API fetch COMPLETO: {total_inserted} knowledge packages insertados de {total_qids} QIDs")

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

        # Circuit breaker: skip if Ollama has failed too many times consecutively
        if PipelineController._ollama_circuit_open:
            # Auto-reset after N seconds to avoid infinite skip loops
            if time.time() - PipelineController._ollama_circuit_opened_at > PipelineController._OLLAMA_CIRCUIT_AUTO_RESET_SECONDS:
                logger.info("Circuit breaker AUTO-RESET after timeout — retrying Ollama")
                PipelineController._ollama_circuit_open = False
                PipelineController._ollama_consecutive_failures = 0
            else:
                logger.warning(f"Circuit breaker OPEN — skipping {domain} (Ollama {PipelineController._ollama_consecutive_failures} consecutive failures)")
                self._log_activity(f"SKIP {domain} — circuit breaker open (Ollama unavailable)", 'WARNING')
                return result

        try:
            self._log_activity(f"Cargando modelo {model} para {domain}")
            model_loaded = await self.llm_runner.ensure_model_loaded(model)
            if not model_loaded:
                logger.error(f"Failed to load model: {model}")
                self._log_activity(f"ERROR: modelo {model} no disponible", 'ERROR')
                PipelineController._ollama_consecutive_failures += 1
                if PipelineController._ollama_consecutive_failures >= PipelineController._OLLAMA_FAILURE_THRESHOLD and not PipelineController._ollama_circuit_open:
                    PipelineController._ollama_circuit_open = True
                    PipelineController._ollama_circuit_opened_at = time.time()
                    logger.critical(f"Circuit breaker OPENED after {PipelineController._ollama_consecutive_failures} consecutive Ollama failures")
                return result
            
            # Model loaded successfully — reset circuit breaker
            PipelineController._ollama_consecutive_failures = 0
            PipelineController._ollama_circuit_open = False

            self._log_activity(f"Modelo {model} listo — iniciando {domain}")
            self.db_manager.execute_query("UPDATE specialist_registry SET status='ACTIVE' WHERE id=?", (sid,))

            total_c, total_l, trusts, pkgs_saved = 0, 0, [], 0

            for query in queries:
                self._log_activity(f"{domain} > Buscando: \"{query[:60]}\"")
                try:
                    results = await asyncio.wait_for(
                        self.web_scraper.search_and_extract(query=query, domain=domain),
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
                        # Quality gate: reject low-trust sources and irrelevant distillations
                        if trust < 40:
                            logger.warning(f"Low trust source ({trust}), skipping {url[:60]}")
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
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available — skipping report chart")
            plt = None

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
        series_raw = defaultdict(list)
        time_labels = []
        for row in history:
            sid = row['specialist_id']
            t = row['timestamp'][:16] if row['timestamp'] else ''
            series_raw[sid].append((t, row['ema_score']))
        for sid, pts in series_raw.items():
            time_labels = [p[0] for p in pts]

        # Chart: combined EMA evolution (×100.000 scale)
        if plt is not None:
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

        if plt is not None:
            lines.append(f"\n## Charts\n")
            lines.append(f"![EMA Evolution](ema_evolution_{ts}.png)\n")

        report_path = report_dir / f'report_{ts}.md'
        report_path.write_text('\n'.join(lines), encoding='utf-8')
        logger.info(f"Report saved: {report_path}")

    def _compute_nurture_priority(self, specialist: dict) -> float:
        """Compute nurture priority score. Higher = more urgent.
        Domain-aware staleness: volatile domains (Geopolitics) decay faster
        than stable ones (Mathematics).
        Base staleness: all specialists gain urgency after 4h without a cycle."""
        ema = specialist.get('ema_score', 0.5)
        packages = specialist.get('packages_absorbed', 0)
        updated_at = specialist.get('updated_at', '')
        weighted_success = specialist.get('weighted_success', 0.0)
        weighted_fail = specialist.get('weighted_fail', 0.0)
        domain = specialist.get('domain', '')

        total_ws_wf = weighted_success + weighted_fail
        fail_rate = weighted_fail / total_ws_wf if total_ws_wf > 0 else 0.0

        # Domain-aware staleness: volatile domains (< 1.0) increase urgency faster
        stability = DOMAIN_STABILITY.get(domain, 0.7)
        staleness_weight = 1.0 / max(stability, 0.1)

        staleness_days = 0.0
        if updated_at:
            try:
                last_update = datetime.strptime(str(updated_at)[:19], '%Y-%m-%d %H:%M:%S')
                staleness_days = (datetime.now() - last_update).total_seconds() / 86400
            except (ValueError, TypeError):
                staleness_days = 7.0

        # Base staleness: all specialists gain urgency after 4h idle (domain-independent)
        staleness_hours = staleness_days * 24
        base_idle_urgency = max(0, staleness_hours - 4) * 0.15

        score = (
            (1.0 - ema) * NURTURE_W_EMA
            + fail_rate * NURTURE_W_FAIL
            + staleness_days * NURTURE_W_STALENESS * staleness_weight
            + base_idle_urgency  # base factor: +0.15/h after 4h idle
            + max(0, 1.0 - packages / NURTURE_PACKAGE_TARGET) * NURTURE_W_PACKAGES
        )
        return round(score, 4)

    async def _run_nurture_mode(self, all_specialists: list, pipeline_start: float,
                                 min_duration_hours: float, max_duration_hours: float,
                                 max_cycles: int, report_interval_minutes: int,
                                 skip_list: str = ''):
        logger.info("=" * 80)
        logger.info("NURTURE V2 — Tier Ascension System")
        logger.info("Target: all specialists to GOLD, then LEGEND. Domain-aware decay.")
        logger.info("=" * 80)

        global_cycle = 0
        last_report_time = 0.0
        current_target = None
        current_target_tier = TIER_GOLD
        target_cycles = 0

        while True:
            if _shutdown_event.is_set():
                logger.info("Shutdown signal received. Stopping nurture.")
                break

            # ── Check if current target reached its goal ──
            if current_target:
                sid, domain = current_target
                row = self.db_manager.execute_query(
                    "SELECT tier FROM specialist_registry WHERE id=?",
                    (sid,), fetch=True
                )
                if row and row[0]['tier'] >= current_target_tier:
                    logger.info(f">>> {domain} alcanzo {TIER_NAMES.get(current_target_tier, '?')} <<<")
                    current_target = None
                    target_cycles = 0

            # ── Max cycles per target: force switch if stuck ──
            if current_target and target_cycles >= NURTURE_MAX_CYCLES_PER_TARGET:
                sid, domain = current_target
                logger.warning(f">>> TARGET STUCK: {domain} no alcanzo {TIER_NAMES.get(current_target_tier, '?')} tras {target_cycles} ciclos. Pasando al siguiente... <<<")
                current_target = None
                target_cycles = 0

            # ── Select next target ──
            if not current_target:
                all_parents = self.db_manager.execute_query(
                    "SELECT id, domain, ema_score, tier, weighted_success, weighted_fail, "
                    "packages_absorbed, updated_at FROM specialist_registry "
                    "WHERE parent_id IS NULL ORDER BY domain",
                    fetch=True
                )
                if not all_parents:
                    break

                all_done = all(s['tier'] >= current_target_tier for s in all_parents)
                if all_done:
                    if current_target_tier == TIER_GOLD:
                        current_target_tier = TIER_LEGEND
                        logger.info(">>> ALL SPECIALISTS GOLD! Now targeting LEGEND... <<<")
                        continue
                    else:
                        logger.info(">>> ALL SPECIALISTS LEGEND! Maintaining indefinitely... <<<")
                        await asyncio.sleep(60)
                        continue

                skip_domains = set(d.strip() for d in skip_list.split(',') if d.strip())
                scored = []
                for s in all_parents:
                    if s['tier'] >= current_target_tier:
                        continue
                    if s['domain'] in skip_domains:
                        continue
                    score = self._compute_nurture_priority(s)
                    scored.append((score, s))

                if not scored:
                    await asyncio.sleep(10)
                    continue

                scored.sort(key=lambda x: x[0], reverse=True)
                _, worst = scored[0]
                current_target = (worst['id'], worst['domain'])
                logger.info(f">>> NEW TARGET: {worst['domain']} (score={scored[0][0]:.2f}, tier={TIER_NAMES.get(worst['tier'], '?')}) <<<")

            # ── Feed the current target ──
            sid, domain = current_target
            spec_row = self.db_manager.execute_query(
                "SELECT * FROM specialist_registry WHERE id=?", (sid,), fetch=True
            )
            if not spec_row:
                current_target = None
                continue
            specialist = spec_row[0]
            model = specialist['model']
            current_ema = specialist.get('ema_score', 0.0)

            global_cycle += 1
            target_cycles += 1
            effective_cycle = ((global_cycle - 1) % 3) + 1

            tier_name = TIER_NAMES.get(specialist.get('tier', TIER_NONE), '?')
            target_name = TIER_NAMES.get(current_target_tier, '?')
            self._update_pipeline_status(
                specialist=domain, model=model, cycle=global_cycle, total_cycles=999,
                phase=f'Nurture v2: {domain} ({tier_name} -> {target_name})', status='ACTIVE'
            )
            logger.info(f"Nurture cycle {global_cycle}: {domain} ({tier_name} -> {target_name}, EMA={current_ema:.4f})")

            model_ready = await self.llm_runner.ensure_model_ready(model)
            if not model_ready:
                logger.error(f"Model {model} unavailable for {domain} — skipping")
                await asyncio.sleep(10)
                current_target = None
                continue

            try:
                phase_b = await asyncio.wait_for(
                    self.run_phase_b(specialist, effective_cycle),
                    timeout=NURTURE_CYCLE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning(f"Nurture cycle timed out for {domain} — retrying")
                continue
            except Exception as e:
                logger.error(f"Nurture cycle failed for {domain}: {e}")
                self.update_ema_score(sid, False)
                continue

            # Circuit breaker skip: don't count as failure, just retry later
            if PipelineController._ollama_circuit_open:
                logger.warning(f"Circuit breaker OPEN for {domain} — skipping without penalty")
                await asyncio.sleep(30)
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
            pkgs_this_cycle = phase_b.get('packages_saved', 0)
            logger.info(f"Nurture progress: {domain} EMA {current_ema:.4f} -> {new_ema:.4f} ({pkgs_this_cycle} pkgs, {effective_cycle}/3 cycle)")

            elapsed = time.time() - pipeline_start
            if elapsed - last_report_time >= report_interval_minutes * 60:
                await self._generate_report(elapsed)
                last_report_time = elapsed

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
                           packages_absorbed = packages_absorbed + ?,
                           last_wikidata_feed = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (cnt, cnt, sid)
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
                           max_cycles: int = 0,
                            from_zero: bool = False,
                            parallel_workers: int = 1,
                            skip_list: str = '') -> None:
        logger.info("=" * 80)
        logger.info("CORAL THOUGHT ORCHESTRATOR - PIPELINE")
        logger.info(f"Phase: {phase} | Specialist: {specialist_filter} | Model: {model_filter}")
        if from_zero and phase in ('full', 'cascade'):
            logger.info("--from-zero activo: Phase A comenzará desde entidad 0 (ignorando checkpoints)")
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
            filter_domains = [d.strip() for d in specialist_filter.split(',')]
            all_specialists = [s for s in all_specialists if s['domain'] in filter_domains]
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
            # Phase A: Cascade — reanudable desde el último checkpoint
            phase_a_results = {s['id']: True for s in all_specialists}
            if phase in ('full', 'cascade'):
                # Obtener el último checkpoint como offset de reanudación
                if from_zero:
                    resume_offset = 0
                    logger.info("Phase A: --from-zero forzado — ejecutando desde entidad 0")
                else:
                    last_cp = self.db_manager.execute_query(
                        "SELECT COALESCE(entities_processed, 0) AS cnt FROM cascade_checkpoints ORDER BY id DESC LIMIT 1", fetch=True
                    )
                    resume_offset = last_cp[0]['cnt'] if last_cp else 0
                    if resume_offset > 0:
                        logger.info(f"Phase A: reanudando desde entidad {resume_offset:,} (ultimo checkpoint)")
                    else:
                        logger.info("Phase A: ejecutando desde el principio (sin checkpoints previos)")
                phase_a_results = await self.run_phase_a_cascade(all_specialists, max_entities, resume_offset=resume_offset)
            else:
                logger.info("Phase A skipped (--phase=nurture)")

            # Auto-feed: absorb unabsorbed Wikidata packages from cascade
            if phase in ('full', 'feed'):
                logger.info("Auto-feed: absorbiendo packages de Wikidata...")
                await self._run_wikidata_feed(all_specialists)

            # Phase B: Nurture mode (one by one) — usado por --phase full y --phase nurture
            if phase in ('nurture', 'full'):
                pipeline_start = time.time()
                await self._run_nurture_mode(
                    all_specialists, pipeline_start,
                    min_duration_hours=min_duration_hours,
                    max_duration_hours=max_duration_hours,
                    max_cycles=max_cycles,
                    report_interval_minutes=report_interval_minutes,
                    skip_list=skip_list,
                )

            # Phase B: Continuous loop (solo --phase web, full ya va a Nurture)
            if phase == 'web':
                loaded_vram_mb = await asyncio.to_thread(check_ollama_vram)
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
                            filter_domains = [d.strip() for d in specialist_filter.split(',')]
                            all_specialists = [s for s in all_specialists if s['domain'] in filter_domains]
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
                    curr = r['ema_score'] or 0.0
                    if curr < prev * 0.85:
                        logger.critical(f"AUTO-ROLLBACK: specialist {sid} dropped {prev:.4f} -> {curr:.4f}")
                        self.db_manager.execute_query(
                            "UPDATE specialist_registry SET ema_score=? WHERE id=?",
                            (prev, sid)
                        )
                        old_tier = self.db_manager.execute_query(
                            "SELECT tier FROM specialist_registry WHERE id=?",
                            (sid,), fetch=True
                        )
                        current_tier_val = old_tier[0]['tier'] if old_tier else 0
                        new_tier = self._compute_tier(sid, prev, current_tier_val)
                        self.db_manager.execute_query(
                            "UPDATE specialist_registry SET tier=? WHERE id=?",
                            (new_tier, sid)
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
    parser.add_argument('--from-zero', action='store_true',
                        help='Ignore checkpoints and start Phase A from entity 0')
    parser.add_argument('--parallel', type=int, default=1,
                        help='Number of parallel worker processes for Phase A (default: 1)')
    parser.add_argument('--skip', type=str, default='',
                        help='Comma-separated list of specialist domains to skip (default: none)')
    return parser.parse_args()


def _signal_handler(signum, frame):
    _shutdown_event.set()
    threading.Timer(5.0, lambda: asyncio.get_event_loop().stop()).start()


async def main(sample_size: Optional[int] = None, min_duration_hours: float = 5.0,
               report_interval_minutes: int = 30,
               phase: str = 'full', specialist_filter: str = 'all',
               model_filter: str = 'all',
               max_duration_hours: float = 0,
               max_cycles: int = 0,
               from_zero: bool = False,
               parallel_workers: int = 1,
               skip_list: str = ''):
    crash_log = LOGS_DIR / 'crash.log'
    if PHASE_B_PER_SPECIALIST_TIMEOUT < 600:
        logger.warning(f"PHASE_B_PER_SPECIALIST_TIMEOUT={PHASE_B_PER_SPECIALIST_TIMEOUT}s es muy bajo — usar >= 600s")

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, _signal_handler)
    try:
        if phase in ('nurture', 'full'):
            max_cycles = 0  # runs indefinitely
            min_duration_hours = 999999  # effectively infinite
            max_duration_hours = 0       # no hard limit
        if phase == 'feed':
            max_cycles = 1  # feed is a single pass, not a loop
            if min_duration_hours >= 5.0:
                min_duration_hours = 0.1  # don't wait 5 hours for nothing
        controller = PipelineController(sample_size=sample_size, cycles_per_specialist=3,
                                         parallel_workers=parallel_workers)
        await controller.run_pipeline(
            min_duration_hours=min_duration_hours,
            report_interval_minutes=report_interval_minutes,
            phase=phase, specialist_filter=specialist_filter,
            model_filter=model_filter,
            max_duration_hours=max_duration_hours,
            max_cycles=max_cycles,
            from_zero=from_zero,
            parallel_workers=parallel_workers,
            skip_list=skip_list,
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
                from_zero=args.from_zero,
                parallel_workers=args.parallel,
                skip_list=args.skip,
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
