"""Tests for Phase S4 — Infrastructure improvements."""
import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestS41_FTS5Search:
    """S4.1: FTS5 keyword search must be available."""

    def test_fts5_table_exists_in_schema(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "database" / "db_manager.py"
        text = content.read_text(encoding="utf-8")
        assert "knowledge_packages_fts" in text
        assert "CREATE VIRTUAL TABLE" in text

    def test_fts5_triggers_exist(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "database" / "db_manager.py"
        text = content.read_text(encoding="utf-8")
        assert "kp_ai AFTER INSERT" in text
        assert "kp_ad AFTER DELETE" in text
        assert "kp_au AFTER UPDATE" in text

    def test_fts5_migration_exists(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "database" / "db_manager.py"
        text = content.read_text(encoding="utf-8")
        assert "kp_fts5_populate" in text

    def test_fetch_context_uses_fts(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "query_api.py"
        text = content.read_text(encoding="utf-8")
        assert "knowledge_packages_fts MATCH" in text


class TestS42_TokenCounting:
    """S4.2: Token estimation must be available."""

    def test_estimate_tokens_exists(self):
        from orchestrator import estimate_tokens
        assert callable(estimate_tokens)

    def test_estimate_tokens_empty(self):
        from orchestrator import estimate_tokens
        assert estimate_tokens("") == 0
        assert estimate_tokens(None) == 0

    def test_estimate_tokens_short(self):
        from orchestrator import estimate_tokens
        # "hello" = 5 chars, 5//4 = 1
        assert estimate_tokens("hello") == 1

    def test_estimate_tokens_long(self):
        from orchestrator import estimate_tokens
        text = "a" * 1000
        assert estimate_tokens(text) == 250

    def test_tokens_used_in_phase_b(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "estimate_tokens(ct)" in text


class TestS43_FeedEMA:
    """S4.3: Feed EMA must not count toward weighted_success."""

    def test_feed_packages_column_migration(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "database" / "db_manager.py"
        text = content.read_text(encoding="utf-8")
        assert "feed_packages" in text

    def test_update_ema_has_is_feed_param(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "is_feed: bool = False" in text

    def test_feed_does_not_increment_ws(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "if not is_feed:" in text
        assert "ws += quality" in text

    def test_feed_mode_uses_is_feed(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "is_feed=True" in text

    @pytest.mark.asyncio
    async def test_feed_update_no_ws_increment(self):
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            from orchestrator import PipelineController
            c = PipelineController()
            c.db_manager = MagicMock()
            # Mock: first call returns specialist state, rest are updates
            c.db_manager.execute_query = MagicMock(side_effect=[
                [{'ema_score': 0.95, 'weighted_success': 10.0, 'weighted_fail': 1.0, 'tier': 2}],
                None,  # UPDATE specialist_registry
                None,  # INSERT ema_history
                None,  # INSERT cycle_history
            ])
            c.update_ema_score(1, success=True, content_length=10000, trust_score=100,
                               contents_count=10, packages_saved=10, is_feed=True)
            # Check the UPDATE call for specialist_registry
            calls = c.db_manager.execute_query.call_args_list
            update_call = calls[1]  # Second call is the UPDATE
            args = update_call[0][1]
            # ws should be 10.0 (unchanged from initial), not 10.0 + quality
            assert args[1] == 10.0, f"weighted_success should be unchanged (10.0), got {args[1]}"


class TestS44_MinCyclesForTier:
    """S4.4: Tier promotion must require minimum Phase B cycles."""

    def test_min_cycle_constants_exist(self):
        from orchestrator import MIN_CYCLES_FOR_BRONZE, MIN_CYCLES_FOR_SILVER, MIN_CYCLES_FOR_GOLD
        assert MIN_CYCLES_FOR_BRONZE == 3
        assert MIN_CYCLES_FOR_SILVER == 10
        assert MIN_CYCLES_FOR_GOLD == 25

    def test_min_cycles_used_in_tier_computation(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "total_cycles >= MIN_CYCLES_FOR_BRONZE" in text
        assert "total_cycles >= MIN_CYCLES_FOR_SILVER" in text
        assert "total_cycles >= MIN_CYCLES_FOR_GOLD" in text

    def test_low_cycles_blocks_promotion(self):
        """A specialist with high EMA but low cycle count should stay at TIER_NONE."""
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            from orchestrator import PipelineController, TIER_NONE, TIER_BRONZE
            c = PipelineController()
            c.db_manager = MagicMock()
            # Mock: high EMA, but only 1 cycle (below MIN_CYCLES_FOR_BRONZE=3)
            c.db_manager.execute_query = MagicMock(return_value=[
                {'weighted_success': 50.0, 'weighted_fail': 0.0, 'packages_absorbed': 500}
            ])
            # Mock cycle_history: only 1 cycle
            c.db_manager.execute_query = MagicMock(side_effect=[
                [{'weighted_success': 50.0, 'weighted_fail': 0.0, 'packages_absorbed': 500}],
                [{'total': 1, 'fails': 0, 'avg_q': 0.95}],
            ])
            result = c._compute_tier(1, 0.95, TIER_NONE)
            # Should NOT promote to Bronze because only 1 cycle
            assert result == TIER_NONE, f"Expected TIER_NONE with 1 cycle, got {result}"
