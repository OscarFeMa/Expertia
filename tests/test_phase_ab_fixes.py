"""Tests for Phase A+B fixes — Critical and High priority bug fixes."""
import pytest
import time
import threading
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# A1: Imports fix — ClassHierarchyCache, BatchWikidataExtractor, CHECKPOINT_INTERVAL
# ═══════════════════════════════════════════════════════════════════════════════

class TestA1_ImportsFix:
    """A1: Verify all required imports exist in orchestrator.py."""

    def test_dissect_wikidata_imports_exist(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "from dissect_wikidata import ClassHierarchyCache, BatchWikidataExtractor, CHECKPOINT_INTERVAL" in content

    def test_class_hierarchy_cache_importable(self):
        from dissect_wikidata import ClassHierarchyCache
        assert ClassHierarchyCache is not None

    def test_batch_wikidata_extractor_importable(self):
        from dissect_wikidata import BatchWikidataExtractor
        assert BatchWikidataExtractor is not None

    def test_checkpoint_interval_importable(self):
        from dissect_wikidata import CHECKPOINT_INTERVAL
        assert isinstance(CHECKPOINT_INTERVAL, int)
        assert CHECKPOINT_INTERVAL > 0

    def test_no_gzip_import(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "import gzip" not in content

    def test_no_ijson_import(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "import ijson" not in content

    def test_no_decimal_import(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "from decimal import Decimal" not in content

    def test_no_contextmanager_import(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "from contextlib import contextmanager" not in content

    def test_threading_imported(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "import threading" in content


# ═══════════════════════════════════════════════════════════════════════════════
# A2: Auth warning — log warning when no API key
# ═══════════════════════════════════════════════════════════════════════════════

class TestA2_AuthWarning:
    """A2: Verify auth warning exists when no API key is set."""

    def test_auth_warning_in_source(self):
        from pathlib import Path
        router_path = Path(__file__).parent.parent / "api_router.py"
        content = router_path.read_text(encoding="utf-8")
        assert "EXPERTIA_API_KEY not set" in content

    def test_auth_still_works_with_key(self):
        import api_router
        original = api_router.EXPERTIA_API_KEY
        try:
            api_router.EXPERTIA_API_KEY = "test-key-123"
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                api_router.verify_api_key("wrong-key")
            assert exc_info.value.status_code == 403
        finally:
            api_router.EXPERTIA_API_KEY = original

    def test_auth_passes_when_no_key_set(self):
        import api_router
        original = api_router.EXPERTIA_API_KEY
        try:
            api_router.EXPERTIA_API_KEY = ""
            result = api_router.verify_api_key(None)
            assert result is None
        finally:
            api_router.EXPERTIA_API_KEY = original

    def test_auth_passes_with_correct_key(self):
        import api_router
        original = api_router.EXPERTIA_API_KEY
        try:
            api_router.EXPERTIA_API_KEY = "correct-key"
            result = api_router.verify_api_key("correct-key")
            assert result == "correct-key"
        finally:
            api_router.EXPERTIA_API_KEY = original


# ═══════════════════════════════════════════════════════════════════════════════
# A3: CORS restriction — localhost only
# ═══════════════════════════════════════════════════════════════════════════════

class TestA3_CORSRestriction:
    """A3: CORS must be restricted to localhost origins only."""

    def test_no_wildcard_origin(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert 'allow_origins=["*"]' not in content

    def test_localhost_origin_present(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert "http://localhost:8011" in content

    def test_127_0_0_1_origin_present(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert "http://127.0.0.1:8011" in content

    def test_methods_restricted(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert 'allow_methods=["GET", "POST"]' in content

    def test_no_wildcard_methods(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert 'allow_methods=["*"]' not in content


# ═══════════════════════════════════════════════════════════════════════════════
# A4: SQL injection — whitelist tables in get_table_count
# ═══════════════════════════════════════════════════════════════════════════════

class TestA4_SQLInjectionFix:
    """A4: get_table_count must whitelist table names."""

    def test_valid_table_works(self):
        from database.db_manager import DatabaseManager
        db = DatabaseManager(":memory:")
        count = db.get_table_count("specialist_registry")
        assert isinstance(count, int)

    def test_invalid_table_returns_zero(self):
        from database.db_manager import DatabaseManager
        db = DatabaseManager(":memory:")
        count = db.get_table_count("evil_table; DROP TABLE specialist_registry; --")
        assert count == 0

    def test_empty_string_returns_zero(self):
        from database.db_manager import DatabaseManager
        db = DatabaseManager(":memory:")
        count = db.get_table_count("")
        assert count == 0

    def test_all_valid_tables_in_whitelist(self):
        from database.db_manager import DatabaseManager
        db = DatabaseManager(":memory:")
        valid_tables = ["specialist_registry", "knowledge_packages", "cartridge_offsets",
                        "super_experts", "super_expert_members", "wikidata_sync_log"]
        for table in valid_tables:
            count = db.get_table_count(table)
            assert isinstance(count, int), f"Table {table} should be valid"

    def test_injection_with_union(self):
        from database.db_manager import DatabaseManager
        db = DatabaseManager(":memory:")
        count = db.get_table_count("specialist_registry UNION SELECT password FROM users")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# A5: Memory leak — _p279_cache eviction
# ═══════════════════════════════════════════════════════════════════════════════

class TestA5_P279CacheEviction:
    """A5: _p279_cache must be evicted when exceeding 100K entries."""

    def test_cache_eviction_code_exists(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "len(cache) > 100000" in content

    def test_cache_keeps_last_50k(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "list(cache.items())[-50000:]" in content


# ═══════════════════════════════════════════════════════════════════════════════
# A6: Signal handler — threading.Event instead of asyncio.Event
# ═══════════════════════════════════════════════════════════════════════════════

class TestA6_SignalHandlerThreadSafe:
    """A6: Signal handler must use threading.Event, not asyncio.Event."""

    def test_uses_threading_event(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "_shutdown_event = threading.Event()" in content

    def test_no_asyncio_event_for_shutdown(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "_shutdown_event = asyncio.Event()" not in content

    def test_signal_handler_thread_safe(self):
        import orchestrator
        event = orchestrator._shutdown_event
        assert isinstance(event, type(threading.Event()))
        # threading.Event is thread-safe — set from signal handler works
        event.clear()
        event.set()
        assert event.is_set()

    def test_signal_handler_no_inner_import(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        # The signal handler should NOT have "import threading" inside it
        lines = content.split('\n')
        in_handler = False
        for line in lines:
            if 'def _signal_handler' in line:
                in_handler = True
            elif in_handler and line.strip() and not line.strip().startswith('#') and not line.strip().startswith('def '):
                if 'import threading' in line:
                    pytest.fail("Signal handler should not have inner 'import threading'")
            elif in_handler and line.strip().startswith('def ') and '_signal_handler' not in line:
                break


# ═══════════════════════════════════════════════════════════════════════════════
# B1: start_all.bat — cd /d fix
# ═══════════════════════════════════════════════════════════════════════════════

class TestB1_StartAllBat:
    """B1: start_all.bat must change to script directory first."""

    def test_has_cd_d(self):
        bat_path = Path(__file__).parent.parent / "start_all.bat"
        content = bat_path.read_text(encoding="utf-8")
        assert 'cd /d' in content

    def test_has_dp0(self):
        bat_path = Path(__file__).parent.parent / "start_all.bat"
        content = bat_path.read_text(encoding="utf-8")
        assert '%~dp0' in content

    def test_timeout_5_seconds(self):
        bat_path = Path(__file__).parent.parent / "start_all.bat"
        content = bat_path.read_text(encoding="utf-8")
        assert "timeout /t 5" in content

    def test_uses_pythonw(self):
        bat_path = Path(__file__).parent.parent / "start_all.bat"
        content = bat_path.read_text(encoding="utf-8")
        assert "pythonw.exe" in content


# ═══════════════════════════════════════════════════════════════════════════════
# B2: Nurture backoff — sleep between retries
# ═══════════════════════════════════════════════════════════════════════════════

class TestB2_NurtureBackoff:
    """B2: Nurture mode must sleep 30s when model unavailable."""

    def test_backoff_sleep_exists(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "await asyncio.sleep(30)" in content

    def test_backoff_after_model_skip(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        # Find the backoff near the "Model ... unavailable" message
        idx_model_unavail = content.find("Model {current_target['model']} unavailable")
        idx_sleep = content.find("await asyncio.sleep(30)", idx_model_unavail)
        assert idx_sleep > idx_model_unavail, "sleep(30) must come after model unavailable message"


# ═══════════════════════════════════════════════════════════════════════════════
# B3: Feed quality — realistic values
# ═══════════════════════════════════════════════════════════════════════════════

class TestB3_FeedQuality:
    """B3: Feed mode must use realistic quality values, not 100/100."""

    def test_trust_score_not_100(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        # Find the feed mode EMA update section
        feed_section = content[content.find("Feed mode: update EMA"):]
        assert "trust_score=95" in feed_section or "trust_score=100" not in feed_section

    def test_trust_score_is_95(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        feed_section = content[content.find("Feed mode: update EMA"):]
        assert "trust_score=95" in feed_section


# ═══════════════════════════════════════════════════════════════════════════════
# B4: Rate limiting /kill — max 3 per 10 min
# ═══════════════════════════════════════════════════════════════════════════════

class TestB4_KillRateLimit:
    """B4: /kill endpoint must be rate-limited to 3 per 10 minutes."""

    def test_rate_limiter_class_exists(self):
        from api_router import KillRateLimiter
        assert KillRateLimiter is not None

    def test_rate_limiter_allows_first_3(self):
        from api_router import KillRateLimiter
        limiter = KillRateLimiter(max_calls=3, window_seconds=600)
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is True
        assert limiter.is_allowed() is True

    def test_rate_limiter_blocks_fourth(self):
        from api_router import KillRateLimiter
        limiter = KillRateLimiter(max_calls=3, window_seconds=600)
        for _ in range(3):
            limiter.is_allowed()
        assert limiter.is_allowed() is False

    def test_rate_limiter_allows_after_window(self):
        from api_router import KillRateLimiter
        limiter = KillRateLimiter(max_calls=3, window_seconds=0)  # window=0 means always expire
        for _ in range(3):
            limiter.is_allowed()
        assert limiter.is_allowed() is True

    def test_kill_limiter_instance_exists(self):
        import api_router
        assert hasattr(api_router, '_kill_limiter')
        assert isinstance(api_router._kill_limiter, api_router.KillRateLimiter)

    def test_kill_returns_429_when_limited(self):
        import api_router
        original_limiter = api_router._kill_limiter
        try:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed.return_value = False
            api_router._kill_limiter = mock_limiter
            from httpx import ASGITransport, AsyncClient
            import asyncio
            from query_api import app
            transport = ASGITransport(app=app)
            async def run_test():
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post("/api/kill")
                    return resp
            resp = asyncio.run(run_test())
            assert resp.status_code == 429
        finally:
            api_router._kill_limiter = original_limiter


# ═══════════════════════════════════════════════════════════════════════════════
# B5: TOCTOU race — atomic pipeline start
# ═══════════════════════════════════════════════════════════════════════════════

class TestB5_TOCTOUFix:
    """B5: Pipeline start must be atomic (check-and-act in same lock)."""

    def test_pipeline_start_entirely_in_lock(self):
        from pathlib import Path
        router_path = Path(__file__).parent.parent / "api_router.py"
        content = router_path.read_text(encoding="utf-8")
        # Find the start_pipeline function
        start_idx = content.find("def start_pipeline")
        # Find the next function definition
        next_func = content.find("\ndef ", start_idx + 1)
        start_func = content[start_idx:next_func]
        # The entire function body should be inside one `with _pipeline_lock:` block
        lock_enter = start_func.find("with _pipeline_lock:")
        assert lock_enter > 0, "start_pipeline must use _pipeline_lock"
        # Check that Popen is inside the lock (after lock_enter)
        popen_in_lock = start_func.find("subprocess.Popen", lock_enter)
        assert popen_in_lock > 0, "Popen must be inside _pipeline_lock"


# ═══════════════════════════════════════════════════════════════════════════════
# B7: Chinese chars removed
# ═══════════════════════════════════════════════════════════════════════════════

class TestB7_NoChineseChars:
    """B7: Query strings must not contain Chinese characters."""

    def test_no_chinese_in_queries(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        import re
        chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        matches = chinese_pattern.findall(content)
        assert len(matches) == 0, f"Found Chinese characters in orchestrator.py: {matches}"

    def test_case_studies_replaces_chinese(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "case studies" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Full import chain verification
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration_ImportChain:
    """Verify the full import chain works without errors."""

    def test_orchestrator_imports_successfully(self):
        import orchestrator
        assert hasattr(orchestrator, 'PipelineController')
        assert hasattr(orchestrator, 'ClassHierarchyCache')
        assert hasattr(orchestrator, 'BatchWikidataExtractor')
        assert hasattr(orchestrator, 'CHECKPOINT_INTERVAL')

    def test_api_router_imports_successfully(self):
        import api_router
        assert hasattr(api_router, 'router')
        assert hasattr(api_router, 'verify_api_key')
        assert hasattr(api_router, 'KillRateLimiter')

    def test_db_manager_imports_successfully(self):
        import database.db_manager
        assert hasattr(database.db_manager, 'DatabaseManager')

    def test_query_api_imports_successfully(self):
        import query_api
        assert hasattr(query_api, 'app')
