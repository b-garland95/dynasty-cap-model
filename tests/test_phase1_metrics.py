"""Direct unit tests for phase1_metrics: aggregate_sav and compute_dollar_values."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.utils.config import load_league_config
from src.valuation.phase1_metrics import aggregate_sav, compute_dollar_values


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_started_weekly(seasons: list[int] | None = None, n_weeks: int = 4) -> pd.DataFrame:
    """Minimal started_weekly fixture: deterministic wmsv for each player-week."""
    if seasons is None:
        seasons = [2024]
    rows = []
    for season in seasons:
        for week in range(1, n_weeks + 1):
            for i, (pos, pts, msv) in enumerate(
                [("QB1", 25.0, 8.0), ("QB2", 20.0, 3.0),
                 ("RB1", 18.0, 5.0), ("RB2", 12.0, 0.0)]
            ):
                rows.append({
                    "season": season,
                    "week": week,
                    "gsis_id": f"G-{pos}",
                    "player": pos,
                    "position": pos[:2],
                    "points": pts,
                    "wmsv": msv,
                    "wdrag": 0.0 if msv > 0 else -2.0,
                    "margin": msv if msv > 0 else -2.0,
                    "assigned_slot": "QB" if pos.startswith("Q") else "RB",
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# aggregate_sav
# ---------------------------------------------------------------------------

def test_aggregate_sav_sav_equals_sum_of_wmsv():
    df = _make_started_weekly(n_weeks=3)
    sav = aggregate_sav(df)

    for (season, gsis_id), group in df.groupby(["season", "gsis_id"]):
        expected = group["wmsv"].sum()
        row = sav[(sav["season"] == season) & (sav["gsis_id"] == gsis_id)]
        assert len(row) == 1
        assert math.isclose(float(row["sav"].iloc[0]), expected, abs_tol=1e-9)


def test_aggregate_sav_is_nonnegative():
    """SAV = sum of wmsv = sum of max(0, margin) — always non-negative."""
    sav = aggregate_sav(_make_started_weekly())
    assert (sav["sav"] >= 0).all()


def test_aggregate_sav_weeks_started_count():
    df = _make_started_weekly(n_weeks=5)
    sav = aggregate_sav(df)
    # Each player appears in every week, so weeks_started_in_leaguewide_set == n_weeks
    assert (sav["weeks_started_in_leaguewide_set"] == 5).all()


def test_aggregate_sav_multi_season():
    df = _make_started_weekly(seasons=[2023, 2024], n_weeks=2)
    sav = aggregate_sav(df)
    # Should produce one row per (season, player)
    assert set(sav["season"].unique()) == {2023, 2024}
    assert len(sav) == 4 * 2  # 4 players × 2 seasons


def test_aggregate_sav_without_gsis_id_uses_player_name():
    df = _make_started_weekly().drop(columns=["gsis_id"])
    sav = aggregate_sav(df)
    assert "player" in sav.columns
    assert len(sav) > 0


def test_aggregate_sav_empty_input_returns_empty():
    empty = pd.DataFrame(columns=["season", "gsis_id", "player", "position",
                                   "points", "wmsv", "wdrag", "margin", "assigned_slot"])
    sav = aggregate_sav(empty)
    assert len(sav) == 0


# ---------------------------------------------------------------------------
# compute_dollar_values
# ---------------------------------------------------------------------------

def test_compute_dollar_values_sum_to_total_cap():
    """Sum of player dollar_values must equal base_cap × n_teams each season."""
    config = load_league_config()
    df = _make_started_weekly(seasons=[2023, 2024])
    sav = aggregate_sav(df)
    sav["esv"] = sav["sav"]  # ESV = SAV for this test
    sav["ld"] = 0.0
    sav["cg"] = 0.0
    df["esv_week"] = df["wmsv"]

    season_values, _ = compute_dollar_values(sav, df, config)
    expected_cap = float(config["cap"]["base_cap"]) * int(config["league"]["teams"])

    for season, group in season_values.groupby("season"):
        total = group["dollar_value"].sum()
        assert math.isclose(total, expected_cap, rel_tol=1e-6), (
            f"Season {season}: sum {total:.2f} != {expected_cap}"
        )


def test_compute_dollar_values_proportional_to_esv():
    """A player with 2× the ESV must get exactly 2× the dollar value."""
    config = load_league_config()
    sv = pd.DataFrame([
        {"season": 2024, "gsis_id": "A", "player": "A", "sav": 10.0, "esv": 10.0, "ld": 0.0, "cg": 0.0},
        {"season": 2024, "gsis_id": "B", "player": "B", "sav": 5.0, "esv": 5.0, "ld": 0.0, "cg": 0.0},
    ])
    df = pd.DataFrame([
        {"season": 2024, "gsis_id": "A", "player": "A", "wmsv": 10.0, "points": 10.0, "esv_week": 10.0},
        {"season": 2024, "gsis_id": "B", "player": "B", "wmsv": 5.0, "points": 5.0, "esv_week": 5.0},
    ])
    sv_out, _ = compute_dollar_values(sv, df, config)
    dv_a = float(sv_out.loc[sv_out["gsis_id"] == "A", "dollar_value"].iloc[0])
    dv_b = float(sv_out.loc[sv_out["gsis_id"] == "B", "dollar_value"].iloc[0])
    assert math.isclose(dv_a / dv_b, 2.0, rel_tol=1e-9)
