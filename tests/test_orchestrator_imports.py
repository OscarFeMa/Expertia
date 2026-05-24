"""Test that orchestrator modules can be imported without errors."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')


def test_imports():
    """Test that all key modules can be imported."""
    # Test config
    from config.settings import (
        DATABASE_PATH,
        WIKIDATA_DUMP_PATH,
        WIKIDATA_OUTPUT_DIR,
        OLLAMA_HOST,
        OLLAMA_PORT,
        LLM_TIMEOUT,
        LLM_TEMPERATURE,
        LLM_MAX_TOKENS,
        SEARCH_DELAY_MIN,
        SEARCH_DELAY_MAX,
        MAX_RESULTS_PER_SEARCH,
        SEARCH_TIMEOUT,
        PARSER_TIMEOUT,
        INCLUDE_LINKS,
        USER_AGENTS,
        DISTILLATION_ENABLED,
        DISTILLATION_MODEL,
        SUITABILITY_THRESHOLD,
        MAX_TOTAL_EXPERTS,
        MAX_SPECIALISTS_PER_DOMAIN,
        REPORTING_INTERVAL_SECONDS,
        COOLDOWN_SECONDS,
        WIKIDATA_EXTRACTION_TIMEOUT_HOURS
    )
    assert DATABASE_PATH is not None
    assert WIKIDATA_DUMP_PATH is not None
    
    # Test database manager
    from database.db_manager import get_db_manager, reset_db_manager
    db_manager = get_db_manager()
    assert db_manager is not None
    reset_db_manager()
    
    # Test LLM manager
    from llm_manager import LLMRunner, get_llm_runner
    llm_runner = LLMRunner()
    assert llm_runner is not None
    
    # Test web scraper
    from web_scraper import ModernWebScraper, WebScraperError, RateLimitError, ScraperTimeoutError
    scraper = ModernWebScraper()
    assert scraper is not None
    
    # Test metrics
    from metrics import MetricsCollector
    metrics = MetricsCollector()
    assert metrics is not None
    
    # Test orchestrator (just import, don't run)
    from orchestrator import PipelineController, validate_paths, WIKIDATA_SCHEMAS, SPECIALIST_REGISTRY
    assert validate_paths is not None
    assert WIKIDATA_SCHEMAS is not None
    assert len(WIKIDATA_SCHEMAS) == 15
    assert SPECIALIST_REGISTRY is not None
    assert len(SPECIALIST_REGISTRY) == 15
    
    # Test dissect_wikidata
    from dissect_wikidata import WikidataStreamingExtractor, TAG_TO_QID_MAP
    assert WikidataStreamingExtractor is not None
    assert TAG_TO_QID_MAP is not None
    assert len(TAG_TO_QID_MAP) > 0
    
    print("OK All imports successful!")


if __name__ == "__main__":
    test_imports()