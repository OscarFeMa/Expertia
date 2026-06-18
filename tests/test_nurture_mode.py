"""Tests for new Nurture Mode — Maintenance + Growth (3 pillars)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestNurturePriorityScoring:
    """Pillar 1: Priority scoring based on EMA, weighted_success/fail, staleness, packages."""

    def test_constants_exist(self):
        from orchestrator import (
            NURTURE_W_EMA, NURTURE_W_FAIL,
            NURTURE_W_STALENESS, NURTURE_W_PACKAGES, NURTURE_PACKAGE_TARGET
        )
        assert NURTURE_W_EMA == 10.0
        assert NURTURE_W_FAIL == 8.0
        assert NURTURE_W_STALENESS == 0.5
        assert NURTURE_W_PACKAGES == 3.0
        assert NURTURE_PACKAGE_TARGET == 500

    def test_no_nurture_target_ema(self):
        """NURTURE_TARGET_EMA should no longer exist."""
        import orchestrator
        assert not hasattr(orchestrator, 'NURTURE_TARGET_EMA')

    def test_compute_priority_low_ema_high_score(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            spec = {
                'ema_score': 0.5,
                'weighted_success': 500.0,
                'weighted_fail': 0.0,
                'packages_absorbed': 500,
                'updated_at': '2026-06-01 12:00:00',
            }
            score = c._compute_nurture_priority(spec)
            assert score > 0, f"Score should be positive, got {score}"

    def test_compute_priority_high_ema_low_score(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            spec = {
                'ema_score': 0.99,
                'weighted_success': 1000.0,
                'weighted_fail': 0.0,
                'packages_absorbed': 1000,
                'updated_at': '2026-06-02 20:00:00',
            }
            score = c._compute_nurture_priority(spec)
            assert score >= 0, f"Score should be non-negative, got {score}"

    def test_low_ema_beats_high_ema(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            base = {
                'weighted_success': 500.0,
                'weighted_fail': 0.0,
                'packages_absorbed': 500,
                'updated_at': '2026-06-02 20:00:00',
            }
            low_ema = c._compute_nurture_priority({**base, 'ema_score': 0.5})
            high_ema = c._compute_nurture_priority({**base, 'ema_score': 0.99})
            assert low_ema > high_ema, f"Low EMA ({low_ema}) should score higher than high EMA ({high_ema})"

    def test_high_fail_rate_beats_low(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            base = {
                'ema_score': 0.95,
                'packages_absorbed': 500,
                'updated_at': '2026-06-02 20:00:00',
            }
            high_fail = c._compute_nurture_priority({**base, 'weighted_success': 500.0, 'weighted_fail': 500.0})
            low_fail = c._compute_nurture_priority({**base, 'weighted_success': 500.0, 'weighted_fail': 0.0})
            assert high_fail > low_fail

    def test_few_packages_beats_many(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            base = {
                'ema_score': 0.95,
                'weighted_success': 500.0,
                'weighted_fail': 0.0,
                'updated_at': '2026-06-02 20:00:00',
            }
            few = c._compute_nurture_priority({**base, 'packages_absorbed': 10})
            many = c._compute_nurture_priority({**base, 'packages_absorbed': 2000})
            assert few > many

    def test_stale_update_beats_fresh(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            base = {
                'ema_score': 0.95,
                'weighted_success': 500.0,
                'weighted_fail': 0.0,
                'packages_absorbed': 500,
            }
            stale = c._compute_nurture_priority({**base, 'updated_at': '2026-05-20 12:00:00'})
            fresh = c._compute_nurture_priority({**base, 'updated_at': '2026-06-02 20:00:00'})
            assert stale > fresh

    def test_missing_updated_at_defaults_to_7_days(self):
        from orchestrator import PipelineController
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            c = PipelineController()
            spec = {
                'ema_score': 0.95,
                'weighted_success': 500.0,
                'weighted_fail': 0.0,
                'packages_absorbed': 500,
                'updated_at': '',
            }
            score = c._compute_nurture_priority(spec)
            assert score > 0


class TestNurtureContinuousRecycling:
    """Pillar 2: Nurture processes ALL specialists, not just those below threshold."""

    def test_nurture_selects_highest_priority_not_lowest_ema(self):
        """Nurture should select by priority score, not just lowest EMA."""
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "_compute_nurture_priority" in content
        assert "scored.sort(key=lambda x: x[0], reverse=True)" in content

    def test_nurture_never_exits_on_all_reached(self):
        """Nurture should NOT have 'all reached threshold → complete' logic."""
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "REACHED EMA >=" not in content
        assert "nurture complete!" not in content.replace("No specialists found — nurture complete!", "")

    def test_nurture_queries_all_parents(self):
        """Nurture should query ALL parent specialists, not filter by EMA threshold."""
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "WHERE parent_id IS NULL ORDER BY domain" in content

    def test_nurture_single_focus_per_iteration(self):
        """Nurture v2: focus on ONE specialist per iteration until tier target reached."""
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "current_target = None" in content
        assert "current_target_tier = TIER_GOLD" in content
        assert "scored = []" in content
        assert "scored.sort(key=lambda x: x[0], reverse=True)" in content

    def test_nurture_logs_target_info(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "score=" in content
        assert "Nurture v2:" in content


class TestNurtureSubSpecialistExpansion:
    """Pillar 3: Auto-expand sub-specialists from unspawned QID expansions."""

    def test_expansion_method_exists(self):
        from orchestrator import PipelineController
        assert hasattr(PipelineController, '_check_subspecialist_expansion')

    def test_expansion_called_in_nurture(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        assert "_check_subspecialist_expansion" in content

    def test_expansion_respects_max_limits(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        idx = content.find("def _check_subspecialist_expansion")
        method_body = content[idx:idx+2000]
        assert "MAX_SUBSPECIALISTS" in method_body
        assert "MAX_CHILDREN_PER_PARENT" in method_body

    def test_expansion_checks_threshold(self):
        from pathlib import Path
        orch_path = Path(__file__).parent.parent / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")
        idx = content.find("def _check_subspecialist_expansion")
        method_body = content[idx:idx+2000]
        assert "SUBSPECIALIST_THRESHOLD" in method_body


class TestNurtureModeIntegration:
    """Integration tests for the full nurture mode."""

    @pytest.mark.asyncio
    async def test_nurture_mode_runs_with_empty_db(self):
        """Nurture should handle empty specialist registry gracefully."""
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner") as mock_llm, \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            from orchestrator import PipelineController
            c = PipelineController()
            c.db_manager = MagicMock()
            c.db_manager.execute_query = MagicMock(return_value=[])
            c.llm_runner = AsyncMock()
            c.web_scraper = AsyncMock()
            c.metrics = MagicMock()
            c.ingestor = MagicMock()
            c._label_cache = {}
            c._update_pipeline_status = MagicMock()
            c._generate_report = AsyncMock()
            c._log_activity = MagicMock()

            import time
            await c._run_nurture_mode(
                all_specialists=[],
                pipeline_start=time.time(),
                min_duration_hours=0,
                max_duration_hours=0,
                max_cycles=1,
                report_interval_minutes=30,
            )
            # With empty DB, nurture should exit gracefully (no crash)
            # _update_pipeline_status is NOT called because there are no specialists
