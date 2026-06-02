"""Tests for Phase S2 fixes — Pipeline integrity."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestS21_BronzePenalty:
    """S2.1: Bronze penalty must be LESS punishing than None (0.97 > 0.965)."""

    def test_bronze_penalty_less_than_none(self):
        from orchestrator import FAILURE_PENALTIES, TIER_NONE, TIER_BRONZE
        assert FAILURE_PENALTIES[TIER_BRONZE] > FAILURE_PENALTIES[TIER_NONE], \
            f"Bronze ({FAILURE_PENALTIES[TIER_BRONZE]}) should penalize LESS than None ({FAILURE_PENALTIES[TIER_NONE]})"

    def test_bronze_penalty_value(self):
        from orchestrator import FAILURE_PENALTIES, TIER_BRONZE
        assert FAILURE_PENALTIES[TIER_BRONZE] == 0.97

    def test_all_penalties_ordered(self):
        from orchestrator import FAILURE_PENALTIES, TIER_NONE, TIER_BRONZE, TIER_SILVER, TIER_GOLD, TIER_LEGEND
        # Higher value = less punishment. None should be most punishing, Legend least.
        assert FAILURE_PENALTIES[TIER_NONE] < FAILURE_PENALTIES[TIER_BRONZE]
        assert FAILURE_PENALTIES[TIER_BRONZE] < FAILURE_PENALTIES[TIER_SILVER]
        assert FAILURE_PENALTIES[TIER_SILVER] <= FAILURE_PENALTIES[TIER_GOLD]


class TestS22_ComputeTierException:
    """S2.2: _compute_tier must return TIER_NONE on exception, not current_tier."""

    def test_exception_returns_tier_none(self):
        from orchestrator import PipelineController, TIER_NONE
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            c.db_manager = MagicMock()
            c.db_manager.execute_query = MagicMock(side_effect=Exception("DB error"))
            result = c._compute_tier(1, 0.95, 2)
            assert result == TIER_NONE, f"Expected TIER_NONE on exception, got {result}"


class TestS23_DuplicateRoute:
    """S2.3: /wikidata/feed must not appear twice in api_router."""

    def test_no_duplicate_feed_route(self):
        import ast
        from pathlib import Path
        router_path = Path(__file__).parent.parent / "api_router.py"
        content = router_path.read_text(encoding="utf-8")
        feed_decorators = content.count('@router.post("/wikidata/feed"')
        assert feed_decorators == 1, f"Expected 1 /wikidata/feed route, found {feed_decorators}"


class TestS24_StaleActiveReset:
    """S2.4: API startup must reset stale ACTIVE statuses."""

    def test_lifespan_resets_active(self):
        from pathlib import Path
        api_path = Path(__file__).parent.parent / "query_api.py"
        content = api_path.read_text(encoding="utf-8")
        assert "UPDATE specialist_registry SET status = 'IDLE' WHERE status = 'ACTIVE'" in content


class TestS25_QualityGate:
    """S2.5: Phase B must reject distillations shorter than 10 chars."""

    def test_quality_gate_exists(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "len(dist.strip()) < 10" in content

    @pytest.mark.asyncio
    async def test_short_distill_rejected(self):
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner") as mock_llm, \
             patch("orchestrator.ModernWebScraper") as mock_scraper, \
             patch("orchestrator.MetricsCollector") as mock_metrics, \
             patch("orchestrator.KnowledgeIngestor") as mock_ingestor:
            from orchestrator import PipelineController
            c = PipelineController()
            c.llm_runner = AsyncMock()
            c.web_scraper = AsyncMock()
            c.ingestor = MagicMock()
            c.metrics = MagicMock()
            c.db_manager = MagicMock()
            c._label_cache = {}
            c.llm_runner.ensure_model_loaded = AsyncMock(return_value=True)
            c.llm_runner.query_llm = AsyncMock(return_value="short")
            c.web_scraper.search_and_extract = AsyncMock(return_value=[
                {"content": "test content", "trust_score": 50, "url": "http://test.com"},
            ])
            specialist = {"id": 1, "domain": "Physics", "model": "phi4-mini:3.8b"}
            result = await c.run_phase_b(specialist, cycle=1)
            assert result["packages_saved"] == 0, "Short distillation should be rejected"

    @pytest.mark.asyncio
    async def test_good_distill_accepted(self):
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner") as mock_llm, \
             patch("orchestrator.ModernWebScraper") as mock_scraper, \
             patch("orchestrator.MetricsCollector") as mock_metrics, \
             patch("orchestrator.KnowledgeIngestor") as mock_ingestor:
            from orchestrator import PipelineController
            c = PipelineController()
            c.llm_runner = AsyncMock()
            c.web_scraper = AsyncMock()
            c.ingestor = MagicMock()
            c.metrics = MagicMock()
            c.db_manager = MagicMock()
            c._label_cache = {}
            c.llm_runner.ensure_model_loaded = AsyncMock(return_value=True)
            c.llm_runner.query_llm = AsyncMock(return_value="This is a detailed distillation of physics knowledge covering quantum mechanics and relativity.")
            c.web_scraper.search_and_extract = AsyncMock(return_value=[
                {"content": "This is a detailed article about physics covering quantum mechanics, thermodynamics, and relativity. " * 5, "trust_score": 80, "url": "http://test.com"},
            ])
            specialist = {"id": 1, "domain": "Physics", "model": "phi4-mini:3.8b"}
            result = await c.run_phase_b(specialist, cycle=1)
            assert result["packages_saved"] > 0, "Good distillation should be accepted"
