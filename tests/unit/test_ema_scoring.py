import pytest
import math
import sys
from unittest.mock import MagicMock, patch


TIER_NONE = 0
TIER_BRONZE = 1
TIER_SILVER = 2
TIER_GOLD = 3
TIER_LEGEND = 4
FAILURE_PENALTIES = {0: 0.965, 1: 0.96, 2: 0.98, 3: 0.99, 4: 0.99}
TIER_NAMES = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Legend"}

TIER_CRITERIA = {
    TIER_BRONZE: {"ema": 0.92, "quality": 0.60, "fail_rate": 0.15, "packages": 200},
    TIER_SILVER: {"ema": 0.95, "quality": 0.70, "fail_rate": 0.08, "packages": 500},
    TIER_GOLD: {"ema": 0.97, "quality": 0.75, "fail_rate": 0.05, "packages": 1500},
}
LEGEND_EMA_MIN = 0.995
LEGEND_CYCLES_CLEAN = 25
MIN_CYCLES_FOR_BRONZE = 3
MIN_CYCLES_FOR_SILVER = 10
MIN_CYCLES_FOR_GOLD = 25


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_query.return_value = [{"ema_score": 0.50, "weighted_success": 0.0, "weighted_fail": 0.0, "tier": 0}]
    return db


def _update_ema_score(db, specialist_id, success, content_length=0, trust_score=50, contents_count=0, packages_saved=0, current_tier=0, failure_type='knowledge'):
    """Inline copy of orchestrator.PipelineController.update_ema_score logic."""
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
        if failure_type == 'knowledge':
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
        "INSERT INTO cycle_history (specialist_id, success, quality, ema_before, ema_after, failure_type) VALUES (?, ?, ?, ?, ?, ?)",
        (specialist_id, 1 if success else 0, quality, current_ema, new_ema, failure_type),
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


# ── Tier computation tests (relaxed Gold: quality 0.75, fail_rate 0.05) ──

def _compute_tier(ema, avg_quality, fail_rate, packages, total_cycles,
                  current_tier=TIER_NONE, clean_cycles=0, window_fails=0):
    """Inline copy of orchestrator.PipelineController._compute_tier logic."""
    if current_tier == TIER_LEGEND:
        if window_fails < 2:
            return TIER_LEGEND
        return TIER_GOLD
    if (ema >= TIER_CRITERIA[TIER_GOLD]["ema"]
            and avg_quality >= TIER_CRITERIA[TIER_GOLD]["quality"]
            and fail_rate < TIER_CRITERIA[TIER_GOLD]["fail_rate"]
            and packages >= TIER_CRITERIA[TIER_GOLD]["packages"]
            and total_cycles >= MIN_CYCLES_FOR_GOLD):
        if ema >= LEGEND_EMA_MIN and clean_cycles >= LEGEND_CYCLES_CLEAN:
            return TIER_LEGEND
        return TIER_GOLD
    if (ema >= TIER_CRITERIA[TIER_SILVER]["ema"]
            and avg_quality >= TIER_CRITERIA[TIER_SILVER]["quality"]
            and fail_rate < TIER_CRITERIA[TIER_SILVER]["fail_rate"]
            and packages >= TIER_CRITERIA[TIER_SILVER]["packages"]
            and total_cycles >= MIN_CYCLES_FOR_SILVER):
        return TIER_SILVER
    if (ema >= TIER_CRITERIA[TIER_BRONZE]["ema"]
            and avg_quality >= TIER_CRITERIA[TIER_BRONZE]["quality"]
            and fail_rate < TIER_CRITERIA[TIER_BRONZE]["fail_rate"]
            and packages >= TIER_CRITERIA[TIER_BRONZE]["packages"]
            and total_cycles >= MIN_CYCLES_FOR_BRONZE):
        return TIER_BRONZE
    return TIER_NONE


