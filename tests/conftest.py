"""Shared pytest fixtures for the dynasty-cap-model test suite.

Import fixtures in tests via normal pytest discovery (no explicit import needed).
Helper functions that build synthetic DataFrames are also exposed here so test
files can import them directly rather than each defining their own copy.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.utils.config import load_league_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def league_config() -> dict:
    """Load and validate league config once per test session."""
    return load_league_config()


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixture_roster_path() -> str:
    """Absolute path to the tiny 5-player fixture roster CSV."""
    return str(FIXTURES_DIR / "tiny_roster.csv")


# ---------------------------------------------------------------------------
# Synthetic data helpers (importable functions, not fixtures)
# ---------------------------------------------------------------------------

def make_player_pool(
    n_qb: int = 12,
    n_rb: int = 30,
    n_wr: int = 45,
    n_te: int = 18,
    weeks: list[int] | None = None,
    season: int = 2024,
    with_gsis_id: bool = True,
) -> pd.DataFrame:
    """Build a synthetic weekly player pool covering regular-season weeks.

    Points decrease by index so higher-numbered players are unambiguously
    weaker, making slot assignments deterministic.
    """
    if weeks is None:
        weeks = list(range(1, 15))

    rows: list[dict] = []
    for week in weeks:
        for pos, n, base_pts in [("QB", n_qb, 30.0), ("RB", n_rb, 20.0),
                                  ("WR", n_wr, 15.0), ("TE", n_te, 12.0)]:
            for i in range(1, n + 1):
                row: dict = {
                    "season": season,
                    "week": week,
                    "player": f"{pos}{i}",
                    "position": pos,
                    "points": max(0.0, base_pts - i + 1 - 0.1 * (week - 1)),
                    "projected_points": max(0.0, base_pts - i + 1),
                }
                if with_gsis_id:
                    row["gsis_id"] = f"G-{pos}{i}"
                rows.append(row)
    return pd.DataFrame(rows)


def make_adp_df(
    n_qb: int = 12,
    n_rb: int = 30,
    n_wr: int = 45,
    n_te: int = 18,
    season: int = 2024,
) -> pd.DataFrame:
    """Build a synthetic ADP DataFrame matching make_player_pool player IDs."""
    rows: list[dict] = []
    rank = 1
    for pos, n in [("QB", n_qb), ("RB", n_rb), ("WR", n_wr), ("TE", n_te)]:
        for i in range(1, n + 1):
            rows.append({
                "season": season,
                "player": f"{pos}{i}",
                "position": pos,
                "rank": rank,
                "gsis_id": f"G-{pos}{i}",
            })
            rank += 1
    return pd.DataFrame(rows)
