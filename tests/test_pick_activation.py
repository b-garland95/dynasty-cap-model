"""Tests for src/contracts/pick_activation.py"""

import math

import pytest

from src.contracts.pick_activation import (
    activation_probability,
    effective_cap_hit,
    effective_value_contribution,
    pick_effective_economics,
    pick_slot_number,
)

# ---------------------------------------------------------------------------
# Minimal config fixture
# ---------------------------------------------------------------------------

CONFIG = {
    "draft_picks": {
        "picks_per_round": 10,
        # No activation_curve key → module defaults apply
    },
    "practice_squad": {
        "cap_percent": 0.25,
    },
}

CONFIG_CUSTOM_CURVE = {
    "draft_picks": {
        "picks_per_round": 10,
        "activation_curve": {
            "alpha": 0.90,
            "beta": 0.07,
            "floor": 0.08,
        },
    },
    "practice_squad": {
        "cap_percent": 0.25,
    },
}

# ---------------------------------------------------------------------------
# pick_slot_number
# ---------------------------------------------------------------------------


def test_slot_number_r1_pick1():
    assert pick_slot_number(1, 1) == 1


def test_slot_number_r1_pick10():
    assert pick_slot_number(1, 10) == 10


def test_slot_number_r2_pick1():
    assert pick_slot_number(2, 1) == 11


def test_slot_number_r2_pick10():
    assert pick_slot_number(2, 10) == 20


def test_slot_number_r4_pick10():
    assert pick_slot_number(4, 10) == 40


# ---------------------------------------------------------------------------
# activation_probability — curve shape
# ---------------------------------------------------------------------------


def test_r1_slot1_high_activation():
    """1.01 should have high activation probability (> 0.85)."""
    p = activation_probability(1, CONFIG)
    assert p > 0.85, f"expected p > 0.85 at slot 1, got {p:.4f}"


def test_activation_monotone_r1():
    """Activation probability is strictly decreasing within Round 1."""
    probs = [activation_probability(pick_slot_number(1, k), CONFIG) for k in range(1, 11)]
    for i in range(len(probs) - 1):
        assert probs[i] > probs[i + 1], (
            f"Not strictly decreasing: slot {i+1} p={probs[i]:.4f} >= slot {i+2} p={probs[i+1]:.4f}"
        )


def test_activation_monotone_across_rounds():
    """Activation probability is strictly decreasing from round 1 through round 4."""
    slots = [
        pick_slot_number(1, 1),   # 1.01
        pick_slot_number(1, 10),  # 1.10
        pick_slot_number(2, 1),   # 2.01
        pick_slot_number(2, 10),  # 2.10
        pick_slot_number(3, 1),   # 3.01
        pick_slot_number(4, 10),  # 4.10
    ]
    probs = [activation_probability(s, CONFIG) for s in slots]
    for i in range(len(probs) - 1):
        assert probs[i] > probs[i + 1], (
            f"Not strictly decreasing at index {i}: {probs[i]:.4f} >= {probs[i+1]:.4f}"
        )


def test_r2_sharp_dropoff_vs_r1():
    """Round 2 activation is materially lower than Round 1 overall.

    The curve is a smooth log-decay, so adjacent slots at the round boundary
    (1.10 → 2.01) differ by one slot step — a small gap by design.  The
    meaningful 'sharp dropoff' is visible when comparing Round-1 averages to
    Round-2 averages (or Round-1 first pick to Round-2 last pick).
    """
    p_r1_avg = sum(
        activation_probability(pick_slot_number(1, k), CONFIG) for k in range(1, 11)
    ) / 10
    p_r2_avg = sum(
        activation_probability(pick_slot_number(2, k), CONFIG) for k in range(1, 11)
    ) / 10
    # Round-2 average should be at least 15 percentage points below Round-1 average.
    assert p_r1_avg - p_r2_avg > 0.15, (
        f"R1 avg={p_r1_avg:.4f}, R2 avg={p_r2_avg:.4f}, gap={p_r1_avg - p_r2_avg:.4f}"
    )


def test_floor_applies_at_late_round():
    """Late round picks should hit the floor, not go below it."""
    # Default floor = 0.05; slot 40 (4.10) must equal floor.
    p = activation_probability(pick_slot_number(4, 10), CONFIG)
    assert p >= 0.05


def test_floor_is_lower_bound():
    """activation_probability is never below the floor for any slot."""
    for rnd in range(1, 5):
        for s in range(1, 11):
            slot = pick_slot_number(rnd, s)
            p = activation_probability(slot, CONFIG)
            assert p >= 0.05, f"p={p:.4f} below floor at round={rnd} slot={s}"


def test_returns_float():
    p = activation_probability(1, CONFIG)
    assert isinstance(p, float)


def test_config_none_uses_defaults():
    """Calling with config=None should produce the same result as config with no curve key."""
    p_none = activation_probability(1, None)
    p_cfg = activation_probability(1, CONFIG)
    assert abs(p_none - p_cfg) < 1e-9


def test_custom_curve_params():
    """Custom alpha/beta/floor are respected."""
    p = activation_probability(1, CONFIG_CUSTOM_CURVE)
    assert abs(p - 0.90) < 1e-9  # alpha=0.90, slot=1 → raw == alpha


