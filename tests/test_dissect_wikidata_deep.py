"""Tests for dissect_wikidata.py — entity matching, QID extraction, batch extractor."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEntityMatching:
    """Tests for _entity_matches_target() P31/P279 matching."""

    def test_import_exists(self):
        from dissect_wikidata import WikidataStreamingExtractor
        assert hasattr(WikidataStreamingExtractor, '_entity_matches_target')

    def _make_extractor(self, target_qids=None):
        from dissect_wikidata import WikidataStreamingExtractor
        ext = object.__new__(WikidataStreamingExtractor)
        ext._custom_matcher = None
        ext.target_qids = target_qids or set()
        return ext

    def test_matches_p31(self):
        ext = self._make_extractor({"Q11190"})
        entity = {
            "claims": {
                "P31": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q11190"}}}}
                ]
            }
        }
        result = ext._entity_matches_target(entity)
        assert result is True

    def test_matches_p279(self):
        ext = self._make_extractor({"Q11190"})
        entity = {
            "claims": {
                "P279": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q11190"}}}}
                ]
            }
        }
        result = ext._entity_matches_target(entity)
        assert result is True

    def test_no_match(self):
        ext = self._make_extractor({"Q11190"})
        entity = {
            "claims": {
                "P31": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q99999"}}}}
                ]
            }
        }
        result = ext._entity_matches_target(entity)
        assert result is False

    def test_empty_claims(self):
        ext = self._make_extractor({"Q11190"})
        entity = {"claims": {}}
        result = ext._entity_matches_target(entity)
        assert result is False


class TestTagToQidMap:
    """Tests for TAG_TO_QID_MAP domain mapping."""

    def test_import_exists(self):
        from dissect_wikidata import TAG_TO_QID_MAP
        assert isinstance(TAG_TO_QID_MAP, dict)

    def test_medicine_mapped(self):
        from dissect_wikidata import TAG_TO_QID_MAP
        assert "medicine" in TAG_TO_QID_MAP

    def test_physics_mapped(self):
        from dissect_wikidata import TAG_TO_QID_MAP
        assert "physics" in TAG_TO_QID_MAP


class TestBatchWikidataExtractor:
    """Tests for BatchWikidataExtractor batch processing."""

    def test_import_exists(self):
        from dissect_wikidata import BatchWikidataExtractor
        assert callable(BatchWikidataExtractor)

    def test_get_entity_qids(self):
        from dissect_wikidata import BatchWikidataExtractor
        entity = {
            "claims": {
                "P31": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q11190"}}}}
                ],
                "P279": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q12345"}}}}
                ]
            }
        }
        ext = object.__new__(BatchWikidataExtractor)
        qids = ext._get_entity_qids(entity)
        assert "Q11190" in qids
        assert "Q12345" in qids
