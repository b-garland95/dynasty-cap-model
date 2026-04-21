"""Integration tests: pick activation economics wired into the cap health pipeline.

Covers the end-to-end path from pick inventory → effective cap / value fields
that the Cap Health dashboard consumes.

Specifically exercises:
  - _enrich_picks_with_values (server-side enrichment)
  - pick_effective_economics used inside enrich
  - That owned picks change both projected value (eff_value > 0) and
    effective cap burden (eff_cap_hit > 0) for current-year picks
  - That future-year picks contribute 0 to both
  - That eff_cap_hit < full_cap for picks below slot 1 (activation discount applied)
"""

from __future__ import annotations

import math

import pytest

from src.contracts.pick_activation import (
    activation_probability,
    pick_slot_number,
    pick_effective_economics,
)
from src.contracts.pick_values import pick_base_salary, pick_value_metrics

# ---------------------------------------------------------------------------
# Shared config matching league_config.yaml defaults
# ---------------------------------------------------------------------------

ROOKIE_SCALE = {
    "round1": {
        "1.01": 14, "1.02": 12, "1.03": 12, "1.04": 10, "1.05": 10,
        "1.06": 10, "1.07": 8,  "1.08": 8,  "1.09": 8,  "1.10": 6,
    },
    "round2_salary": 4,
    "round3_salary": 2,
    "round4_salary": 1,
    "contract_years": 3,
    "option_years": 1,
}

CONFIG = {
    "rookie_scale": ROOKIE_SCALE,
    "cap": {
        "base_cap": 300,
        "annual_inflation": 0.10,
        "discount_rate": 0.25,
    },
    "season": {
        "target_season": 2026,
    },
    "draft_picks": {
        "picks_per_round": 10,
    },
    "practice_squad": {
        "cap_percent": 0.25,
    },
}

CURRENT_SEASON = 2026


# ---------------------------------------------------------------------------
# Helpers mirroring _enrich_picks_with_values from server.py
# ---------------------------------------------------------------------------

def enrich_pick(rnd: int, slot: int | None, year: int) -> dict:
    """Return an enriched pick dict matching the server-side logic."""
    base = pick_base_salary(rnd, slot, ROOKIE_SCALE)
    metrics = pick_value_metrics(base, year, CURRENT_SEASON, CONFIG)
    econ = pick_effective_economics(
        rnd=rnd,
        slot_within_round=slot,
        full_cap_current_year=float(metrics["value_1yr"]),
        config=CONFIG,
    )
    return {
        "round": rnd,
        "slot": slot,
        "year": year,
        **metrics,
        "p_activate": econ["p_activate"],
        "eff_cap_hit": econ["eff_cap_hit"],
        "eff_value": econ["eff_value"],
    }


# ---------------------------------------------------------------------------
# Current-year picks (offset=0) contribute non-zero effective values
# ---------------------------------------------------------------------------


def test_current_year_r1_slot1_has_nonzero_eff_value():
    p = enrich_pick(1, 1, CURRENT_SEASON)
    assert p["eff_value"] > 0, "1.01 current-year pick should contribute eff_value"


def test_current_year_r1_slot1_has_nonzero_eff_cap_hit():
    p = enrich_pick(1, 1, CURRENT_SEASON)
    assert p["eff_cap_hit"] > 0, "1.01 current-year pick should contribute eff_cap_hit"


def test_current_year_eff_cap_less_than_full_cap_for_late_r1():
    """Late Round 1 picks should have eff_cap_hit < full value_1yr due to partial PS discount."""
    p = enrich_pick(1, 10, CURRENT_SEASON)
    assert p["eff_cap_hit"] < p["value_1yr"]


def test_current_year_eff_value_equals_eff_cap_hit():
    """For rookie picks (zero surplus), eff_value == eff_cap_hit."""
    for rnd, slot in [(1, 1), (1, 5), (1, 10), (2, 1), (3, None), (4, None)]:
        p = enrich_pick(rnd, slot, CURRENT_SEASON)
        assert abs(p["eff_value"] - p["eff_cap_hit"]) < 1e-9, (
            f"eff_value != eff_cap_hit for round={rnd} slot={slot}"
        )


# ---------------------------------------------------------------------------
# Future-year picks (offset > 0) contribute zero effective values
# ---------------------------------------------------------------------------


def test_future_year_r1_slot1_eff_value_is_zero():
    """A 2027 pick contributes nothing to current-year effective value."""
    p = enrich_pick(1, 1, CURRENT_SEASON + 1)
    assert p["eff_value"] == 0.0


