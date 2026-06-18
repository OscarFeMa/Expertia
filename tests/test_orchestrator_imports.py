"""Test that orchestrator modules can be imported without errors."""

import sys
import os
import traceback
import io

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

# Capture all output to a buffer
_output_buf = io.StringIO()


def _log(msg):
    """Print to both stdout and our buffer."""
    print(msg)
    _output_buf.write(msg + "\n")


def test_imports():
    """Test that all key modules can be imported."""
    # Test config
    _log("  importing config.settings...")
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
        SUBSPECIALIST_THRESHOLD,
        WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
        REPORTING_INTERVAL_SECONDS,
        COOLDOWN_SECONDS,
    )
    _log("  config.settings OK")
    assert DATABASE_PATH is not None
    assert WIKIDATA_DUMP_PATH is not None
    
    # Test database manager
    _log("  importing database.db_manager...")
    from database.db_manager import get_db_manager, reset_db_manager
    db_manager = get_db_manager()
    assert db_manager is not None
    reset_db_manager()
    _log("  database.db_manager OK")
    
    # Test LLM manager
    _log("  importing llm_manager...")
    from llm_manager import LLMRunner, get_llm_runner
    llm_runner = LLMRunner()
    assert llm_runner is not None
    _log("  llm_manager OK")
    
    # Test web scraper
    _log("  importing web_scraper...")
    from web_scraper import ModernWebScraper, WebScraperError, RateLimitError, ScraperTimeoutError
    scraper = ModernWebScraper()
    assert scraper is not None
    _log("  web_scraper OK")
    
    # Test metrics
    _log("  importing metrics...")
    from metrics import MetricsCollector
    metrics = MetricsCollector()
    assert metrics is not None
    _log("  metrics OK")
    
    # Test orchestrator (just import, don't run)
    _log("  importing orchestrator...")
    from orchestrator import PipelineController, validate_paths, WIKIDATA_SCHEMAS, SPECIALIST_REGISTRY
    assert validate_paths is not None
    assert WIKIDATA_SCHEMAS is not None
    assert len(WIKIDATA_SCHEMAS) == 18
    assert SPECIALIST_REGISTRY is not None
    assert len(SPECIALIST_REGISTRY) == 18
    _log("  orchestrator OK")
    
    # Test dissect_wikidata
    _log("  importing dissect_wikidata...")
    from dissect_wikidata import WikidataStreamingExtractor, TAG_TO_QID_MAP
    assert WikidataStreamingExtractor is not None
    assert TAG_TO_QID_MAP is not None
    assert len(TAG_TO_QID_MAP) > 0
    _log("  dissect_wikidata OK")
    
    _log("\nOK All imports successful!")


if __name__ == "__main__":
    _log(f"Python {sys.version}")
    _log(f"Platform: {sys.platform}")
    _log(f"CWD: {os.getcwd()}")
    _log(f"Script: {__file__}")
    _log(f"Path: {sys.path}")
    try:
        test_imports()
    except Exception:
        _log("\nFAILED with traceback:")
        traceback.print_exc(file=_output_buf)
        _output_buf.seek(0)
        print("\nFull output:\n" + _output_buf.read())
        # Write to GITHUB_STEP_SUMMARY if available
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            try:
                with open(summary_path, "a") as f:
                    f.write("### Test imports failed\n")
                    f.write("```\n")
                    _output_buf.seek(0)
                    f.write(_output_buf.read())
                    f.write("\n```\n")
            except Exception as e:
                print(f"Failed to write to GITHUB_STEP_SUMMARY: {e}")
        sys.exit(1)
    else:
        _output_buf.seek(0)
        print("\nFull output:\n" + _output_buf.read())