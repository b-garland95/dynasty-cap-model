"""
Tests for src/contracts/roster_adjusted_value.py

All tests use synthetic DataFrames with explicit availability_rates so results
are fully deterministic and don't depend on the processed CSV on disk.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from src.contracts.roster_adjusted_value import (
    assign_team_lineup,
    build_team_rav_summary,
    build_trade_gap_screen,
    compute_depth_discounts,
    compute_rav,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

AVAILABILITY_RATES = {
    "QB": 0.75,   # absence 0.25
    "RB": 0.70,   # absence 0.30
    "WR": 0.75,   # absence 0.25
    "TE": 0.72,   # absence 0.28
}

REGULAR_SEASON_WEEKS = 17
FLOOR = 0.01

CONFIG = {
    "lineup": {
        "qb": 1,
        "rb": 2,
        "wr": 3,
        "te": 1,
        "flex": 2,
        "superflex": 1,
    },
    "rav": {
        "regular_season_weeks": REGULAR_SEASON_WEEKS,
        "bench_depth_2plus_floor": FLOOR,
    },
}


def _kermit_roster() -> pd.DataFrame:
    """Synthetic roster modelled on Kermit's actual situation: 3 QBs, thin elsewhere."""
    return pd.DataFrame([
        {"player": "Josh Allen",       "team": "Kermit", "position": "QB", "tv_y0": 111.40, "cap_y0": 70.0, "surplus_y0": 41.40},
        {"player": "Trevor Lawrence",  "team": "Kermit", "position": "QB", "tv_y0":  56.44, "cap_y0": 36.0, "surplus_y0": 20.44},
        {"player": "Tyler Shough",     "team": "Kermit", "position": "QB", "tv_y0":  40.64, "cap_y0":  2.0, "surplus_y0": 38.64},
        {"player": "Josh Jacobs",      "team": "Kermit", "position": "RB", "tv_y0":  28.54, "cap_y0": 40.0, "surplus_y0": -11.46},
        {"player": "Chuba Hubbard",    "team": "Kermit", "position": "RB", "tv_y0":  14.16, "cap_y0": 39.0, "surplus_y0": -24.84},
        {"player": "DJ Giddens",       "team": "Kermit", "position": "RB", "tv_y0":  -0.11, "cap_y0":  1.0, "surplus_y0": -1.11},
        {"player": "Jaylen Waddle",    "team": "Kermit", "position": "WR", "tv_y0":  24.13, "cap_y0": 28.0, "surplus_y0": -3.87},
        {"player": "Adonai Mitchell",  "team": "Kermit", "position": "WR", "tv_y0":   0.08, "cap_y0":  2.0, "surplus_y0": -1.92},
        {"player": "Pat Bryant",       "team": "Kermit", "position": "WR", "tv_y0":  -4.87, "cap_y0":  1.0, "surplus_y0": -5.87},
        {"player": "Troy Franklin",    "team": "Kermit", "position": "WR", "tv_y0":  -4.87, "cap_y0":  4.0, "surplus_y0": -8.87},
        {"player": "George Kittle",    "team": "Kermit", "position": "TE", "tv_y0":  -0.07, "cap_y0": 14.0, "surplus_y0": -14.07},
        {"player": "Ben Sinnott",      "team": "Kermit", "position": "TE", "tv_y0": -10.78, "cap_y0":  1.0, "surplus_y0": -11.78},
    ])


