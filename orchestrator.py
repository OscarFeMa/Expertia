"""
Coral Thought Orchestrator - Production-Ready Pipeline
Phase A: Cascade Wikidata scanning with progressive QID expansion & checkpoints
Phase B: Web scraping + LLM distillation with EMA scoring
"""

import time
import logging
import json
import asyncio
import gzip
import ijson
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Set
from decimal import Decimal
from contextlib import contextmanager
from datetime import datetime

from database.db_manager import get_db_manager
from llm_manager import LLMRunner
from web_scraper import ModernWebScraper, WebScraperError, RateLimitError
from metrics import MetricsCollector

from config.settings import (
    LOGS_DIR,
    WIKIDATA_DUMP_PATH,
    WIKIDATA_OUTPUT_DIR as TARGET_OUTPUT_DIR,
    WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
)

log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

WIKIDATA_SCHEMAS = {
    "SoftwareEngineering": {"root": "Q11661", "props": ["P31", "P279", "P306", "P400"]},
    "Mathematics": {"root": "Q395", "props": ["P31", "P279", "P2534", "P192"]},
    "Medicine": {"root": "Q11190", "props": ["P31", "P279", "P923", "P780", "P699"]},
    "LegalSystem": {"root": "Q7748", "props": ["P31", "P279", "P1684", "P427"]},
    "PhilosophyHistory": {"root": "Q315", "props": ["P31", "P279", "P61"]},
    "FinanceEconomics": {"root": "Q8134", "props": ["P31", "P279", "P2283", "P1441"]},
    "Physics": {"root": "Q11424", "props": ["P31", "P279", "P2067", "P2541"]},
    "Cybersecurity": {"root": "Q151211", "props": ["P31", "P279", "P2824"]},
    "Bioinformatics": {"root": "Q193635", "props": ["P31", "P279", "P685"]},
    "Geopolitics": {"root": "Q79461", "props": ["P31", "P279", "P30"]},
    "DataScience": {"root": "Q1156829", "props": ["P31", "P279", "P2078"]},
    "Chemistry": {"root": "Q11158", "props": ["P31", "P279", "P662", "P2067"]},
    "ArtHistory": {"root": "Q178561", "props": ["P31", "P279", "P170", "P136"]},
    "Electronics": {"root": "Q11663", "props": ["P31", "P279", "P306", "P400"]},
    "Astronomy": {"root": "Q333", "props": ["P31", "P279", "P2067"]}
}

SPECIALIST_REGISTRY = [
    {"domain": "SoftwareEngineering", "model": "qwen2.5-coder:3b", "root": "Q11661", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Mathematics", "model": "qwen2.5:3b", "root": "Q395", "props": ["P31", "P279", "P2534", "P192"]},
    {"domain": "Medicine", "model": "phi3:mini", "root": "Q11190", "props": ["P31", "P279", "P923", "P780", "P699"]},
    {"domain": "LegalSystem", "model": "llama3.2:3b", "root": "Q7748", "props": ["P31", "P279", "P1684", "P427"]},
    {"domain": "PhilosophyHistory", "model": "gemma2:2b", "root": "Q315", "props": ["P31", "P279", "P61"]},
    {"domain": "FinanceEconomics", "model": "mistral:7b", "root": "Q8134", "props": ["P31", "P279", "P2283", "P1441"]},
    {"domain": "Physics", "model": "qwen2.5:3b", "root": "Q11424", "props": ["P31", "P279", "P2067", "P2541"]},
    {"domain": "Cybersecurity", "model": "llama3.2:3b", "root": "Q151211", "props": ["P31", "P279", "P2824"]},
    {"domain": "Bioinformatics", "model": "phi3:mini", "root": "Q193635", "props": ["P31", "P279", "P685"]},
    {"domain": "Geopolitics", "model": "llama3.2:3b", "root": "Q79461", "props": ["P31", "P279", "P30"]},
    {"domain": "DataScience", "model": "qwen2.5-coder:3b", "root": "Q1156829", "props": ["P31", "P279", "P2078"]},
    {"domain": "Chemistry", "model": "qwen2.5:3b", "root": "Q11158", "props": ["P31", "P279", "P662", "P2067"]},
    {"domain": "ArtHistory", "model": "gemma2:2b", "root": "Q178561", "props": ["P31", "P279", "P170", "P136"]},
    {"domain": "Electronics", "model": "qwen2.5:3b", "root": "Q11663", "props": ["P31", "P279", "P306", "P400"]},
    {"domain": "Astronomy", "model": "qwen2.5:3b", "root": "Q333", "props": ["P31", "P279", "P2067"]}
]

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


CHECKPOINT_INTERVAL = 500_000
MAX_CASCADE_ENTITIES = 10_000_000


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (Decimal,)):
            return float(obj)
        return super().default(obj)


