"""Tests for orchestrator.py — Phase B logic with mocked dependencies."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def controller():
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
        return c


class TestRunPhaseB:
    @pytest.mark.asyncio
    async def test_no_model_loaded_returns_default(self, controller):
        controller.llm_runner.ensure_model_loaded = AsyncMock(return_value=False)
        specialist = {"id": 1, "domain": "TestDomain", "model": "test-model"}
        result = await controller.run_phase_b(specialist, cycle=1)
        assert result["success"] is False
        assert result["contents_count"] == 0

    @pytest.mark.asyncio
    async def test_model_loaded_scrapes_and_distills(self, controller):
        controller.llm_runner.ensure_model_loaded = AsyncMock(return_value=True)
        controller.llm_runner.query_llm = AsyncMock(return_value="Distilled knowledge point")
        controller.web_scraper.search_and_extract = AsyncMock(return_value=[
            {"content": "This is a detailed article about physics covering quantum mechanics, thermodynamics, and relativity. " * 5, "trust_score": 80, "url": "http://test.com/article"},
        ])
        controller.db_manager.execute_query = MagicMock()

        specialist = {"id": 1, "domain": "Physics", "model": "phi4-mini:3.8b"}
        result = await controller.run_phase_b(specialist, cycle=1)
        assert result["success"] is True
        assert result["contents_count"] > 0
        assert result["packages_saved"] > 0
        assert result["avg_trust"] > 0

    @pytest.mark.asyncio
    async def test_scraper_rate_limit_graceful(self, controller):
        from web_scraper import RateLimitError
        controller.llm_runner.ensure_model_loaded = AsyncMock(return_value=True)
        controller.web_scraper.search_and_extract = AsyncMock(side_effect=RateLimitError("Rate limited"))
        controller.db_manager.execute_query = MagicMock()

        specialist = {"id": 2, "domain": "Chemistry", "model": "phi4-mini:3.8b"}
        result = await controller.run_phase_b(specialist, cycle=1)
        assert result["success"] is False
        assert result["contents_count"] == 0

    @pytest.mark.asyncio
    async def test_sets_and_clears_status(self, controller):
        controller.llm_runner.ensure_model_loaded = AsyncMock(return_value=True)
        controller.llm_runner.query_llm = AsyncMock(return_value="test")
        controller.web_scraper.search_and_extract = AsyncMock(return_value=[
            {"content": "test", "trust_score": 50, "url": "http://test.com"},
        ])
        status_calls = []
        controller.db_manager.execute_query = MagicMock(side_effect=lambda q, p=None: status_calls.append((q, p)))

        specialist = {"id": 3, "domain": "Math", "model": "phi4-mini:3.8b"}
        await controller.run_phase_b(specialist, cycle=1)
        status_sets = [c for c in status_calls if c[0] and 'status' in str(c[0])]
        assert any('ACTIVE' in str(s[0]) for s in status_sets)
        assert any('IDLE' in str(s[0]) for s in status_sets)
