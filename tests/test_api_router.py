"""Tests for api_router.py — FastAPI API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestIsPidAlive:
    def test_none_pid(self):
        from api_router import _is_pid_alive
        assert _is_pid_alive(None) is False

    @patch("api_router.os.name", "nt")
    @patch("api_router.subprocess.run")
    def test_windows_pid_alive(self, mock_run):
        from api_router import _is_pid_alive
        mock_run.return_value = MagicMock(stdout="python.exe 1234 Console 1 10,000 K")
        result = _is_pid_alive(1234)
        assert result is True
        mock_run.assert_called_once()

    @patch("api_router.os.name", "nt")
    @patch("api_router.subprocess.run")
    def test_windows_pid_not_alive(self, mock_run):
        from api_router import _is_pid_alive
        mock_run.return_value = MagicMock(stdout="No tasks running")
        result = _is_pid_alive(9999)
        assert result is False

    @patch("api_router.os.name", "posix")
    @patch("api_router.os.kill")
    def test_posix_pid_alive(self, mock_kill):
        from api_router import _is_pid_alive
        mock_kill.return_value = None
        result = _is_pid_alive(1234)
        assert result is True

    @patch("api_router.os.name", "posix")
    @patch("api_router.os.kill")
    def test_posix_pid_dead(self, mock_kill):
        from api_router import _is_pid_alive
        mock_kill.side_effect = OSError()
        result = _is_pid_alive(1234)
        assert result is False


class TestPipelineState:
    def test_save_and_load(self, tmp_path):
        import json
        from api_router import _save_pipeline_state, _load_pipeline_state, _pipeline, _PIPELINE_STATE_FILE

        original_path = _PIPELINE_STATE_FILE
        try:
            test_file = tmp_path / "test_pipeline_state.json"
            import api_router
            api_router._PIPELINE_STATE_FILE = test_file

            _pipeline["pid"] = 42
            _pipeline["duration_hours"] = 3.0
            _save_pipeline_state()

            _pipeline["pid"] = None
            _pipeline["duration_hours"] = 0
            _load_pipeline_state()

            assert _pipeline["pid"] == 42
            assert _pipeline["duration_hours"] == 3.0
        finally:
            api_router._PIPELINE_STATE_FILE = original_path


class TestEndpoints:
    @pytest.fixture
    async def client(self):
        from httpx import ASGITransport, AsyncClient
        from query_api import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "database" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_status_returns_200(self, client):
        resp = await client.get("/api/status")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_specialists_returns_200(self, client):
        resp = await client.get("/api/specialists")
        assert resp.status_code == 200
        data = resp.json()
        assert "specialists" in data

    @pytest.mark.asyncio
    async def test_activity_log_returns_200(self, client):
        resp = await client.get("/api/activity-log?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data

    @pytest.mark.asyncio
    async def test_knowledge_stats_returns_200(self, client):
        resp = await client.get("/api/knowledge-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_packages" in data
        assert "by_domain" in data

    @pytest.mark.asyncio
    async def test_pipeline_pid_returns_200(self, client):
        resp = await client.get("/api/pipeline/pid")
        assert resp.status_code == 200
        data = resp.json()
        assert "pid" in data
        assert "alive" in data

    @pytest.mark.asyncio
    async def test_ollama_models_returns_200(self, client):
        resp = await client.get("/api/ollama/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data

    @pytest.mark.asyncio
    async def test_start_pipeline_without_auth_returns_403(self, client):
        import api_router
        api_router.EXPERTIA_API_KEY = "test-secret"
        resp = await client.post("/api/pipeline/start", json={"phase": "web"})
        assert resp.status_code == 403
        api_router.EXPERTIA_API_KEY = ""

    @pytest.mark.asyncio
    async def test_stop_pipeline_without_auth_returns_403(self, client):
        import api_router
        api_router.EXPERTIA_API_KEY = "test-secret"
        resp = await client.post("/api/pipeline/stop")
        assert resp.status_code == 403
        api_router.EXPERTIA_API_KEY = ""

    @pytest.mark.asyncio
    async def test_super_experts_returns_200(self, client):
        resp = await client.get("/api/super-experts")
        assert resp.status_code == 200
        data = resp.json()
        assert "super_experts" in data