class BatchWikidataExtractor:
    """Scans dump ONCE, matches ALL specialists, with progressive QID expansion & checkpoints."""

    def __init__(self, input_path: Path, output_dir: Path,
                 specialist_matchers: Dict[int, Dict],
                 checkpoint_callback=None,
                 progress_callback=None):
        self.input_path = input_path
        self.output_dir = output_dir
        self.specialist_matchers = specialist_matchers
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback
        self.entities_processed = 0
        self.start_time = time.time()
        self.matched_counts: Dict[int, int] = {sid: 0 for sid in specialist_matchers}
        self.expansion_counts: Dict[int, int] = {sid: 0 for sid in specialist_matchers}
        self._last_checkpoint = 0
        self._last_progress_write = 0
        self.db_manager = get_db_manager()

    @contextmanager
    def _open_gzip_stream(self):
        try:
            with gzip.open(self.input_path, 'rb') as f:
                yield f
        except Exception as e:
            logger.error(f"Failed to open gzip stream: {e}")
            raise

    def _extract_entity_qids(self, entity: Dict) -> Set[str]:
        qids = set()
        for prop in ('P31', 'P279'):
            for claim in entity.get('claims', {}).get(prop, []):
                try:
                    qid = claim['mainsnak']['datavalue']['value']['id']
                    if qid:
                        qids.add(qid)
                except (KeyError, TypeError):
                    pass
        return qids

    def _flush_buffer(self, specialist_id: int, buffer: list):
        info = self.specialist_matchers.get(specialist_id)
        if not info or not buffer:
            return
        output_file = self.output_dir / f"cartridge_{info['domain']}.json.gz"
        try:
            with gzip.open(output_file, 'at', encoding='utf-8') as f:
                for entity in buffer:
                    f.write(json.dumps(entity, cls=DecimalEncoder) + '\n')
        except Exception as e:
            logger.error(f"Failed to write buffer for specialist {specialist_id}: {e}")

    def _flush_all_buffers(self, buffers: Dict):
        for sid, buf in buffers.items():
            if buf:
                self._flush_buffer(sid, buf)
                buf.clear()

    def extract_with_timeout(
        self,
        timeout_hours: float = 4.0,
        sample_size: Optional[int] = None,
        loaded_expansions: Optional[Dict[str, Set[int]]] = None,
    ) -> bool:
        """Single pass with progressive QID expansion and checkpoints."""
        timeout_seconds = timeout_hours * 3600
        start_ts = time.time()

        root_to_sids = defaultdict(list)
        expanded_qids_map = defaultdict(set)
        if loaded_expansions:
            for qid, sids in loaded_expansions.items():
                expanded_qids_map[qid].update(sids)
        all_root_qids = set()

        for sid, info in self.specialist_matchers.items():
            root_to_sids[info['root_qid']].append(sid)
            all_root_qids.add(info['root_qid'])

        buffers = {sid: [] for sid in self.specialist_matchers}
        discovered_expansions: Dict[int, Set[str]] = {sid: set() for sid in self.specialist_matchers}
        self.matched_counts = {sid: 0 for sid in self.specialist_matchers}
        self.expansion_counts = {sid: 0 for sid in self.specialist_matchers}

        total_expanded_qids = len(expanded_qids_map)
        logger.info(f"[Batch] Starting cascade extraction for {len(self.specialist_matchers)} specialists")
        logger.info(f"[Batch] Root QIDs: {list(root_to_sids.keys())}")
        logger.info(f"[Batch] Loaded expanded QIDs: {total_expanded_qids}")

        try:
            with self._open_gzip_stream() as f:
                parser = ijson.items(f, 'item')

                for entity in parser:
                    if (time.time() - start_ts) > timeout_seconds:
                        logger.critical("[Batch] TIMEOUT reached")
                        self._flush_all_buffers(buffers)
                        return False

                    self.entities_processed += 1

                    if self.entities_processed % 10000 == 0:
                        elapsed = time.time() - start_ts
                        total_matched = sum(self.matched_counts.values())
                        eps = self.entities_processed / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"[Batch] Processed: {self.entities_processed}, "
                            f"Matched: {total_matched}, "
                            f"Expanded QIDs: {sum(len(v) for v in discovered_expansions.values())}, "
                            f"Elapsed: {elapsed:.1f}s ({eps:.0f}/s)"
                        )
                        # Real-time progress update every 50K entities
                        if self.entities_processed - self._last_progress_write >= 50000:
                            self._last_progress_write = self.entities_processed
                            if self.progress_callback:
                                self.progress_callback(
                                    entities_processed=self.entities_processed,
                                    elapsed=elapsed,
                                    rate=eps,
                                )

                    if sample_size and self.entities_processed >= sample_size:
                        logger.info(f"[Batch] Sample size reached: {sample_size}")
                        break

                    entity_qids = self._extract_entity_qids(entity)
                    if not entity_qids:
                        continue

                    matched_sids = set()
                    trigger_by_root = set()

                    for qid in entity_qids:
                        if qid in root_to_sids:
                            for sid in root_to_sids[qid]:
                                matched_sids.add(sid)
                                trigger_by_root.add(sid)
                        if qid in expanded_qids_map:
                            matched_sids.update(expanded_qids_map[qid])

                    if not matched_sids:
                        continue

                    for sid in matched_sids:
                        buffers[sid].append(entity)
                        self.matched_counts[sid] += 1
                        if len(buffers[sid]) >= 1000:
                            self._flush_buffer(sid, buffers[sid])
                            buffers[sid] = []

                    if trigger_by_root:
                        for sid in trigger_by_root:
                            root_qid = self.specialist_matchers[sid]['root_qid']
                            for qid in entity_qids:
                                if qid != root_qid and qid not in all_root_qids:
                                    if qid not in discovered_expansions[sid]:
                                        discovered_expansions[sid].add(qid)
                                        self.expansion_counts[sid] += 1

                    # Checkpoint every CHECKPOINT_INTERVAL
                    if self.entities_processed - self._last_checkpoint >= CHECKPOINT_INTERVAL:
                        self._flush_all_buffers(buffers)
                        self._last_checkpoint = self.entities_processed
                        if self.checkpoint_callback:
                            self.checkpoint_callback(
                                cp_num=self.entities_processed // CHECKPOINT_INTERVAL,
                                entities_processed=self.entities_processed,
                                matches_per_specialist=dict(self.matched_counts),
                                expansions_per_specialist={sid: list(qs) for sid, qs in discovered_expansions.items() if qs},
                                elapsed=time.time() - start_ts,
                            )

                self._flush_all_buffers(buffers)

            elapsed = time.time() - start_ts
            total_matched = sum(self.matched_counts.values())
            logger.info(f"[Batch] Cascade completed in {elapsed:.1f}s")
            logger.info(f"[Batch] Total processed: {self.entities_processed}")
            logger.info(f"[Batch] Total matched: {total_matched}")
            for sid, count in self.matched_counts.items():
                domain = self.specialist_matchers[sid]['domain']
                added = len(discovered_expansions.get(sid, set()))
                logger.info(f"  {domain}: {count} matches, {added} expanded QIDs")
            return True

        except Exception as e:
            logger.error(f"[Batch] Extraction failed: {e}")
            self._flush_all_buffers(buffers)
            return False


