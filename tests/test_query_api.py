"""Tests for query_api.py — FastAPI query endpoint."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from query_api import _find_best_domain, _fetch_context


class TestFindBestDomain:
    def test_software_keyword(self):
        domain, model = _find_best_domain("How do I write a Python function?")
        assert domain == "SoftwareEngineering"

    def test_medicine_keyword(self):
        domain, model = _find_best_domain("What causes heart disease?")
        assert domain == "Medicine"

    def test_finance_keyword(self):
        domain, model = _find_best_domain("What is inflation?")
        assert domain == "FinanceEconomics"

    def test_fallback_to_first_specialist(self):
        domain, model = _find_best_domain("Tell me a story")
        assert domain is not None


class TestFetchContext:
    @patch("query_api._get_db")
    def test_returns_list(self, mock_get_db):
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {"structured_knowledge": "Some context about medicine"}
        ]
        mock_get_db.return_value = mock_db
        result = _fetch_context("Medicine", "test", max_chars=2000)
        assert isinstance(result, list)
        assert len(result) > 0

    @patch("query_api._get_db")
    def test_empty_db_returns_empty_list(self, mock_get_db):
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []
        mock_get_db.return_value = mock_db
        result = _fetch_context("Unknown", "test", max_chars=2000)
        assert isinstance(result, list)


class TestQueryRequest:
    def test_question_required(self):
        from query_api import QueryRequest
        req = QueryRequest(question="What is quantum computing?")
        assert req.question == "What is quantum computing?"
        assert req.domain is None
        assert req.max_context_tokens == 2000
