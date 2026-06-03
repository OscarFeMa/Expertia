"""Tests for tools/update_wikidata.py — SPARQL, garbage filter, entity batch fetch."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGarbageFilter:
    """Tests for is_garbage_content() filter."""

    def test_import_exists(self):
        from tools.update_wikidata import is_garbage_content
        assert callable(is_garbage_content)

    def test_captcha_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("Please complete the CAPTCHA verification") is True

    def test_cookie_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("We use cookies to improve your experience") is True

    def test_loading_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("Loading... please wait") is True

    def test_good_content_accepted(self):
        from tools.update_wikidata import is_garbage_content
        content = "Mathematics is the study of numbers, shapes and patterns. It has many branches including algebra, geometry and calculus."
        assert is_garbage_content(content) is False

    def test_short_content_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("Short") is True

    def test_empty_content_rejected(self):
        from tools.update_wikidata import is_garbage_content
        assert is_garbage_content("") is True


class TestBuildSparqlQuery:
    """Tests for build_sparql_query() SPARQL generation."""

    def test_import_exists(self):
        from tools.update_wikidata import build_sparql_query
        assert callable(build_sparql_query)

    def test_generates_valid_sparql(self):
        from tools.update_wikidata import build_sparql_query
        query = build_sparql_query("Q11190", since=None)
        assert "SELECT" in query
        assert "WHERE" in query
        assert "Q11190" in query

    def test_since_filter_applied(self):
        from tools.update_wikidata import build_sparql_query
        query = build_sparql_query("Q11190", since="2026-01-01T00:00:00Z")
        assert "2026-01-01" in query


class TestRunSparql:
    """Tests for run_sparql() with mocked HTTP."""

    def test_import_exists(self):
        from tools.update_wikidata import run_sparql
        assert callable(run_sparql)

    @patch('tools.update_wikidata.requests.get')
    def test_returns_results_on_success(self, mock_get):
        from tools.update_wikidata import run_sparql
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": {"bindings": [{"qid": {"value": "Q123"}}]}
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        results = run_sparql("SELECT * WHERE { ?qid wdt:P31 wd:Q11190 }")
        assert isinstance(results, list)


class TestFetchEntitiesBatch:
    """Tests for fetch_entities_batch() with mocked HTTP."""

    def test_import_exists(self):
        from tools.update_wikidata import fetch_entities_batch
        assert callable(fetch_entities_batch)
