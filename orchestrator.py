"""
Coral Thought Orchestrator - Production-Ready Pipeline

Implements the 15-specialist architecture with:
- StreamingDissector via dissect_wikidata.py (reused, zero-RAM-bloat)
- LLMRunner: Single-Active-Model policy
- PipelineController: Phase A (Wikidata) + Phase B (Web Scraping)
- Metrics: Performance counters and progress tracking
- Scoring: EMA score updates after successful cycles

Hardware Constraints: NVIDIA RTX 1660 (6GB VRAM), 32GB RAM
"""

import time
import logging
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable

from database.db_manager import get_db_manager
from llm_manager import LLMRunner
from web_scraper import ModernWebScraper, WebScraperError, RateLimitError
from metrics import MetricsCollector

from config.settings import (
    WIKIDATA_DUMP_PATH,
    WIKIDATA_OUTPUT_DIR as TARGET_OUTPUT_DIR,
    WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
    DISTILLATION_MODEL,
    SUITABILITY_THRESHOLD,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# ONTOLOGY MAPPING (WIKIDATA P-CODES)
# ============================================================================

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

# ============================================================================
# SPECIALIST REGISTRY (15 EXPERTS)
# ============================================================================

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

# ============================================================================
# IMPORT SHARED WIKIDATA EXTRACTOR (avoids code duplication)
# ============================================================================

from dissect_wikidata import WikidataStreamingExtractor


# ============================================================================
# PATH VALIDATION
# ============================================================================

def validate_paths() -> bool:
    """Validate that input path exists and output directory is creatable.
    
    Returns:
        bool: True if all paths are valid, False otherwise
    """
    all_valid = True
    
    # Wikidata dump must exist
    if not WIKIDATA_DUMP_PATH.exists():
        logger.critical(f"Wikidata dump not found: {WIKIDATA_DUMP_PATH}")
        all_valid = False
    else:
        logger.info(f"Wikidata dump found: {WIKIDATA_DUMP_PATH}")
    
    # Output directory: create if missing
    try:
        TARGET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory ready: {TARGET_OUTPUT_DIR}")
    except Exception as e:
        logger.critical(f"Cannot create output directory {TARGET_OUTPUT_DIR}: {e}")
        all_valid = False
    
    return all_valid


# ============================================================================
# PIPELINE CONTROLLER (MAIN ORCHESTRATION)
# ============================================================================

class PipelineController:
    """Main pipeline controller for Phase A and Phase B execution."""
    
    def __init__(self, sample_size: Optional[int] = None):
        """Initialize the pipeline controller.
        
        Args:
            sample_size: Optional limit for testing (None = full processing)
        """
        self.db_manager = get_db_manager()
        self.llm_runner = LLMRunner()
        self.web_scraper = ModernWebScraper()
        self.metrics = MetricsCollector()
        self._sample_size = sample_size
    
    def initialize_specialists(self) -> bool:
        """Initialize specialist registry in database.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Initialize tables
            if not self.db_manager.initialize_specialist_tables():
                logger.error("Failed to initialize specialist tables")
                return False
            
            # Insert specialists from registry
            for specialist in SPECIALIST_REGISTRY:
                try:
                    self.db_manager.execute_query(
                        """
                        INSERT OR REPLACE INTO specialist_registry 
                        (domain, model, root_qid, properties, ema_score, tier, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            specialist['domain'],
                            specialist['model'],
                            specialist['root'],
                            json.dumps(specialist['props']),
                            0.10,  # Base EMA score
                            3,  # Tier 3
                            'IDLE'
                        )
                    )
                    logger.info(f"Initialized specialist: {specialist['domain']}")
                except Exception as e:
                    logger.error(f"Failed to insert specialist {specialist['domain']}: {e}")
            
            logger.info("Specialist registry initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize specialists: {e}")
            return False
    
    def get_specialists(self) -> List[Dict]:
        """Fetch all specialists from database.
        
        Returns:
            List[Dict]: List of specialist dictionaries
        """
        try:
            specialists = self.db_manager.execute_query(
                """
                SELECT id, domain, model, root_qid, properties, ema_score, status
                FROM specialist_registry
                ORDER BY ema_score ASC
                """,
                fetch=True
            )
            return specialists if specialists else []
        except Exception as e:
            logger.error(f"Failed to fetch specialists: {e}")
            return []
    
    def handle_extraction_failure(self, specialist_id: int) -> None:
        """Activate fallback mechanism for failed extraction.
        
        Args:
            specialist_id: Specialist ID to mark for fallback
        """
        try:
            self.db_manager.execute_query(
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
    
    def update_ema_score(
        self,
        specialist_id: int,
        success: bool,
        content_length: int = 0,
        trust_score: int = 50
    ) -> None:
        """Update EMA score for specialist after cycle with dynamic scoring.
        
        Args:
            specialist_id: Specialist ID to update
            success: Whether the cycle was successful
            content_length: Length of content extracted (for quality assessment)
            trust_score: Trust score of source (0-100)
        """
        try:
            # Get current EMA score
            result = self.db_manager.execute_query(
                """
                SELECT ema_score FROM specialist_registry WHERE id = ?
                """,
                (specialist_id,),
                fetch=True
            )
            
            if not result:
                return
            
            current_ema = result[0]['ema_score']
            
            # Calculate quality factor based on content length and trust score
            quality_factor = 1.0
            
            if success and content_length > 0:
                # Normalize content length (0-1000 chars -> 0-1.0)
                length_factor = min(content_length / 1000.0, 1.0)
                # Normalize trust score (0-100 -> 0-1.0)
                trust_factor = trust_score / 100.0
                # Combined quality factor
                quality_factor = 0.6 * length_factor + 0.4 * trust_factor
            
            # Calculate new EMA score with dynamic adjustment
            if success:
                # Base increment adjusted by quality factor
                increment = 0.05 * quality_factor
                new_ema = min(current_ema + increment, 1.0)  # Cap at 1.0
            else:
                # Decrement for failure
                new_ema = max(current_ema - 0.02, 0.0)  # Floor at 0.0
            
            # Update specialist EMA
            self.db_manager.execute_query(
                """
                UPDATE specialist_registry 
                SET ema_score = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_ema, specialist_id)
            )
            
            # Record in EMA history
            self.db_manager.execute_query(
                """
                INSERT INTO ema_history (specialist_id, ema_score)
                VALUES (?, ?)
                """,
                (specialist_id, new_ema)
            )
            
            logger.info(
                f"Updated EMA for specialist {specialist_id}: {current_ema:.3f} -> {new_ema:.3f} "
                f"(quality_factor: {quality_factor:.2f})"
            )
            
        except Exception as e:
            logger.error(f"Failed to update EMA score: {e}")
    
    @staticmethod
    def _make_schema_matcher(schema: Dict) -> Callable[[Dict], bool]:
        """Create a matcher function that checks root QID via P31/P279.
        
        Only exact root QID matches are considered (no property-based
        matching to avoid false positives).
        
        Args:
            schema: WIKIDATA_SCHEMAS entry with root and props
            
        Returns:
            Callable that takes an entity dict and returns bool
        """
        root_qid = schema['root']
        
        def matches_schema(entity: Dict) -> bool:
            claims = entity.get('claims', {})
            
            # Check P31 (instance of) for exact root QID match
            if 'P31' in claims:
                for claim in claims['P31']:
                    try:
                        mainsnak = claim.get('mainsnak', {})
                        datavalue = mainsnak.get('datavalue', {})
                        qid = datavalue.get('value', {}).get('id', '')
                        if qid == root_qid:
                            return True
                    except (KeyError, TypeError):
                        continue
            
            # Check P279 (subclass of) for exact root QID match
            if 'P279' in claims:
                for claim in claims['P279']:
                    try:
                        mainsnak = claim.get('mainsnak', {})
                        datavalue = mainsnak.get('datavalue', {})
                        qid = datavalue.get('value', {}).get('id', '')
                        if qid == root_qid:
                            return True
                    except (KeyError, TypeError):
                        continue
            
            return False
        
        return matches_schema
    
    async def run_phase_a(self, specialist: Dict) -> bool:
        """Run Phase A: Wikidata extraction for specialist.
        
        Args:
            specialist: Specialist dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        specialist_id = specialist['id']
        domain = specialist['domain']
        schema = WIKIDATA_SCHEMAS.get(domain)
        
        if not schema:
            logger.error(f"No schema found for domain: {domain}")
            return False
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE A: Wikidata Extraction for {domain}")
        logger.info(f"{'=' * 60}")
        
        # Initialize tracking record
        try:
            self.db_manager.execute_query(
                """
                INSERT OR REPLACE INTO cartridge_offsets 
                (qid, cartridge_name, specialist_id, status)
                VALUES (?, ?, ?, ?)
                """,
                (f"specialist_{specialist_id}", f"cartridge_{schema['root']}.json.gz", specialist_id, "PROCESSING: 0%")
            )
        except Exception as e:
            logger.error(f"Failed to initialize tracking: {e}")
        
        # Use shared WikidataStreamingExtractor with schema matcher
        matcher = self._make_schema_matcher(schema)
        extractor = WikidataStreamingExtractor(
            input_path=WIKIDATA_DUMP_PATH,
            output_dir=TARGET_OUTPUT_DIR,
            domain=domain,
            expert_id=specialist_id,
            custom_matcher=matcher,
        )
        
        # Extract with timeout (support sample_size for testing)
        success = extractor.extract_with_timeout(
            timeout_hours=WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
            sample_size=self._sample_size,
        )
        
        # Track metrics
        self.metrics.record_phase_a(
            specialist_id=specialist_id,
            domain=domain,
            success=success,
            entities_processed=extractor.entities_processed,
            entities_matched=extractor.entities_matched,
        )
        
        # Update final status
        if success:
            self.db_manager.execute_query(
                """
                UPDATE cartridge_offsets 
                SET status = 'COMPLETED'
                WHERE specialist_id = ?
                """,
                (specialist_id,)
            )
            logger.info(f"PHASE A completed successfully for {domain}")
        else:
            self.handle_extraction_failure(specialist_id)
            logger.warning(f"PHASE A failed for {domain}. Fallback activated.")
        
        return success
    
    async def run_phase_b(self, specialist: Dict) -> bool:
        """Run Phase B: Web scraping + LLM distillation for specialist.
        
        Args:
            specialist: Specialist dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        specialist_id = specialist['id']
        domain = specialist['domain']
        model = specialist['model']
        
        logger.info(f"\n{'=' * 60}")
        logger.info(f"PHASE B: Web Scraping + Distillation for {domain}")
        logger.info(f"{'=' * 60}")
        
        try:
            # Load specialist model using LLMRunner
            model_loaded = await self.llm_runner.ensure_model_loaded(model)
            if not model_loaded:
                logger.error(f"Failed to load model: {model}")
                return False
            
            # Update specialist status
            self.db_manager.execute_query(
                """
                UPDATE specialist_registry 
                SET status = 'ACTIVE'
                WHERE id = ?
                """,
                (specialist_id,)
            )
            
            # Generate search queries based on domain
            search_queries = [
                f"{domain} latest research",
                f"{domain} best practices 2026",
                f"{domain} state of the art",
            ]
            
            total_contents = 0
            for query in search_queries:
                    try:
                        # Direct await since search_and_extract is async
                        results = await self.web_scraper.search_and_extract(
                            query=query,
                            max_results=3,
                        )
                        total_contents += len(results)
                        
                        # If a model is loaded, distill each extracted content
                        if results:
                            for content in results[:2]:  # Distill top 2 per query
                                try:
                                    distill_prompt = (
                                        f"Summarize the following {domain} knowledge in 3 bullet points:\n\n"
                                        f"{content.get('content', '')[:2000]}"
                                    )
                                    distillation = await self.llm_runner.query_llm(
                                        model_name=model,
                                        prompt=distill_prompt,
                                    )
                                    logger.debug(f"Distillation result: {distillation[:100]}...")
                                except Exception as distill_err:
                                    logger.warning(f"Distillation failed: {distill_err}")
                        
                    except (RateLimitError, WebScraperError) as e:
                        logger.warning(f"Search failed for '{query}': {e}")
                        continue
            
            # Track metrics
            self.metrics.record_phase_b(
                specialist_id=specialist_id,
                domain=domain,
                success=total_contents > 0,
                contents_count=total_contents,
            )
            
            # Update specialist status
            self.db_manager.execute_query(
                """
                UPDATE specialist_registry 
                SET status = 'IDLE'
                WHERE id = ?
                """,
                (specialist_id,)
            )
            
            logger.info(f"PHASE B completed for {domain}: {total_contents} contents extracted")
            return total_contents > 0
            
        except Exception as e:
            logger.error(f"Phase B failed for {domain}: {e}")
            return False
    
    async def run_pipeline(self, sample_size: Optional[int] = None) -> None:
        """Run the complete pipeline for all specialists.
        
        Args:
            sample_size: Optional limit for testing (None = full processing)
        """
        logger.info("=" * 80)
        logger.info("CORAL THOUGHT ORCHESTRATOR - PIPELINE START")
        logger.info("=" * 80 + "\n")
        
        # Validate paths
        if not validate_paths():
            logger.critical("Path validation failed. Aborting.")
            return
        
        # Initialize specialists
        if not self.initialize_specialists():
            logger.critical("Failed to initialize specialists. Aborting.")
            return
        
        # Fetch specialists
        specialists = self.get_specialists()
        
        if not specialists:
            logger.warning("No specialists found. Aborting.")
            return
        
        logger.info(f"Processing {len(specialists)} specialists...\n")
        
        try:
            # Process each specialist
            for specialist in specialists:
                specialist_id = specialist['id']
                domain = specialist['domain']
                
                logger.info(f"\n{'=' * 80}")
                logger.info(f"Processing Specialist: {domain} (ID: {specialist_id})")
                logger.info(f"Model: {specialist['model']}")
                logger.info(f"Current EMA: {specialist['ema_score']:.3f}")
                logger.info(f"{'=' * 80}")
                
                try:
                    # Phase A: Wikidata Extraction
                    phase_a_success = await self.run_phase_a(specialist)
                    
                    # Phase B: Web Scraping (always run for delta updates)
                    phase_b_success = await self.run_phase_b(specialist)
                    
                    # Update EMA score with dynamic scoring
                    overall_success = phase_a_success or phase_b_success
                    content_length = 500 if overall_success else 0
                    trust_score = 70 if overall_success else 50
                    self.update_ema_score(specialist_id, overall_success, content_length, trust_score)
                    
                except Exception as e:
                    logger.error(f"Error processing specialist {domain}: {e}")
                    self.update_ema_score(specialist_id, False)
        
        finally:
            # Cleanup - ensure VRAM is freed even on error
            await self.llm_runner.cleanup()
            self.web_scraper.cleanup()
        
        # Print final metrics summary
        self.metrics.print_summary()
        
        logger.info("\n" + "=" * 80)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 80)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main(sample_size: Optional[int] = None):
    """Main entry point for the orchestrator.
    
    Args:
        sample_size: Optional limit for testing (None = full processing)
    """
    controller = PipelineController(sample_size=sample_size)
    await controller.run_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