def _simple_roster(team: str = "Alpha") -> pd.DataFrame:
    """Minimal roster: 1 QB, 3 RBs, 4 WRs, 2 TEs — enough to fill all slots."""
    return pd.DataFrame([
        {"player": "QB1",  "team": team, "position": "QB", "tv_y0": 80.0,  "cap_y0": 40.0, "surplus_y0": 40.0},
        {"player": "QB2",  "team": team, "position": "QB", "tv_y0": 50.0,  "cap_y0": 20.0, "surplus_y0": 30.0},
        {"player": "QB3",  "team": team, "position": "QB", "tv_y0": 20.0,  "cap_y0":  5.0, "surplus_y0": 15.0},
        {"player": "RB1",  "team": team, "position": "RB", "tv_y0": 60.0,  "cap_y0": 30.0, "surplus_y0": 30.0},
        {"player": "RB2",  "team": team, "position": "RB", "tv_y0": 40.0,  "cap_y0": 20.0, "surplus_y0": 20.0},
        {"player": "RB3",  "team": team, "position": "RB", "tv_y0": 30.0,  "cap_y0": 10.0, "surplus_y0": 20.0},
        {"player": "WR1",  "team": team, "position": "WR", "tv_y0": 55.0,  "cap_y0": 25.0, "surplus_y0": 30.0},
        {"player": "WR2",  "team": team, "position": "WR", "tv_y0": 35.0,  "cap_y0": 15.0, "surplus_y0": 20.0},
        {"player": "WR3",  "team": team, "position": "WR", "tv_y0": 25.0,  "cap_y0": 10.0, "surplus_y0": 15.0},
        {"player": "WR4",  "team": team, "position": "WR", "tv_y0":  5.0,  "cap_y0":  2.0, "surplus_y0":  3.0},
        {"player": "TE1",  "team": team, "position": "TE", "tv_y0": 28.0,  "cap_y0": 12.0, "surplus_y0": 16.0},
        {"player": "TE2",  "team": team, "position": "TE", "tv_y0": 10.0,  "cap_y0":  4.0, "surplus_y0":  6.0},
    ])


# ---------------------------------------------------------------------------
# compute_depth_discounts
# ---------------------------------------------------------------------------

def test_compute_depth_discounts_qb_uses_double_bye():
    discounts = compute_depth_discounts(AVAILABILITY_RATES, REGULAR_SEASON_WEEKS, FLOOR)
    qb_d0 = discounts["QB"][0]
    rb_d0 = discounts["RB"][0]
    # QB bench depth 0 should be strictly larger (covers 2 starters' byes)
    assert qb_d0 > rb_d0, f"QB d0={qb_d0:.4f} should exceed RB d0={rb_d0:.4f}"


def test_compute_depth_discounts_depth1_less_than_depth0():
    discounts = compute_depth_discounts(AVAILABILITY_RATES, REGULAR_SEASON_WEEKS, FLOOR)
    for pos in ["QB", "RB", "WR", "TE"]:
        d0, d1, d2 = discounts[pos]
        assert d0 > d1, f"{pos}: depth-0 discount {d0:.4f} should exceed depth-1 {d1:.4f}"
        assert d1 >= d2, f"{pos}: depth-1 discount {d1:.4f} should be >= depth-2+ floor {d2:.4f}"


def test_compute_depth_discounts_floor_applied_at_depth2():
    discounts = compute_depth_discounts(AVAILABILITY_RATES, REGULAR_SEASON_WEEKS, FLOOR)
    for pos in ["QB", "RB", "WR", "TE"]:
        assert math.isclose(discounts[pos][2], FLOOR), f"{pos} depth-2+ should equal floor"


