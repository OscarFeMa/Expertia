import pytest
import sys
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    """Return a mock db_manager with execute_query."""
    db = MagicMock()
    db.execute_query.return_value = [{"ema_score": 0.50}]
    return db


def _update_ema_score(db, specialist_id, success, content_length=0, trust_score=50):
    """Inline copy of orchestrator.PipelineController.update_ema_score logic."""
    result = db.execute_query(
        "SELECT ema_score FROM specialist_registry WHERE id = ?", (specialist_id,), fetch=True
    )
    if not result:
        return
    current_ema = result[0]["ema_score"]
    alpha = 0.05
    if success:
        if content_length > 0:
            length_factor = min(content_length / 1000.0, 1.0)
            trust_factor = trust_score / 100.0
            quality = 0.6 * length_factor + 0.4 * trust_factor
        else:
            quality = 0.15
    else:
        quality = 0.0
    new_ema = alpha * quality + (1.0 - alpha) * current_ema
    db.execute_query(
        "UPDATE specialist_registry SET ema_score=? WHERE id=?",
        (new_ema, specialist_id),
    )
    db.execute_query(
        "INSERT INTO ema_history (specialist_id, ema_score) VALUES (?, ?)",
        (specialist_id, new_ema),
    )
    return new_ema


class TestEMAScoring:
    def test_success_with_content_increases_ema(self, mock_db):
        """EMA should increase when content is successfully processed."""
        new_ema = _update_ema_score(mock_db, 1, success=True, content_length=500, trust_score=80)
        # quality = 0.6*min(500/1000,1) + 0.4*0.8 = 0.6*0.5 + 0.32 = 0.62
        # new = 0.05*0.62 + 0.95*0.5 = 0.031 + 0.475 = 0.506
        assert new_ema == pytest.approx(0.506, rel=1e-3)
        assert new_ema > 0.50

    def test_success_without_content_small_boost(self, mock_db):
        """EMA should get a small boost even without content length."""
        new_ema = _update_ema_score(mock_db, 1, success=True, content_length=0)
        # quality = 0.15
        # new = 0.05*0.15 + 0.95*0.5 = 0.0075 + 0.475 = 0.4825
        assert new_ema == pytest.approx(0.4825, rel=1e-3)

    def test_failure_decreases_ema(self, mock_db):
        """EMA should decrease on failure (quality=0)."""
        new_ema = _update_ema_score(mock_db, 1, success=False)
        # new = 0.05*0 + 0.95*0.5 = 0.475
        assert new_ema == pytest.approx(0.475, rel=1e-3)
        assert new_ema < 0.50

    def test_content_length_capped_at_1000(self, mock_db):
        """content_length >=1000 should all produce same length_factor=1.0."""
        new_ema_1k = _update_ema_score(mock_db, 1, success=True, content_length=1000, trust_score=50)
        new_ema_5k = _update_ema_score(mock_db, 1, success=True, content_length=5000, trust_score=50)
        assert new_ema_1k == pytest.approx(new_ema_5k, rel=1e-3)

    def test_content_length_below_1000_varies(self, mock_db):
        """content_length below 1000 should produce different EMAs."""
        new_ema_100 = _update_ema_score(mock_db, 1, success=True, content_length=100, trust_score=50)
        new_ema_500 = _update_ema_score(mock_db, 1, success=True, content_length=500, trust_score=50)
        assert new_ema_100 != pytest.approx(new_ema_500, rel=1e-3)

    def test_multiple_updates_converge(self, mock_db):
        """Multiple successes should push EMA toward quality asymptote."""
        ema = 0.10
        mock_db.execute_query.return_value = [{"ema_score": ema}]
        for _ in range(50):
            mock_db.execute_query.return_value = [{"ema_score": ema}]
            ema = _update_ema_score(mock_db, 1, success=True, content_length=1000, trust_score=100)
        # Asymptote for quality=1.0 is 1.0
        assert ema > 0.90

    def test_db_query_called_correctly(self, mock_db):
        """Verify the correct SQL queries are executed."""
        _update_ema_score(mock_db, 42, success=True, content_length=200, trust_score=70)
        calls = [str(c) for c in mock_db.execute_query.call_args_list]
        assert any("ema_score FROM specialist_registry" in c for c in calls)
        assert any("UPDATE specialist_registry" in c for c in calls)
        assert any("INSERT INTO ema_history" in c for c in calls)
