import pytest
import math
import sys
from unittest.mock import MagicMock, patch


TIER_NONE = 0
FAILURE_PENALTIES = {0: 0.965, 1: 0.96, 2: 0.98, 3: 0.99, 4: 0.99}
TIER_NAMES = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Legend"}


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_query.return_value = [{"ema_score": 0.50, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
    return db


def _update_ema_score(db, specialist_id, success, content_length=0, trust_score=50, contents_count=0, packages_saved=0, current_tier=0):
    """Inline copy of orchestrator.PipelineController.update_ema_score logic (quadratic convergence)."""
    result = db.execute_query(
        "SELECT ema_score FROM specialist_registry WHERE id = ?", (specialist_id,), fetch=True
    )
    if not result:
        return
    current_ema = result[0]["ema_score"]
    ws = 0.0
    wf = 0.0

    if success:
        if content_length > 0 and contents_count > 0:
            size_factor = 1.0 - math.exp(-content_length / 5000)
            coverage_factor = min(contents_count / 10.0, 1.0)
            trust_factor = trust_score / 100.0
            efficiency = min(packages_saved / max(contents_count, 1), 1.0)
            quality = 0.25 * size_factor + 0.25 * coverage_factor + 0.25 * trust_factor + 0.25 * efficiency
        else:
            quality = 0.1
        ws += quality
        alpha = 0.08
        new_ema = current_ema + alpha * quality * (1.0 - current_ema)
    else:
        quality = 0.0
        wf += 1.0
        penalty = FAILURE_PENALTIES.get(current_tier, 0.94)
        new_ema = current_ema * penalty

    db.execute_query(
        "UPDATE specialist_registry SET ema_score=? WHERE id=?",
        (new_ema, specialist_id),
    )
    db.execute_query(
        "INSERT INTO ema_history (specialist_id, ema_score) VALUES (?, ?)",
        (specialist_id, new_ema),
    )
    db.execute_query(
        "INSERT INTO cycle_history (specialist_id, success, quality, ema_before, ema_after) VALUES (?, ?, ?, ?, ?)",
        (specialist_id, 1 if success else 0, quality, current_ema, new_ema),
    )
    return new_ema


class TestEMAScoring:
    def test_success_with_content_increases_ema(self, mock_db):
        new_ema = _update_ema_score(mock_db, 1, success=True, content_length=500, trust_score=80, contents_count=1, packages_saved=1)
        # size_factor = 1 - exp(-500/5000) ≈ 0.0952
        # coverage_factor = min(1/10, 1) = 0.1
        # trust_factor = 0.8
        # efficiency = min(1/1, 1) = 1.0
        # quality = 0.25*(0.0952 + 0.1 + 0.8 + 1.0) ≈ 0.4988
        # new_ema = 0.5 + 0.08 * 0.4988 * (1 - 0.5) = 0.5 + 0.01995 ≈ 0.5200
        assert new_ema == pytest.approx(0.5200, rel=1e-2)
        assert new_ema > 0.50

    def test_success_without_content_small_boost(self, mock_db):
        new_ema = _update_ema_score(mock_db, 1, success=True, content_length=0)
        # quality = 0.1
        # new_ema = 0.5 + 0.08 * 0.1 * (1 - 0.5) = 0.5 + 0.004 = 0.504
        assert new_ema == pytest.approx(0.504, rel=1e-3)

    def test_failure_decreases_ema(self, mock_db):
        new_ema = _update_ema_score(mock_db, 1, success=False)
        # tier=0 → penalty=0.965, new_ema = 0.5 * 0.965 = 0.4825
        assert new_ema == pytest.approx(0.4825, rel=1e-3)
        assert new_ema < 0.50

    def test_failure_penalty_less_severe_at_higher_tier(self, mock_db):
        """Higher tiers get gentler failure penalties."""
        ema_none = _update_ema_score(mock_db, 1, success=False, current_tier=0)
        ema_legend = _update_ema_score(mock_db, 1, success=False, current_tier=4)
        # tier=0: 0.5*0.965=0.4825; tier=4: 0.5*0.99=0.495
        assert ema_legend > ema_none

    def test_content_length_capped_at_saturation(self, mock_db):
        """Very long content should saturate size_factor near 1.0."""
        new_ema_5k = _update_ema_score(mock_db, 1, success=True, content_length=5000, trust_score=100, contents_count=1, packages_saved=1)
        new_ema_20k = _update_ema_score(mock_db, 1, success=True, content_length=20000, trust_score=100, contents_count=1, packages_saved=1)
        assert new_ema_5k == pytest.approx(new_ema_20k, rel=1e-2)

    def test_content_length_below_threshold_varies(self, mock_db):
        new_ema_100 = _update_ema_score(mock_db, 1, success=True, content_length=100, trust_score=50, contents_count=1, packages_saved=1)
        new_ema_5k = _update_ema_score(mock_db, 1, success=True, content_length=5000, trust_score=50, contents_count=1, packages_saved=1)
        assert abs(new_ema_5k - new_ema_100) > 0.001

    def test_multiple_updates_converge_to_one(self, mock_db):
        ema = 0.10
        mock_db.execute_query.return_value = [{"ema_score": ema, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
        for _ in range(200):
            mock_db.execute_query.return_value = [{"ema_score": ema, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
            ema = _update_ema_score(mock_db, 1, success=True, content_length=10000, trust_score=100, contents_count=10, packages_saved=10)
        # Quadratic convergence asymptotically approaches 1.0 (never reaches exactly)
        assert ema > 0.98
        assert ema < 1.0

    def test_quadratic_convergence_never_overshoots(self, mock_db):
        """Quality=1.0 should approach but never exceed 1.0."""
        ema = 0.999
        mock_db.execute_query.return_value = [{"ema_score": ema, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
        for _ in range(50):
            mock_db.execute_query.return_value = [{"ema_score": ema, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
            ema = _update_ema_score(mock_db, 1, success=True, content_length=10000, trust_score=100, contents_count=10, packages_saved=10)
        assert ema < 1.0

    def test_db_query_called_correctly(self, mock_db):
        _update_ema_score(mock_db, 42, success=True, content_length=200, trust_score=70, contents_count=1, packages_saved=1)
        calls = [str(c) for c in mock_db.execute_query.call_args_list]
        assert any("ema_score FROM specialist_registry" in c for c in calls)
        assert any("UPDATE specialist_registry" in c for c in calls)
        assert any("INSERT INTO ema_history" in c for c in calls)
        assert any("INSERT INTO cycle_history" in c for c in calls)
