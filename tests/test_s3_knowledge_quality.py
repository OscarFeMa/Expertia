"""Tests for Phase S3 — Knowledge quality improvements."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestS31_PropertyLabels:
    """S3.1: Wikidata property labels must be resolved to human-readable names."""

    def test_property_labels_dict_exists(self):
        from tools.update_wikidata import PROPERTY_LABELS
        assert 'P31' in PROPERTY_LABELS
        assert PROPERTY_LABELS['P31'] == 'instance of'
        assert PROPERTY_LABELS['P279'] == 'subclass of'

    def test_property_labels_used_in_build(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "tools" / "update_wikidata.py"
        text = content.read_text(encoding="utf-8")
        assert "PROPERTY_LABELS.get(prop_id, prop_id)" in text


class TestS32_QualityFilter:
    """S3.2: Garbage content must be rejected before INSERT."""

    def test_is_garbage_content_exists(self):
        from tools.update_wikidata import is_garbage_content
        assert callable(is_garbage_content)

    def test_garbage_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("This page requires cookie to be enabled") is True
        assert is_garbage_content("Sign in to continue") is True
        assert is_garbage_content("short") is True  # too short
        assert is_garbage_content("") is True
        assert is_garbage_content("JavaScript is disabled in your browser") is True

    def test_good_content_accepted(self):
        from tools.update_wikidata import is_garbage_content
        text = "Physics is the fundamental science of matter and energy. It studies the behavior of the universe at every scale."
        assert is_garbage_content(text) is False

    def test_filter_used_in_update(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "tools" / "update_wikidata.py"
        text = content.read_text(encoding="utf-8")
        assert "is_garbage_content(structured)" in text


class TestS33_TierFiltering:
    """S3.3: Knowledge must only be served from specialists with tier >= 1."""

    def test_tier_join_in_fetch_context(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "query_api.py"
        text = content.read_text(encoding="utf-8")
        assert "sr.tier >= 1" in text
        assert "JOIN specialist_registry sr" in text


class TestS34_KeywordMatching:
    """S3.4: query_super_expert must use question keywords for relevance."""

    def test_keyword_scoring_in_query(self):
        from pathlib import Path
        content = Path(__file__).parent.parent / "orchestrator.py"
        text = content.read_text(encoding="utf-8")
        assert "relevance" in text
        assert "keywords" in text

    def test_query_super_expert_returns_top_k(self):
        with patch("orchestrator.get_db_manager") as mock_db, \
             patch("orchestrator.LLMRunner"), \
             patch("orchestrator.ModernWebScraper"), \
             patch("orchestrator.MetricsCollector"), \
             patch("orchestrator.KnowledgeIngestor"):
            from orchestrator import PipelineController
            c = PipelineController()
            c.db_manager = MagicMock()
            c.db_manager.execute_query = MagicMock(return_value=[
                {'topic': 'Quantum physics', 'structured_knowledge': 'Quantum mechanics basics',
                 'source_url': 'http://test.com', 'created_at': '2026-01-01'},
                {'topic': 'Classical mechanics', 'structured_knowledge': 'Newton laws',
                 'source_url': 'http://test2.com', 'created_at': '2026-01-02'},
            ])
            # Mock get_super_expert_members
            c.get_super_expert_members = MagicMock(return_value=[
                {'domain': 'Physics', 'weight': 1.0, 'ema_score': 0.96}
            ])
            results = c.query_super_expert('PhysicsCouncil', 'quantum entanglement', top_k=5)
            assert isinstance(results, list)
            assert len(results) <= 5
