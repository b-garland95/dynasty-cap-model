"""Tests for market_salary: normal operation and bad-denominator warning."""

from __future__ import annotations

import math
import warnings

import pandas as pd
import pytest

from src.utils.config import load_league_config
from src.valuation.market_salary import compute_market_salary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adp_df(n: int = 30, season: int = 2024) -> pd.DataFrame:
    """Build a synthetic ADP frame with enough ranked players to fill top_k."""
    rows = []
    for pos, count in [("QB", n // 4), ("RB", n // 2), ("WR", n // 3), ("TE", n // 6)]:
        for i in range(1, count + 1):
            rows.append({
                "season": season,
                "gsis_id": f"{pos}{i}",
                "player": f"{pos}{i}",
                "position": pos,
                "rank": len(rows) + 1,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Normal operation
# ---------------------------------------------------------------------------

def test_market_salary_adds_market_salary_column():
    config = load_league_config()
    df = _adp_df(n=100)
    result = compute_market_salary(df, config)
    assert "market_salary" in result.columns
    assert (result["market_salary"] > 0).all()


def test_market_salary_higher_for_lower_rank():
    """Player ranked 1st should have higher market salary than player ranked 20th."""
    config = load_league_config()
    df = _adp_df(n=100)
    result = compute_market_salary(df, config).sort_values("adp_rank_within_season")
    salaries = result["market_salary"].values
    # Generally decreasing; at minimum, first is higher than last
    assert salaries[0] > salaries[-1]


def test_market_salary_empty_input_returns_empty():
    config = load_league_config()
    df = pd.DataFrame(columns=["season", "gsis_id", "player", "position", "rank"])
    result = compute_market_salary(df, config)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Bad denominator → warning + NaN
# ---------------------------------------------------------------------------

def test_market_salary_zero_denominator_warns_and_returns_nan():
    """When ADP pool has 0 players in the top_k, emit RuntimeWarning and produce NaN."""
    config = load_league_config()
    # A single player — top_k (teams × active_spots) >> 1, so sum(s_raw.head(top_k)) ≈ s_raw[0]
    # Force the issue by creating an empty DataFrame that still has a season key
    empty_df = pd.DataFrame([
        {"season": 2024, "gsis_id": "X1", "player": "X1", "position": "QB", "rank": 0}
    ])
    # rank=0 → adp_rank_within_season=1 → s_raw = (1/1)^beta > 0, so denominator won't be 0
    # Instead: mock a degenerate case by using a rank of -1 to get s_raw=0
    # The real way to trigger zero denom is an empty pool.
    # Use a config with active_roster_spots=0 to force top_k=0.
    import copy
    cfg = copy.deepcopy(config)
    cfg["capture_model"]["roster_model"]["active_roster_spots_per_team"] = 0

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = compute_market_salary(_adp_df(n=30), cfg)

    runtime_warns = [x for x in w if issubclass(x.category, RuntimeWarning)]
    assert len(runtime_warns) >= 1, "Expected RuntimeWarning for zero denominator"
    assert result["market_salary"].isna().all()