def test_future_year_r1_slot1_eff_cap_hit_is_zero():
    """A 2027 pick has zero current-year cap burden."""
    p = enrich_pick(1, 1, CURRENT_SEASON + 1)
    assert p["eff_cap_hit"] == 0.0


def test_two_year_future_pick_zero_eff():
    p = enrich_pick(2, None, CURRENT_SEASON + 2)
    assert p["eff_value"] == 0.0
    assert p["eff_cap_hit"] == 0.0


# ---------------------------------------------------------------------------
# End-to-end: team with owned picks has higher value and higher cap burden
# ---------------------------------------------------------------------------


def test_team_with_picks_has_higher_value_than_team_without():
    """Owning a current-year pick increases a team's total effective value."""
    base_player_value = 50.0

    # Team A: players only
    team_a_value = base_player_value

    # Team B: players + one 1.01 current-year pick
    pick_r1_s1 = enrich_pick(1, 1, CURRENT_SEASON)
    team_b_value = base_player_value + pick_r1_s1["eff_value"]

    assert team_b_value > team_a_value


def test_team_with_picks_has_higher_cap_burden():
    """Owning a current-year pick increases a team's effective cap burden."""
    # Team with 1.01 pick
    pick_r1_s1 = enrich_pick(1, 1, CURRENT_SEASON)
    assert pick_r1_s1["eff_cap_hit"] > 0


def test_pick_cap_burden_reduces_available_cap():
    """Available cap is correctly reduced by pick cap burden.

    Simulates the JS logic:
      cap_remaining_after_picks = max(cap_remaining - pick_cap_burden, 0)
    """
    base_cap = 300.0
    current_cap_usage = 250.0
    cap_remaining = base_cap - current_cap_usage  # 50

    pick = enrich_pick(1, 1, CURRENT_SEASON)
    cap_after_picks = max(cap_remaining - pick["eff_cap_hit"], 0)

    # Pick cap burden is at most full value_1yr (14), so cap_after_picks < cap_remaining
    assert cap_after_picks < cap_remaining
    assert cap_after_picks >= 0


def test_multiple_picks_aggregate_correctly():
    """Summing eff_cap_hit across multiple owned picks gives the team's total burden."""
    picks = [
        enrich_pick(1, 3, CURRENT_SEASON),   # current-year R1 slot 3
        enrich_pick(2, 1, CURRENT_SEASON),   # current-year R2 slot 1
        enrich_pick(1, 1, CURRENT_SEASON + 1),  # future-year R1 slot 1 → 0
    ]
    total_eff_cap = sum(p["eff_cap_hit"] for p in picks)
    # Only the two current-year picks contribute
    assert total_eff_cap > 0
    # The future-year pick adds nothing
    assert picks[2]["eff_cap_hit"] == 0.0
    # Total matches sum of the two current-year values individually
    expected = picks[0]["eff_cap_hit"] + picks[1]["eff_cap_hit"]
    assert abs(total_eff_cap - expected) < 1e-9


# ---------------------------------------------------------------------------
# Activation probability flows through correctly
# ---------------------------------------------------------------------------


def test_p_activate_field_present_and_reasonable():
    for rnd, slot in [(1, 1), (1, 10), (2, 5), (4, 10)]:
        p = enrich_pick(rnd, slot, CURRENT_SEASON)
        assert 0.0 < p["p_activate"] <= 1.0, (
            f"p_activate={p['p_activate']} out of range for round={rnd} slot={slot}"
        )


def test_r1_slot1_p_activate_highest():
    """1.01 has a higher activation probability than any other pick."""
    p_top = enrich_pick(1, 1, CURRENT_SEASON)["p_activate"]
    for rnd in range(1, 5):
        for slot in range(1, 11):
            if rnd == 1 and slot == 1:
                continue
            p = enrich_pick(rnd, slot, CURRENT_SEASON)["p_activate"]
            assert p_top >= p


def test_eff_cap_formula_matches_manual():
    """eff_cap = p_activate * full_cap + (1 - p_activate) * ps_cap."""
    p = enrich_pick(1, 4, CURRENT_SEASON)
    full_cap = p["value_1yr"]
    ps_cap = 0.25 * full_cap
    expected = p["p_activate"] * full_cap + (1 - p["p_activate"]) * ps_cap
    assert abs(p["eff_cap_hit"] - expected) < 1e-9