class PipelineController:
    def __init__(self, sample_size: Optional[int] = None, cycles_per_specialist: int = 3):
        self.db_manager = get_db_manager()
        self.llm_runner = LLMRunner()
        self.web_scraper = ModernWebScraper()
        self.metrics = MetricsCollector()
        self._sample_size = sample_size
        self._cycles_per_specialist = cycles_per_specialist
        self._start_time = 0

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
        try:
            self.db_manager.execute_query("ALTER TABLE pipeline_status ADD COLUMN start_epoch REAL DEFAULT 0")
        except Exception:
            pass
        try:
            self.db_manager.execute_query("ALTER TABLE pipeline_status ADD COLUMN cascade_entities INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            self.db_manager.execute_query("ALTER TABLE pipeline_status ADD COLUMN cascade_max INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            self.db_manager.execute_query("ALTER TABLE pipeline_status ADD COLUMN cascade_checkpoint INTEGER DEFAULT 0")
        except Exception:
            pass

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
                           (domain, model, root_qid, properties, ema_score, tier, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (specialist['domain'], specialist['model'], specialist['root'],
                         json.dumps(specialist['props']), 0.10, 3, 'IDLE')
                    )
                    self.db_manager.execute_query(
                        """UPDATE specialist_registry 
                           SET model = ?, root_qid = ?, properties = ?, tier = ?
                           WHERE domain = ?""",
                        (specialist['model'], specialist['root'], json.dumps(specialist['props']), 3, specialist['domain'])
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
                "INSERT OR IGNORE INTO pipeline_status (id, status, start_epoch) VALUES (1, ?, ?)",
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

    def update_ema_score(self, specialist_id: int, success: bool, content_length: int = 0, trust_score: int = 50):
        try:
            result = self.db_manager.execute_query(
                "SELECT ema_score FROM specialist_registry WHERE id = ?", (specialist_id,), fetch=True
            )
            if not result:
                return
            current_ema = result[0]['ema_score']
            quality_factor = 1.0
            if success and content_length > 0:
                length_factor = min(content_length / 1000.0, 1.0)
                trust_factor = trust_score / 100.0
                quality_factor = 0.6 * length_factor + 0.4 * trust_factor
            new_ema = min(current_ema + 0.05 * quality_factor, 1.0) if success else max(current_ema - 0.02, 0.0)
            self.db_manager.execute_query(
                "UPDATE specialist_registry SET ema_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (new_ema, specialist_id)
            )
            self.db_manager.execute_query(
                "INSERT INTO ema_history (specialist_id, ema_score) VALUES (?, ?)",
                (specialist_id, new_ema)
            )
            logger.info(f"EMA {specialist_id}: {current_ema:.3f} -> {new_ema:.3f} (qf:{quality_factor:.2f})")
        except Exception as e:
            logger.error(f"Failed to update EMA: {e}")

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
                        except Exception:
                            pass
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

        extractor = BatchWikidataExtractor(
            input_path=WIKIDATA_DUMP_PATH,
            output_dir=TARGET_OUTPUT_DIR,
            specialist_matchers=specialist_matchers,
            checkpoint_callback=checkpoint_callback,
            progress_callback=progress_callback,
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

        # Vary queries per cycle for diverse knowledge
        cycle_queries = {
            1: [f"{domain} latest research 2026", f"{domain} best practices",
                f"{domain} state of the art", f"{domain} key concepts",
                f"{domain} fundamentals explained", f"{domain} modern approaches",
                f"{domain} essential knowledge", f"{domain} introduction"],
            2: [f"{domain} current trends", f"{domain} challenges and solutions",
                f"{domain} future directions", f"{domain} innovations",
                f"{domain} cutting edge research", f"{domain} expert insights",
                f"{domain}案例分析", f"{domain} overview"],
            3: [f"{domain} tools and frameworks", f"{domain} implementations",
                f"{domain} best tools 2026", f"{domain} comparison",
                f"{domain} practical guide", f"{domain} tutorial",
                f"{domain} advanced concepts", f"{domain} deep dive"],
        }
        queries = cycle_queries.get(cycle, cycle_queries[1])

        try:
            model_loaded = await self.llm_runner.ensure_model_loaded(model)
            if not model_loaded:
                logger.error(f"Failed to load model: {model}")
                return result

            self.db_manager.execute_query("UPDATE specialist_registry SET status='ACTIVE' WHERE id=?", (sid,))

            total_c, total_l, trusts, pkgs_saved = 0, 0, [], 0

            for query in queries:
                try:
                    results = await self.web_scraper.search_and_extract(query=query, max_results=5)
                    total_c += len(results)
                    for content in results:
                        ct = content.get('content', '')
                        if not ct:
                            continue
                        total_l += len(ct)
                        trust = content.get('trust_score', 50)
                        trusts.append(trust)
                        url = content.get('url', '') or content.get('source', '')
                        prompt = f"Summarize the following {domain} knowledge in 3 bullet points:\n\n{ct[:2000]}"
                        dist = await self.llm_runner.query_llm(model_name=model, prompt=prompt)
                        logger.debug(f"Distill: {dist[:100]}...")
                        # Save knowledge package
                        if dist and url:
                            try:
                                self.db_manager.execute_query(
                                    """INSERT INTO knowledge_packages (topic, source_url, domain, structured_knowledge)
                                       VALUES (?, ?, ?, ?)""",
                                    (query[:100], url, domain, dist[:500])
                                )
                                pkgs_saved += 1
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
            self.db_manager.execute_query("UPDATE specialist_registry SET status='IDLE' WHERE id=?", (sid,))
            avg_t = sum(trusts) / len(trusts) if trusts else 50.0
            logger.info(f"Phase B complete for {domain} (cycle {cycle}): {total_c} contents, {pkgs_saved} packages")
            result.update(success=total_c > 0, contents_count=total_c, total_length=total_l, avg_trust=avg_t, packages_saved=pkgs_saved)
            return result
        except Exception as e:
            logger.error(f"Phase B failed for {domain}: {e}")
            return result

    async def run_pipeline(self, sample_size: Optional[int] = None) -> None:
        logger.info("=" * 80)
        logger.info("CORAL THOUGHT ORCHESTRATOR - PIPELINE START (CASCADE MODE)")
        logger.info("=" * 80 + "\n")

        self._start_time = time.time()
        self._update_pipeline_status(status='INIT', phase='Inicializando...')

        if not validate_paths():
            self._update_pipeline_status(status='ERROR', phase='Path validation failed')
            return
        if not self.initialize_specialists():
            self._update_pipeline_status(status='ERROR', phase='Init failed')
            return

        all_specialists = self.get_specialists()
        if not all_specialists:
            return

        max_entities = sample_size or MAX_CASCADE_ENTITIES
        logger.info(f"Cascade target: {max_entities:,} entities for {len(all_specialists)} specialists")

        model_groups = defaultdict(list)
        for specialist in all_specialists:
            model_groups[specialist['model']].append(specialist)
        sorted_models = sorted(model_groups.keys())

        try:
            # Phase A: Cascade
            phase_a_results = await self.run_phase_a_cascade(all_specialists, max_entities)

            # Phase B: Parallel per model group, 3 cycles
            for model_name in sorted_models:
                group = model_groups[model_name]
                self._update_pipeline_status(status='CHECKING_MODEL', phase=f'Verificando modelo: {model_name}')
                model_available = self.llm_runner.verify_model_exists(model_name)
                if not model_available:
                    self._update_pipeline_status(status='SKIPPED', phase=f'Modelo no encontrado: {model_name}')
                    for specialist in group:
                        self.update_ema_score(specialist['id'], False)
                    continue

                for cycle in range(1, self._cycles_per_specialist + 1):
                    domains = [s['domain'] for s in group]
                    self._update_pipeline_status(
                        specialist=', '.join(domains[:3]) + ('...' if len(domains) > 3 else ''),
                        model=model_name, cycle=cycle, total_cycles=self._cycles_per_specialist,
                        phase=f'Phase B: Web + LLM ({len(group)} paralelo)', status='ACTIVE'
                    )
                    # Parallel Phase B for all specialists sharing this model
                    tasks = [self.run_phase_b(s, cycle) for s in group]
                    phase_b_results = await asyncio.gather(*tasks)

                    for specialist, phase_b in zip(group, phase_b_results):
                        sid, domain = specialist['id'], specialist['domain']
                        phase_a_ok = phase_a_results.get(sid, False)
                        ok = phase_a_ok or phase_b['success']
                        self.update_ema_score(sid, ok, phase_b.get('total_length', 0), phase_b.get('avg_trust', 50))
                        if cycle < self._cycles_per_specialist:
                            r = self.db_manager.execute_query(
                                "SELECT ema_score FROM specialist_registry WHERE id=?", (sid,), fetch=True
                            )
                            if r:
                                specialist['ema_score'] = r[0]['ema_score']

        finally:
            await self.llm_runner.cleanup()
            self.web_scraper.cleanup()

        self.metrics.print_summary()
        self._update_pipeline_status(status='COMPLETED', phase='Pipeline finalizado')
        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 80)


async def main(sample_size: Optional[int] = None, cycles: int = 3):
    controller = PipelineController(sample_size=sample_size, cycles_per_specialist=cycles)
    await controller.run_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
