"""
Python Streaming Wikidata Extractor - Zero-RAM-Bloat Implementation

Replaces wdsub with native Python streaming solution using ijson and gzip.
Processes 142 GB Wikidata JSON dump without loading into memory.

Architecture:
- Streaming decompression via gzip module
- Iterative JSON parsing via ijson
- Filter entities by TAG_TO_QID_MAP (P31/P279 properties)
- Output to compressed cartridges per domain
- Timeout and fallback mechanisms
"""

import gzip
try:
    import ijson
except ImportError:
    ijson = None
    import logging
    logging.getLogger(__name__).critical("ijson not installed — Wikidata extraction disabled")
import time
import logging
import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from decimal import Decimal
from contextlib import contextmanager
from datetime import datetime

from database.db_manager import get_db_manager


logger = logging.getLogger(__name__)


# ============================================================================
# PATH CONFIGURATION  (single source: config/settings.py)
# ============================================================================

from config.settings import (
    WIKIDATA_DUMP_PATH,
    WIKIDATA_OUTPUT_DIR as TARGET_OUTPUT_DIR,
    WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
    LANGUAGES,
)
from tools.update_wikidata import build_structured_knowledge, _pick_first

# ============================================================================
# WIKIDATA QID MAPPING
# ============================================================================

TAG_TO_QID_MAP: Dict[str, str] = {
    # Formal Sciences
    "mathematics": "Q395",
    "logic": "Q4091",
    "algorithms": "Q21198",
    "statistics": "Q39194",
    "computing": "Q11661",
    "formal": "Q11359",
    
    # Engineering
    "physics": "Q413",
    "mechanics": "Q1016",
    "chemistry": "Q2329",
    "industrial": "Q2329",
    "infrastructure": "Q38833",
    "materials": "Q38672",
    "software": "Q11661",
    
    # Economy
    "finance": "Q43015",
    "markets": "Q37654",
    "competition": "Q486975",
    "macroeconomics": "Q9102",
    "trade": "Q5272",
    "game_theory": "Q131193",
    
    # Legal
    "law": "Q362",
    "regulation": "Q1143825",
    "compliance": "Q188451",
    "policy": "Q373204",
    "standard": "Q163872",
    "oauth2": "Q2301042",
    
    # Humanities
    "history": "Q309",
    "geopolitics": "Q171408",
    "culture": "Q11042",
    "sociology": "Q192525",
    "society": "Q870",
    "empire": "Q1725",
    
    # Biology
    "health": "Q12147",
    "medicine": "Q11190",
    "environment": "Q7150",
    "ecology": "Q17999",
    "biochemistry": "Q1660",
    "organic": "Q23614"
}


# ============================================================================
# STREAMING EXTRACTOR
# ============================================================================

class DecimalEncoder(json.JSONEncoder):
    """Custom encoder that handles Decimal types from Wikidata quantities."""
    def default(self, obj):
        if isinstance(obj, (Decimal,)):
            return float(obj)
        return super().default(obj)