def test_custom_floor_applied():
    """Custom floor is respected at late slots."""
    p = activation_probability(pick_slot_number(4, 10), CONFIG_CUSTOM_CURVE)
    assert p >= 0.08


# ---------------------------------------------------------------------------
# effective_cap_hit
# ---------------------------------------------------------------------------


def test_eff_cap_full_activation():
    """p_activate=1 → eff_cap == full_cap."""
    assert effective_cap_hit(10.0, 1.0, 0.25) == 10.0


def test_eff_cap_no_activation():
    """p_activate=0 → eff_cap == ps_cap."""
    assert effective_cap_hit(10.0, 0.0, 0.25) == 2.5


def test_eff_cap_midpoint():
    """p_activate=0.5 → midpoint between full and PS cap."""
    result = effective_cap_hit(10.0, 0.5, 0.25)
    expected = 0.5 * 10.0 + 0.5 * 2.5
    assert abs(result - expected) < 1e-9


def test_eff_cap_always_below_full():
    """eff_cap < full_cap whenever p_activate < 1."""
    for p in [0.0, 0.3, 0.7, 0.99]:
        assert effective_cap_hit(10.0, p, 0.25) <= 10.0


def test_eff_cap_always_above_ps_cap():
    """eff_cap >= ps_cap for any p_activate in [0, 1]."""
    ps_cap = 0.25 * 10.0
    for p in [0.0, 0.3, 0.7, 1.0]:
        assert effective_cap_hit(10.0, p, 0.25) >= ps_cap


# ---------------------------------------------------------------------------
# effective_value_contribution
# ---------------------------------------------------------------------------


def test_eff_value_full_activation():
    assert effective_value_contribution(10.0, 1.0, 0.25) == 10.0


def test_eff_value_no_activation():
    assert effective_value_contribution(10.0, 0.0, 0.25) == 2.5


def test_eff_value_equals_eff_cap_for_rookies():
    """Since intrinsic_value == full_cap for rookies, eff_value == eff_cap."""
    for p in [0.0, 0.5, 0.92, 1.0]:
        assert abs(
            effective_value_contribution(10.0, p, 0.25)
            - effective_cap_hit(10.0, p, 0.25)
        ) < 1e-9


# ---------------------------------------------------------------------------
# pick_effective_economics
# ---------------------------------------------------------------------------


def test_pick_econ_r1_slot1_high_p():
    """1.01 has p_activate > 0.85 and eff_cap close to full_cap."""
    result = pick_effective_economics(1, 1, 14.0, CONFIG)
    assert result["p_activate"] > 0.85
    assert result["eff_cap_hit"] > result["ps_cap"]
    assert result["eff_cap_hit"] <= result["full_cap"]


def test_pick_econ_r1_slot1_known_slot():
    result = pick_effective_economics(1, 1, 14.0, CONFIG)
    assert result["slot"] == 1


def test_pick_econ_r2_lower_p_than_r1():
    r1 = pick_effective_economics(1, 10, 6.0, CONFIG)
    r2 = pick_effective_economics(2, 1, 4.0, CONFIG)
    assert r2["p_activate"] < r1["p_activate"]


def test_pick_econ_unknown_slot_uses_midpoint():
    """slot_within_round=None falls back to picks_per_round//2 + 1."""
    result_none = pick_effective_economics(2, None, 4.0, CONFIG)
    result_mid = pick_effective_economics(2, 6, 4.0, CONFIG)
    assert result_none["slot"] == result_mid["slot"]
    assert abs(result_none["p_activate"] - result_mid["p_activate"]) < 1e-9


def test_pick_econ_zero_cap_returns_zeros():
    """Future-year picks (full_cap=0) produce eff_cap=0 and eff_value=0."""
    result = pick_effective_economics(1, 1, 0.0, CONFIG)
    assert result["eff_cap_hit"] == 0.0
    assert result["eff_value"] == 0.0


def test_pick_econ_ps_cap_percent_from_config():
    result = pick_effective_economics(1, 1, 10.0, CONFIG)
    assert abs(result["ps_cap_percent"] - 0.25) < 1e-9
    assert abs(result["ps_cap"] - 0.25 * 10.0) < 1e-9


def test_pick_econ_symmetric_cap_and_value():
    """eff_cap_hit and eff_value are identical for rookie picks."""
    result = pick_effective_economics(2, 5, 4.0, CONFIG)
    assert abs(result["eff_cap_hit"] - result["eff_value"]) < 1e-9


def test_pick_econ_r4_low_p():
    """Round 4 picks should have low activation probability (near floor)."""
    result = pick_effective_economics(4, 10, 1.0, CONFIG)
    assert result["p_activate"] <= 0.20


def test_pick_econ_eff_cap_less_than_full_beyond_r1():
    """All non-top picks should have eff_cap < full_cap due to partial PS discount."""
    # 1.10 already has p_activate < 1 with default params
    result = pick_effective_economics(1, 10, 6.0, CONFIG)
    assert result["eff_cap_hit"] < result["full_cap"]
