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
import ijson
import time
import logging
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from decimal import Decimal
from contextlib import contextmanager

from database.db_manager import get_db_manager


logger = logging.getLogger(__name__)


# ============================================================================
# PATH CONFIGURATION  (single source: config/settings.py)
# ============================================================================

from config.settings import (
    WIKIDATA_DUMP_PATH,
    WIKIDATA_OUTPUT_DIR as TARGET_OUTPUT_DIR,
    WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
)

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
    ):
        self.input_path = input_path
        self.output_dir = output_dir
        self.specialist_matchers = specialist_matchers
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback
        self.hierarchy_cache = hierarchy_cache

        self.entities_processed = 0
        self.matched_counts: Dict[str, int] = {}
        self._start_time = 0

    def extract_with_timeout(
        self,
        timeout_hours: float = 4.0,
        sample_size: Optional[int] = None,
        loaded_expansions: Optional[Dict[str, Set[int]]] = None,
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
                parser = ijson.items(f, 'item')

                for entity in parser:
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

            return True

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            return False

    def _get_entity_qids(self, entity: Dict) -> Set[str]:
        """Extract all QIDs from entity claims (P31 and P279)."""
        qids = set()
        claims = entity.get('claims', {})
        for prop_id in ('P31', 'P279'):
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