class WikidataStreamingExtractor:
    """Zero-RAM-Bloat Wikidata extractor using ijson and gzip streaming.
    
    Supports two matching modes:
    1. target_qids: direct set of QIDs to check P31/P279 against
    2. custom_matcher: callable(entity) -> bool for custom logic
    """
    
    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        target_qids: Set[str] = None,
        domain: str = None,
        expert_id: int = 0,
        custom_matcher = None,
    ):
        """Initialize the streaming extractor.
        
        Args:
            input_path: Path to Wikidata JSON.gz dump
            output_dir: Directory for output cartridges
            target_qids: Set of QIDs to filter (P31/P279 values) or None
            domain: Domain name for output file
            expert_id: Expert ID for tracking
            custom_matcher: Optional callable(entity) -> bool override
        """
        self.input_path = input_path
        self.output_dir = output_dir
        self.target_qids = target_qids or set()
        self.domain = domain or "unknown"
        self.expert_id = expert_id
        self._custom_matcher = custom_matcher
        self.db_manager = get_db_manager()
        
        # Statistics
        self.entities_processed = 0
        self.entities_matched = 0
        self.start_time = time.time()
    
    @contextmanager
    def _open_gzip_stream(self):
        """Context manager for gzip file streaming."""
        try:
            with gzip.open(self.input_path, 'rb') as f:
                yield f
        except Exception as e:
            logger.error(f"Failed to open gzip stream: {e}")
            raise
    
    def _entity_matches_target(self, entity: Dict) -> bool:
        """Check if entity matches via custom_matcher or target QIDs.
        
        Args:
            entity: Wikidata entity dictionary
            
        Returns:
            bool: True if entity matches
        """
        # If custom_matcher is provided, use it (overrides target_qids)
        if self._custom_matcher is not None:
            return self._custom_matcher(entity)
        
        claims = entity.get('claims', {})
        
        # Check P31 (instance of)
        if 'P31' in claims:
            for claim in claims['P31']:
                try:
                    mainsnak = claim.get('mainsnak', {})
                    datavalue = mainsnak.get('datavalue', {})
                    qid = datavalue.get('value', {}).get('id', '')
                    if qid in self.target_qids:
                        return True
                except (KeyError, TypeError):
                    continue
        
        # Check P279 (subclass of)
        if 'P279' in claims:
            for claim in claims['P279']:
                try:
                    mainsnak = claim.get('mainsnak', {})
                    datavalue = mainsnak.get('datavalue', {})
                    qid = datavalue.get('value', {}).get('id', '')
                    if qid in self.target_qids:
                        return True
                except (KeyError, TypeError):
                    continue
        
        return False
    
    def _update_progress(self, progress_pct: float) -> None:
        """Update progress in database.
        
        Args:
            progress_pct: Progress percentage (0-100)
        """
        try:
            self.db_manager.execute_query(
                """
                UPDATE cartridge_offsets 
                SET status = ?
                WHERE specialist_id = ?
                """,
                (f"PROCESSING: {progress_pct:.1f}%", self.expert_id)
            )
        except Exception as e:
            logger.warning(f"Failed to update progress: {e}")
    
    def extract_with_timeout(
        self,
        timeout_hours: float = 4.0,
        sample_size: Optional[int] = None
    ) -> bool:
        """Extract matching entities with timeout protection.
        
        Args:
            timeout_hours: Maximum execution time in hours
            sample_size: Optional limit for testing (None = full processing)
            
        Returns:
            bool: True if extraction completed successfully
        """
        timeout_seconds = timeout_hours * 3600
        start_time = time.time()
        
        output_file = self.output_dir / f"cartridge_{self.domain}.json.gz"
        matched_entities = []
        
        logger.info(f"[Expert {self.expert_id}] Starting extraction. Timeout: {timeout_hours}h")
        if self._custom_matcher:
            logger.info(f"[Expert {self.expert_id}] Using custom matcher (root QID from schema)")
        else:
            logger.info(f"[Expert {self.expert_id}] Target QIDs: {len(self.target_qids)}")
        
        try:
            with self._open_gzip_stream() as f:
                # Use ijson to stream JSON items
                parser = ijson.items(f, 'item')
                
                for entity in parser:
                    # Check timeout
                    if (time.time() - start_time) > timeout_seconds:
                        logger.critical(f"[Expert {self.expert_id}] TIMEOUT reached")
                        return False
                    
                    self.entities_processed += 1
                    
                    # Log progress every 10000 entities
                    if self.entities_processed % 10000 == 0:
                        elapsed = time.time() - start_time
                        progress = (self.entities_processed / sample_size * 100) if sample_size else 0
                        logger.info(
                            f"[Expert {self.expert_id}] Processed: {self.entities_processed}, "
                            f"Matched: {self.entities_matched}, "
                            f"Elapsed: {elapsed:.1f}s"
                        )
                        if sample_size:
                            self._update_progress(progress)
                    
                    # Sample size limit for testing
                    if sample_size and self.entities_processed >= sample_size:
                        logger.info(f"[Expert {self.expert_id}] Sample size reached: {sample_size}")
                        break
                    
                    # Check if entity matches target
                    if self._entity_matches_target(entity):
                        matched_entities.append(entity)
                        self.entities_matched += 1
                        
                        # Write matched entities periodically to avoid memory buildup
                        if len(matched_entities) >= 1000:
                            self._write_entities_to_file(matched_entities, output_file)
                            matched_entities = []
                
                # Write remaining entities
                if matched_entities:
                    self._write_entities_to_file(matched_entities, output_file)
            
            elapsed = time.time() - start_time
            logger.info(f"[Expert {self.expert_id}] Extraction completed in {elapsed:.1f}s")
            logger.info(f"[Expert {self.expert_id}] Total processed: {self.entities_processed}")
            logger.info(f"[Expert {self.expert_id}] Total matched: {self.entities_matched}")
            
            return True
            
        except Exception as e:
            logger.error(f"[Expert {self.expert_id}] Extraction failed: {e}")
            return False
    
    def _write_entities_to_file(self, entities: List[Dict], output_file: Path) -> None:
        """Write entities to compressed output file.
        
        Args:
            entities: List of entity dictionaries
            output_file: Output file path
        """
        try:
            with gzip.open(output_file, 'at', encoding='utf-8') as f:
                for entity in entities:
                    f.write(json.dumps(entity, cls=DecimalEncoder) + '\n')
        except Exception as e:
            logger.error(f"Failed to write entities to file: {e}")
            raise


