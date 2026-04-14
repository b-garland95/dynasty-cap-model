"""Direct unit tests for phase1_par: replacement levels and PAR by player."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.utils.config import load_league_config
from src.valuation.phase1_par import (
    compute_par_by_player,
    compute_position_replacement_level_par,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _points_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _weekly_qb_pool(n: int = 12, n_weeks: int = 4, season: int = 2024) -> pd.DataFrame:
    """Build a minimal QB pool for PAR testing."""
    rows = []
    for week in range(1, n_weeks + 1):
        for i in range(1, n + 1):
            rows.append({
                "season": season,
                "week": week,
                "gsis_id": f"QB{i}",
                "player": f"QB{i}",
                "position": "QB",
                "points": float(30 - i),  # QB1 scores 29, QB2 scores 28, ...
            })
    return pd.DataFrame(rows)


def _full_pool(season: int = 2024, n_weeks: int = 2) -> pd.DataFrame:
    """Build a player pool for all 4 positions with enough depth to exceed requirements."""
    config = load_league_config()
    teams = int(config["league"]["teams"])
    lineup = config["lineup"]
    # Need at least teams * n starters per position
    needed = {
        "QB": teams * int(lineup["qb"]) + 5,
        "RB": teams * int(lineup["rb"]) + 5,
        "WR": teams * int(lineup["wr"]) + 5,
        "TE": teams * int(lineup["te"]) + 5,
    }
    rows = []
    for week in range(1, n_weeks + 1):
        for pos, n in needed.items():
            base = {"QB": 25.0, "RB": 18.0, "WR": 14.0, "TE": 10.0}[pos]
            for i in range(1, n + 1):
                rows.append({
                    "season": season,
                    "week": week,
                    "gsis_id": f"{pos}{i}",
                    "player": f"{pos}{i}",
                    "position": pos,
                    "points": max(0.0, base - i + 1),
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# compute_position_replacement_level_par
# ---------------------------------------------------------------------------

def test_par_replacement_level_is_nth_player_median():
    """Replacement level for QBs = median of weekly Nth QB score across weeks."""
    config = load_league_config()
    teams = int(config["league"]["teams"])
    n_qb_starters = teams * int(config["lineup"]["qb"])
    df = _full_pool(n_weeks=6)

    r_par = compute_position_replacement_level_par(df, config)

    # Verify QB replacement level is roughly the score of the last starter
    # (QB1 = 25, QB2 = 24, ... QBn = 25 - n + 1)
    expected_qb_repl = max(0.0, 25.0 - n_qb_starters + 1)
    assert math.isclose(r_par["QB"], expected_qb_repl, abs_tol=0.5), (
        f"QB replacement level {r_par['QB']:.2f} != expected {expected_qb_repl:.2f}"
    )


def test_par_replacement_level_all_positions_present():
    config = load_league_config()
    df = _full_pool(n_weeks=3)
    r_par = compute_position_replacement_level_par(df, config)
    for pos in ("QB", "RB", "WR", "TE"):
        assert pos in r_par, f"Missing PAR replacement level for {pos}"
        assert r_par[pos] >= 0.0


def test_par_raises_when_insufficient_players():
    """Should raise ValueError if pool is too shallow for required starters."""
    config = load_league_config()
    # Build a pool with only 1 player per position (far below minimum required)
    df = pd.DataFrame([
        {"season": 2024, "week": 1, "gsis_id": "QB1", "player": "QB1",
         "position": "QB", "points": 20.0},
        {"season": 2024, "week": 1, "gsis_id": "RB1", "player": "RB1",
         "position": "RB", "points": 15.0},
        {"season": 2024, "week": 1, "gsis_id": "WR1", "player": "WR1",
         "position": "WR", "points": 12.0},
        {"season": 2024, "week": 1, "gsis_id": "TE1", "player": "TE1",
         "position": "TE", "points": 8.0},
    ])
    with pytest.raises(ValueError, match="Insufficient players for PAR"):
        compute_position_replacement_level_par(df, config)


# ---------------------------------------------------------------------------
# compute_par_by_player
# ---------------------------------------------------------------------------

def test_par_by_player_is_sum_of_weekly_par():
    """Season PAR = sum of (points - r_par) per week."""
    df = _full_pool(n_weeks=3)
    config = load_league_config()
    r_par = compute_position_replacement_level_par(df, config)
    par_df = compute_par_by_player(df, r_par)

    assert "par" in par_df.columns
    assert "total_points" in par_df.columns
    assert len(par_df) > 0

    # Spot-check: QB1 should have par = 3 * (25 - QB_replacement_level)
    qb_repl = r_par["QB"]
    qb1_par = float(par_df.loc[par_df["gsis_id"] == "QB1", "par"].iloc[0])
    expected = 3 * (25.0 - qb_repl)  # 3 weeks × margin
    assert math.isclose(qb1_par, expected, abs_tol=1e-6)


def test_par_total_points_matches_sum_of_weekly_points():
    df = _full_pool(n_weeks=2)
    config = load_league_config()
    r_par = compute_position_replacement_level_par(df, config)
    par_df = compute_par_by_player(df, r_par)

    for gsis_id, group in df.groupby("gsis_id"):
        expected_total = group["points"].sum()
        actual = float(par_df.loc[par_df["gsis_id"] == gsis_id, "total_points"].iloc[0])
        assert math.isclose(actual, expected_total, abs_tol=1e-9)