class TestTierComputation:
    def test_gold_relaxed_quality_threshold(self):
        """Gold now requires quality >= 0.75 (was 0.78). Specialist with 0.76 should pass."""
        tier = _compute_tier(ema=0.975, avg_quality=0.76, fail_rate=0.03,
                             packages=2000, total_cycles=30)
        assert tier == TIER_GOLD

    def test_gold_relaxed_fail_rate_threshold(self):
        """Gold now requires fail_rate < 0.05 (was 0.03). Specialist with 0.04 should pass."""
        tier = _compute_tier(ema=0.98, avg_quality=0.80, fail_rate=0.04,
                             packages=2000, total_cycles=30)
        assert tier == TIER_GOLD

    def test_gold_old_strict_quality_fails(self):
        """Quality 0.77 is below old 0.78 but above new 0.75 — should now pass."""
        tier = _compute_tier(ema=0.975, avg_quality=0.77, fail_rate=0.02,
                             packages=2000, total_cycles=30)
        assert tier == TIER_GOLD

    def test_gold_fail_rate_at_boundary_rejected(self):
        """fail_rate == 0.05 is NOT < 0.05, so Gold should be rejected."""
        tier = _compute_tier(ema=0.98, avg_quality=0.80, fail_rate=0.05,
                             packages=2000, total_cycles=30)
        assert tier == TIER_SILVER

    def test_gold_quality_below_threshold_rejected(self):
        """Quality 0.74 is below 0.75 — should fall to Silver."""
        tier = _compute_tier(ema=0.975, avg_quality=0.74, fail_rate=0.02,
                             packages=2000, total_cycles=30)
        assert tier == TIER_SILVER

    def test_gold_min_cycles_required(self):
        """Below MIN_CYCLES_FOR_GOLD (25) cycles, Gold is not granted."""
        tier = _compute_tier(ema=0.98, avg_quality=0.80, fail_rate=0.01,
                             packages=2000, total_cycles=20)
        assert tier == TIER_SILVER

    def test_legend_promotion(self):
        """EMA >= 0.995 + 25 clean cycles + Gold criteria = Legend."""
        tier = _compute_tier(ema=0.997, avg_quality=0.80, fail_rate=0.0,
                             packages=5000, total_cycles=30, clean_cycles=25)
        assert tier == TIER_LEGEND

    def test_legend_demoted_on_window_failures(self):
        """Legend with 2+ knowledge failures in last 25 cycles demoted to Gold."""
        tier = _compute_tier(ema=0.997, avg_quality=0.80, fail_rate=0.0,
                             packages=5000, total_cycles=30,
                             current_tier=TIER_LEGEND, window_fails=2)
        assert tier == TIER_GOLD

    def test_legend_maintained_under_2_failures(self):
        """Legend with only 1 failure in window stays Legend."""
        tier = _compute_tier(ema=0.997, avg_quality=0.80, fail_rate=0.0,
                             packages=5000, total_cycles=30,
                             current_tier=TIER_LEGEND, window_fails=1)
        assert tier == TIER_LEGEND

    def test_philosophy_history_unblocked(self):
        """Real case: PhilosophyHistory avgQ=0.775, fail_rate=0.06.
        Old strict (quality>=0.78, fail<0.03) would reject. New (quality>=0.75, fail<0.05) —
        still fails fail_rate (0.06 >= 0.05) so it's Silver, not Gold."""
        tier = _compute_tier(ema=0.9845, avg_quality=0.775, fail_rate=0.06,
                             packages=9205891, total_cycles=50)
        assert tier == TIER_SILVER

    def test_full_tier_ordering(self):
        """Verify tier priority: a Legend-eligible specialist beats Gold."""
        legend_tier = _compute_tier(ema=0.998, avg_quality=0.85, fail_rate=0.0,
                                    packages=9000000, total_cycles=50, clean_cycles=25)
        gold_tier = _compute_tier(ema=0.98, avg_quality=0.80, fail_rate=0.02,
                                  packages=9000000, total_cycles=50)
        assert legend_tier > gold_tier