# ============================================================================
# BATCH EXTRACTOR (multi-specialist single-pass)
# ============================================================================

CHECKPOINT_INTERVAL = 50000


class ClassHierarchyCache:
    """Cache for specialist root QID hierarchy."""
    def __init__(self, specialist_root_qids: Dict[str, str]):
        self.root_qids = specialist_root_qids


class BatchWikidataExtractor:
    """Multi-specialist single-pass Wikidata extractor.

    Opens the dump once and checks each entity against all specialists'
    target QIDs simultaneously, tracking per-specialist match counts.
    Saves matched QIDs to matched_qids table for later processing via API.
    Supports progressive QID expansion via loaded_expansions.
    """
    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        specialist_matchers: Dict,
        checkpoint_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        hierarchy_cache: Optional[ClassHierarchyCache] = None,
        db_manager=None,
    ):
        self.input_path = input_path
        self.output_dir = output_dir
        self.specialist_matchers = specialist_matchers
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback
        self.hierarchy_cache = hierarchy_cache
        self.db_manager = db_manager or get_db_manager()

        self.entities_processed = 0
        self.matched_counts: Dict[str, int] = {}
        self._start_time = 0
        self._pending_qids: List[tuple] = []  # batch buffer for QID inserts
        self._pending_packages: List[tuple] = []  # batch buffer for knowledge_packages

    def extract_with_timeout(
        self,
        timeout_hours: float = 4.0,
        sample_size: Optional[int] = None,
        loaded_expansions: Optional[Dict[str, Set[int]]] = None,
        resume_offset: int = 0,
    ) -> bool:
        timeout_seconds = timeout_hours * 3600
        self._start_time = time.time()
        loaded_expansions = loaded_expansions or {}

        spec_targets: Dict[str, Set[str]] = {}
        for sid, info in self.specialist_matchers.items():
            root_qid = info.get('root_qid')
            if root_qid:
                qid_set = {root_qid}
                for qid, spec_ids in loaded_expansions.items():
                    if sid in spec_ids:
                        qid_set.add(qid)
                spec_targets[sid] = qid_set

        checkpoint_num = 0
        expansions_since_checkpoint: Dict[str, Set[str]] = {}

        try:
            with gzip.open(self.input_path, 'rb') as f:
                parser = ijson.basic_parse(f)
                skipped = 0

                # Fast skip: count events without building objects
                if resume_offset > 0:
                    depth = 0
                    for event, value in parser:
                        if event == 'start_map':
                            depth += 1
                        elif event == 'end_map':
                            depth -= 1
                            if depth == 0:
                                skipped += 1
                                if skipped % 500000 == 0:
                                    logger.info(f"Reanudando: saltadas {skipped:,} entidades ya procesadas...")
                                    if self.progress_callback:
                                        skip_elapsed = time.time() - self._start_time
                                        skip_rate = skipped / skip_elapsed if skip_elapsed > 0 else 0
                                        self.progress_callback(skipped, skip_elapsed, skip_rate)
                                if skipped >= resume_offset:
                                    break
                    self.entities_processed = skipped
                    logger.info(f"Reanudacion: saltadas {skipped:,} entidades, reanudando desde entidad {self.entities_processed:,}")

                entity_gen = self._iter_entities(parser)
                for entity in entity_gen:
                    elapsed = time.time() - self._start_time
                    if elapsed > timeout_seconds:
                        logger.critical("Batch extraction TIMEOUT reached")
                        return False

                    self.entities_processed += 1

                    if self.entities_processed % 10000 == 0 and self.progress_callback:
                        rate = self.entities_processed / elapsed if elapsed > 0 else 0
                        self.progress_callback(self.entities_processed, elapsed, rate)

                    if sample_size and self.entities_processed >= sample_size:
                        break

                    entity_qids = self._get_entity_qids(entity)
                    matched_specs = set()
                    for sid, targets in spec_targets.items():
                        if entity_qids & targets:
                            matched_specs.add(sid)

                    for sid in matched_specs:
                        self.matched_counts[sid] = self.matched_counts.get(sid, 0) + 1

                    if matched_specs:
                        for qid in entity_qids:
                            for sid in matched_specs:
                                if qid not in spec_targets.get(sid, set()):
                                    expansions_since_checkpoint.setdefault(sid, set()).add(qid)

                    # Save matched QIDs to matched_qids table for later API fetching
                    for sid in matched_specs:
                        entity_id = entity.get('id', '')
                        if entity_id:
                            self._pending_qids.append((entity_id, sid, entity_id, ''))
                            if len(self._pending_qids) >= 500:
                                self._flush_qids()

                    # Build knowledge packages directly from dump data (no API needed)
                    if matched_specs and entity.get('id'):
                        eid = entity['id']
                        langs = LANGUAGES.split('|')
                        label = _pick_first(entity.get('labels') or {}, langs)
                        structured = build_structured_knowledge(entity, LANGUAGES)
                        if structured and len(structured.strip()) >= 20:
                            topic = f'{label} — Wikidata entity' if label else f'{eid} — Wikidata entity'
                            source_url = f'https://www.wikidata.org/entity/{eid}'
                            for sid in matched_specs:
                                domain = self.specialist_matchers[sid]['domain']
                                self._pending_packages.append((topic, source_url, domain, eid, structured))
                                if len(self._pending_packages) >= 500:
                                    self._flush_packages()

                    if self.entities_processed % CHECKPOINT_INTERVAL == 0 and self.checkpoint_callback:
                        checkpoint_num += 1
                        self.checkpoint_callback(
                            checkpoint_num,
                            self.entities_processed,
                            dict(self.matched_counts),
                            {k: list(v) for k, v in expansions_since_checkpoint.items()},
                            elapsed,
                        )
                        expansions_since_checkpoint.clear()

            if expansions_since_checkpoint and self.checkpoint_callback:
                checkpoint_num += 1
                self.checkpoint_callback(
                    checkpoint_num,
                    self.entities_processed,
                    dict(self.matched_counts),
                    {k: list(v) for k, v in expansions_since_checkpoint.items()},
                    time.time() - self._start_time,
                )

            # Flush remaining QIDs
            if self._pending_qids:
                self._flush_qids()

            # Flush remaining knowledge packages
            if self._pending_packages:
                self._flush_packages()

            return True

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            return False

    @staticmethod
    def _iter_entities(parser):
        """Yield complete entity dicts from a basic_parse generator."""
        for event, value in parser:
            if event != 'start_map':
                continue
            builder = ijson.ObjectBuilder()
            builder.event(event, value)
            depth = 1
            for e, v in parser:
                builder.event(e, v)
                if e == 'end_map':
                    depth -= 1
                    if depth == 0:
                        yield builder.value
                        break
                elif e == 'start_map':
                    depth += 1

    def _ensure_matched_qids_table(self):
        """Create matched_qids table if it doesn't exist (lost during emergency purges)."""
        try:
            self.db_manager.execute_query(
                """CREATE TABLE IF NOT EXISTS matched_qids (
                    qid TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT 'wikidata',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
        except Exception as e:
            logger.warning(f"Failed to ensure matched_qids table: {e}")

    def _flush_qids(self):
        """Flush buffered matched QIDs to database in batch."""
        if not self._pending_qids:
            return
        count = len(self._pending_qids)
        # Make sure the target table exists
        self._ensure_matched_qids_table()
        for attempt in range(4):
            try:
                self.db_manager.execute_many(
                    """INSERT OR IGNORE INTO matched_qids
                       (qid, specialist_id, entity_id, domain)
                       VALUES (?, ?, ?, ?)""",
                    self._pending_qids
                )
                logger.info(f"Wikidata: saved {count} matched QIDs to matched_qids")
                self._pending_qids = []
                return
            except Exception as e:
                err_msg = str(e).lower()
                if attempt < 3 and ("no such table" in err_msg):
                    logger.warning(f"matched_qids table missing, creating and retrying: {e}")
                    self._ensure_matched_qids_table()
                    time.sleep(0.5)
                    continue
                if attempt < 3 and ("locked" in err_msg or "busy" in err_msg or "timeout" in err_msg):
                    wait = 1.0 * (2 ** attempt)
                    logger.warning(f"DB locked, retrying in {wait:.1f}s (attempt {attempt+1}/4): {e}")
                    time.sleep(wait)
                    continue
                logger.warning(f"Wikidata QID batch insert failed ({count} qids): {e}")
                # Safe dump: save to JSON on final failure
                self._safe_dump(self._pending_qids, f"qids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                self._pending_qids = []
                return

    def _safe_dump(self, data, filename: str):
        """Save failed batch to JSON crash dump for later re-ingestion."""
        try:
            crash_dir = Path(self.output_dir) / "crash_dumps"
            crash_dir.mkdir(parents=True, exist_ok=True)
            path = crash_dir / filename
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.warning(f"Safe dump saved: {path} ({len(data)} items)")
        except Exception as dump_e:
            logger.error(f"Safe dump failed: {dump_e}")

    def _flush_packages(self):
        """Flush buffered knowledge packages to database in batch."""
        if not self._pending_packages:
            return
        count = len(self._pending_packages)
        for attempt in range(4):
            try:
                self.db_manager.execute_many(
                    """INSERT OR IGNORE INTO knowledge_packages
                       (topic, source_url, domain, qid, structured_knowledge, created_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    self._pending_packages
                )
                logger.info(f"Wikidata: saved {count} knowledge packages directly from dump")
                self._pending_packages = []
                return
            except Exception as e:
                err_msg = str(e).lower()
                if attempt < 3 and ("locked" in err_msg or "busy" in err_msg or "timeout" in err_msg):
                    wait = 1.0 * (2 ** attempt)
                    logger.warning(f"DB locked, retrying packages in {wait:.1f}s (attempt {attempt+1}/4): {e}")
                    time.sleep(wait)
                    continue
                logger.warning(f"Wikidata package batch insert failed ({count} pkgs): {e}")
                self._safe_dump(self._pending_packages, f"packages_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                self._pending_packages = []
                return

    def _get_entity_qids(self, entity: Dict) -> Set[str]:
        """Extract all QIDs from entity claims (P31, P279, P2579, P921, P101)."""
        qids = set()
        claims = entity.get('claims', {})
        for prop_id in ('P31', 'P279', 'P2579', 'P921', 'P101'):
            for claim in claims.get(prop_id, []):
                try:
                    qid = claim.get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('id')
                    if qid and qid.startswith('Q'):
                        qids.add(qid)
                except Exception:
                    pass
        return qids


# ============================================================================
# ORCHESTRATION
# ============================================================================

def get_active_specialists() -> List[Dict]:
    """Fetch active specialists from database."""
    db_manager = get_db_manager()
    
    try:
        specialists = db_manager.execute_query(
            """
            SELECT id, domain, model, root_qid, properties, ema_score, status
            FROM specialist_registry
            ORDER BY ema_score ASC
            """,
            fetch=True
        )
        logger.info(f"Found {len(specialists)} specialists")
        return specialists
    except Exception as e:
        logger.error(f"Failed to fetch specialists: {e}")
        return []


def is_specialist_inoculated(specialist_id: int) -> bool:
    """Check if specialist has been inoculated with local cartridge.
    
    Args:
        specialist_id: Specialist ID to check
        
    Returns:
        bool: True if inoculated or fallback triggered
    """
    db_manager = get_db_manager()
    
    try:
        result = db_manager.execute_query(
            """
            SELECT status FROM cartridge_offsets 
            WHERE specialist_id = ?
            """,
            (specialist_id,),
            fetch=True
        )
        
        if not result:
            return False
        
        status = result[0]['status']
        return status in ['COMPLETED', 'FALLBACK_TRIGGERED']
        
    except Exception as e:
        logger.warning(f"Failed to check inoculation status: {e}")
        return False


def handle_extraction_failure(specialist_id: int) -> None:
    """Activate fallback mechanism for failed extraction.
    
    Args:
        specialist_id: Specialist ID to mark for fallback
    """
    db_manager = get_db_manager()
    
    try:
        db_manager.execute_query(
            """
            UPDATE cartridge_offsets 
            SET status = 'FALLBACK_TRIGGERED' 
            WHERE specialist_id = ?
            """,
            (specialist_id,)
        )
        logger.warning(f"Specialist {specialist_id} marked as FALLBACK_TRIGGERED")
    except Exception as e:
        logger.error(f"Failed to register fallback: {e}")


def main(sample_size: Optional[int] = None, timeout_hours: float = None):
    """Main standalone entry point for dissect_wikidata.
    
    Args:
        sample_size: Optional limit for testing (None = full processing)
        timeout_hours: Maximum execution time per specialist
    """
    if timeout_hours is None:
        timeout_hours = WIKIDATA_EXTRACTION_TIMEOUT_HOURS
    
    logger.info("=" * 80)
    logger.info("PYTHON STREAMING WIKIDATA EXTRACTOR (standalone)")
    logger.info("=" * 80 + "\n")
    
    # Ensure DB tables exist
    db_manager = get_db_manager()
    db_manager.initialize_specialist_tables()
    
    # Create output directory
    TARGET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Fetch specialists
    specialists = get_active_specialists()
    
    if not specialists:
        logger.warning("No specialists found in database.")
        logger.info("Run orchestrator.py first to initialize specialists.")
        return
    
    # Process each specialist
    for specialist in specialists:
        specialist_id = specialist['id']
        domain = specialist['domain']
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing Specialist: {domain} (ID: {specialist_id})")
        logger.info(f"{'=' * 60}")
        
        # Check if already inoculated
        if is_specialist_inoculated(specialist_id):
            logger.info(f"Specialist {specialist_id} already inoculated. Skipping.")
            continue
        
        # Build QID set from root_qid
        root_qid = specialist['root_qid']
        target_qids = {root_qid}
        
        # Initialize tracking record
        try:
            db_manager.execute_query(
                """
                INSERT OR REPLACE INTO cartridge_offsets 
                (qid, cartridge_name, specialist_id, status)
                VALUES (?, ?, ?, ?)
                """,
                (f"specialist_{specialist_id}", f"cartridge_{domain}.json.gz", specialist_id, "PROCESSING: 0%")
            )
        except Exception as e:
            logger.error(f"Failed to initialize tracking: {e}")
        
        # Create extractor with root QID matching
        extractor = WikidataStreamingExtractor(
            input_path=WIKIDATA_DUMP_PATH,
            output_dir=TARGET_OUTPUT_DIR,
            target_qids=target_qids,
            domain=domain,
            expert_id=specialist_id
        )
        
        # Extract with timeout
        success = extractor.extract_with_timeout(
            timeout_hours=timeout_hours,
            sample_size=sample_size
        )
        
        # Update final status
        if success:
            db_manager.execute_query(
                """
                UPDATE cartridge_offsets 
                SET status = 'COMPLETED'
                WHERE specialist_id = ?
                """,
                (specialist_id,)
            )
            logger.info(f"Specialist {specialist_id} extraction completed successfully.")
        else:
            handle_extraction_failure(specialist_id)
            logger.warning(f"Specialist {specialist_id} extraction failed. Fallback activated.")
    
    logger.info("\n" + "=" * 80)
    logger.info("WIKIDATA EXTRACTION COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    # For testing with sample size
    # main(sample_size=1000, timeout_hours=0.5)
    
    # For full processing
    main(sample_size=None, timeout_hours=4.0)