def test_compute_depth_discounts_formula_values():
    discounts = compute_depth_discounts(AVAILABILITY_RATES, REGULAR_SEASON_WEEKS, FLOOR)
    bye = 1 / REGULAR_SEASON_WEEKS
    # RB: absence = 0.30
    rb_absence = 1 - AVAILABILITY_RATES["RB"]
    assert math.isclose(discounts["RB"][0], bye + rb_absence, rel_tol=1e-9)
    assert math.isclose(discounts["RB"][1], rb_absence ** 2, rel_tol=1e-9)
    # QB: absence = 0.25
    qb_absence = 1 - AVAILABILITY_RATES["QB"]
    assert math.isclose(discounts["QB"][0], 2 * bye + qb_absence, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# assign_team_lineup
# ---------------------------------------------------------------------------

def test_kermit_qb3_gets_bench_slot():
    team_df = _kermit_roster()
    assigned = assign_team_lineup(team_df, CONFIG)
    # Sorted by tv_y0: Allen=QB slot, Lawrence=SF slot, Shough=bench
    allen = assigned.loc[assigned["player"] == "Josh Allen"].iloc[0]
    lawrence = assigned.loc[assigned["player"] == "Trevor Lawrence"].iloc[0]
    shough = assigned.loc[assigned["player"] == "Tyler Shough"].iloc[0]
    assert allen["rav_slot"] == "QB"
    assert allen["started"] is True or allen["started"] == True
    assert lawrence["started"] is True or lawrence["started"] == True
    assert shough["rav_slot"] == "bench"
    assert shough["started"] is False or shough["started"] == False
    assert shough["bench_depth"] == 0


def test_starters_get_full_discount():
    roster = _simple_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    starters = result[result["started"]]
    for _, row in starters.iterrows():
        assert math.isclose(row["depth_discount"], 1.0), f"{row['player']} starter should have discount=1.0"
        assert math.isclose(row["rav_y0"], row["tv_y0"]), f"{row['player']} rav_y0 should equal tv_y0"


def test_flex_resolves_best_remaining():
    """RB3 (tv=30) should win the FLEX slot over WR4 (tv=5)."""
    roster = _simple_roster()
    assigned = assign_team_lineup(roster, CONFIG)
    rb3 = assigned.loc[assigned["player"] == "RB3"].iloc[0]
    wr4 = assigned.loc[assigned["player"] == "WR4"].iloc[0]
    assert rb3["started"] is True or rb3["started"] == True, "RB3 should start in FLEX"
    assert wr4["started"] is False or wr4["started"] == False, "WR4 should be bench"


def test_bench_depth_ordering_within_position():
    """bench_depth should increase for lower tv_y0 bench players of the same position."""
    roster = _simple_roster()
    assigned = assign_team_lineup(roster, CONFIG)
    # WRs: WR1/WR2/WR3 start; RB3 takes FLEX; WR4 is bench_depth=0 among WRs
    wr4 = assigned.loc[assigned["player"] == "WR4"].iloc[0]
    assert not (wr4["started"] is True or wr4["started"] == True)
    assert wr4["bench_depth"] == 0


# ---------------------------------------------------------------------------
# compute_rav
# ---------------------------------------------------------------------------

def test_trade_gap_equals_tv_minus_rav():
    roster = _simple_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    for _, row in result.iterrows():
        expected = row["tv_y0"] - row["rav_y0"]
        assert math.isclose(row["trade_gap_y0"], expected, rel_tol=1e-9), (
            f"{row['player']}: trade_gap {row['trade_gap_y0']:.4f} != tv-rav {expected:.4f}"
        )


def test_negative_tv_bench_player_sign_preserved():
    """A bench player with negative tv_y0 should have negative rav_y0 (sign preserved)."""
    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    # Ben Sinnott: tv_y0 = -10.78, should be bench (Kittle is the TE starter)
    sinnott = result.loc[result["player"] == "Ben Sinnott"].iloc[0]
    assert sinnott["started"] is False or sinnott["started"] == False
    assert sinnott["rav_y0"] < 0, "Negative TV bench player should have negative RAV"


def test_qb_bench_discount_applied():
    """Shough (QB3 bench) should get the QB depth-0 discount."""
    discounts = compute_depth_discounts(AVAILABILITY_RATES, REGULAR_SEASON_WEEKS, FLOOR)
    expected_discount = discounts["QB"][0]

    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    shough = result.loc[result["player"] == "Tyler Shough"].iloc[0]

    assert math.isclose(shough["depth_discount"], expected_discount, rel_tol=1e-9)
    assert math.isclose(shough["rav_y0"], 40.64 * expected_discount, rel_tol=1e-6)


def test_depth1_bench_gets_smaller_discount_than_depth0():
    """The second bench player at a position should have a smaller discount than the first."""
    roster = _simple_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    # QB2 fills SF; QB3 is bench_depth=0. QB1 fills QB slot. No QB bench_depth=1 in this roster.
    # Use RBs: RB3 fills FLEX, so no RB bench players here.
    # Add a 4th RB to force RB bench_depth=1.
    extra = pd.concat([roster, pd.DataFrame([{
        "player": "RB4", "team": "Alpha", "position": "RB", "tv_y0": 5.0, "cap_y0": 1.0, "surplus_y0": 4.0,
    }])], ignore_index=True)
    result2 = compute_rav(extra, CONFIG, AVAILABILITY_RATES)
    rb3 = result2.loc[result2["player"] == "RB3"].iloc[0]
    rb4 = result2.loc[result2["player"] == "RB4"].iloc[0]
    # RB3 goes to FLEX (started), RB4 is bench_depth=0
    assert rb3["started"] is True or rb3["started"] == True
    # RB4 is bench_depth=0; if we want depth 1 we need 5 RBs
    extra2 = pd.concat([extra, pd.DataFrame([{
        "player": "RB5", "team": "Alpha", "position": "RB", "tv_y0": 2.0, "cap_y0": 1.0, "surplus_y0": 1.0,
    }])], ignore_index=True)
    result3 = compute_rav(extra2, CONFIG, AVAILABILITY_RATES)
    rb4_r = result3.loc[result3["player"] == "RB4"].iloc[0]
    rb5_r = result3.loc[result3["player"] == "RB5"].iloc[0]
    assert rb4_r["bench_depth"] == 0
    assert rb5_r["bench_depth"] == 1
    assert rb4_r["depth_discount"] > rb5_r["depth_discount"]


# ---------------------------------------------------------------------------
# build_team_rav_summary
# ---------------------------------------------------------------------------

def test_team_rav_summary_totals_match_per_player():
    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    summary = build_team_rav_summary(result)
    kermit_summary = summary.loc[summary["team"] == "Kermit"].iloc[0]

    expected_total_rav = result.loc[result["team"] == "Kermit", "rav_y0"].sum()
    assert math.isclose(kermit_summary["total_rav_y0"], expected_total_rav, rel_tol=1e-9)

    expected_total_tv = result.loc[result["team"] == "Kermit", "tv_y0"].sum()
    assert math.isclose(kermit_summary["total_tv_y0"], expected_total_tv, rel_tol=1e-9)


def test_team_rav_summary_rav_less_than_tv():
    """RAV total should be less than raw TV total when there are bench players."""
    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    summary = build_team_rav_summary(result)
    kermit = summary.loc[summary["team"] == "Kermit"].iloc[0]
    assert kermit["total_rav_y0"] < kermit["total_tv_y0"]


# ---------------------------------------------------------------------------
# build_trade_gap_screen
# ---------------------------------------------------------------------------

def test_trade_gap_screen_bench_only():
    """Trade gap screen should contain only players where started=False."""
    roster = _simple_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    screen = build_trade_gap_screen(result)
    assert len(screen) > 0
    assert screen["started"].sum() == 0, "Trade gap screen should only contain bench players"


def test_trade_gap_screen_sorted_descending():
    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    screen = build_trade_gap_screen(result)
    gaps = screen["trade_gap_y0"].tolist()
    assert gaps == sorted(gaps, reverse=True), "Trade gap screen must be sorted descending"


def test_shough_near_top_of_trade_gap_screen():
    """Shough has the highest tv_y0 on the bench — should be first in the screen."""
    roster = _kermit_roster()
    result = compute_rav(roster, CONFIG, AVAILABILITY_RATES)
    screen = build_trade_gap_screen(result)
    assert screen.iloc[0]["player"] == "Tyler Shough", (
        f"Expected Shough first, got {screen.iloc[0]['player']}"
    )
