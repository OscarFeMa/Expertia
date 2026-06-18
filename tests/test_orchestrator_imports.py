"""Test that orchestrator modules can be imported without errors."""

import sys
import os
import traceback
import io

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

_output_buf = io.StringIO()


def _log(msg):
    print(msg, flush=True)
    _output_buf.write(msg + "\n")


def _flush_to_summary(label: str):
    """Write the buffer to GITHUB_STEP_SUMMARY if available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    file_path = "/tmp/ci-test-output.txt"
    _output_buf.seek(0)
    content = _output_buf.read()
    try:
        with open(file_path, "a") as f:
            f.write(f"=== Test imports - {label} ===\n")
            f.write(content)
            f.write("\n")
    except Exception as e:
        _log(f"  [WARN] Failed to write to {file_path}: {e}")
    if summary_path:
        try:
            with open(summary_path, "a") as f:
                f.write(f"### Test imports - {label}\n")
                f.write("```\n")
                f.write(content)
                f.write("\n```\n")
        except Exception as e:
            _log(f"  [WARN] Failed to write to GITHUB_STEP_SUMMARY: {e}")
    # Also emit as GitHub Actions annotation
    for line in content.split("\n"):
        if line.strip():
            print(f"::warning title={label}::{line}", flush=True)


def _try_import(label: str, import_stmt: str, create_obj: bool = False):
    """Try an import and log success/failure. Returns the imported module/obj."""
    _log(f"  [{label}] {import_stmt}")
    try:
        exec(import_stmt, globals())
        obj = eval(import_stmt.split("import ")[-1].split(" as ")[0].split(",")[0].strip())
        _log(f"  [{label}] import OK")
        if create_obj:
            _log(f"  [{label}] creating instance...")
            obj = obj()
            _log(f"  [{label}] instance OK")
        return obj
    except Exception:
        _log(f"  [{label}] FAILED:")
        traceback.print_exc(file=_output_buf)
        _output_buf.seek(0)
        # Write to GITHUB_STEP_SUMMARY on failure
        _flush_to_summary(label)
        raise


def test_imports():
    _try_import("config.settings", "from config.settings import DATABASE_PATH, WIKIDATA_DUMP_PATH")
    assert DATABASE_PATH is not None
    assert WIKIDATA_DUMP_PATH is not None

    _try_import("db_manager", "from database.db_manager import get_db_manager, reset_db_manager")
    db = get_db_manager()
    assert db is not None
    reset_db_manager()

    _try_import("llm_manager", "from llm_manager import LLMRunner, get_llm_runner", create_obj=True)

    _try_import("web_scraper", "from web_scraper import ModernWebScraper, WebScraperError, RateLimitError, ScraperTimeoutError", create_obj=True)

    _try_import("metrics", "from metrics import MetricsCollector", create_obj=True)

    _try_import("orchestrator", "from orchestrator import PipelineController, validate_paths, WIKIDATA_SCHEMAS, SPECIALIST_REGISTRY")
    assert validate_paths is not None
    assert WIKIDATA_SCHEMAS is not None
    assert len(WIKIDATA_SCHEMAS) == 18
    assert SPECIALIST_REGISTRY is not None
    assert len(SPECIALIST_REGISTRY) == 18

    _try_import("dissect_wikidata", "from dissect_wikidata import WikidataStreamingExtractor, TAG_TO_QID_MAP")
    assert WikidataStreamingExtractor is not None
    assert TAG_TO_QID_MAP is not None
    assert len(TAG_TO_QID_MAP) > 0

    _log("\nOK All imports successful!")


if __name__ == "__main__":
    _log(f"Python {sys.version}")
    _log(f"Platform: {sys.platform}")
    _log(f"CWD: {os.getcwd()}")
    _log(f"Script: {__file__}")
    _log(f"Path: {sys.path}")
    try:
        test_imports()
    except SystemExit:
        raise
    except BaseException:
        _log("\nFAILED - traceback captured in step summary")
        _flush_to_summary("FAILURE")
        sys.exit(1)
    _flush_to_summary("SUCCESS")