from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

SLOTS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FLEX", "SF")
POSITIONS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


def compute_weekly_raw_cutlines(week_df: pd.DataFrame, config: dict[str, Any]) -> dict[str, float]:
    """Compute deterministic weekly raw cutlines by slot."""
    teams = int(config["league"]["teams"])
    lineup = config["lineup"]
    required_counts = {
        "QB": teams * int(lineup["qb"]),
        "RB": teams * int(lineup["rb"]),
        "WR": teams * int(lineup["wr"]),
        "TE": teams * int(lineup["te"]),
        "FLEX": teams * int(lineup["flex"]),
        "SF": teams * int(lineup["superflex"]),
    }

    remaining = week_df.copy()
    cutlines: dict[str, float] = {}

    cutlines["QB"], remaining = _take_top_players(remaining, ["QB"], required_counts["QB"], "QB")
    cutlines["RB"], remaining = _take_top_players(remaining, ["RB"], required_counts["RB"], "RB")
    cutlines["WR"], remaining = _take_top_players(remaining, ["WR"], required_counts["WR"], "WR")
    cutlines["TE"], remaining = _take_top_players(remaining, ["TE"], required_counts["TE"], "TE")
    cutlines["FLEX"], remaining = _take_top_players(
        remaining,
        ["RB", "WR", "TE"],
        required_counts["FLEX"],
        "FLEX",
    )
    cutlines["SF"], _ = _take_top_players(
        remaining,
        ["QB", "RB", "WR", "TE"],
        required_counts["SF"],
        "SF",
    )
    return cutlines


def compute_position_cutlines(started_df: pd.DataFrame) -> dict[str, float]:
    """Compute position-level cutlines from the leaguewide starting set.

    The position cutline for a given position is the minimum points scored
    by any starter of that position, regardless of which slot they were
    assigned to (e.g. a QB starting in the SF slot contributes to the QB
    position cutline).
    """
    cutlines: dict[str, float] = {}
    for pos in POSITIONS:
        pos_starters = started_df[started_df["position"] == pos]
        if pos_starters.empty:
            raise ValueError(f"No starters found for position {pos}")
        cutlines[pos] = float(pos_starters["points"].min())
    return cutlines


def compute_season_base_cutlines(
    raw_cutlines_by_week: list[dict[str, float]],
    keys: tuple[str, ...] = SLOTS,
) -> dict[str, float]:
    """Compute season base cutlines as the median raw cutline for each key."""
    if not raw_cutlines_by_week:
        raise ValueError("raw_cutlines_by_week must contain at least one week")

    return {
        key: float(median(week_cutlines[key] for week_cutlines in raw_cutlines_by_week))
        for key in keys
    }


def apply_shrinkage(
    raw_cutlines: dict[str, float],
    base_cutlines: dict[str, float],
    config: dict[str, Any],
    keys: tuple[str, ...] = SLOTS,
) -> dict[str, float]:
    """Apply per-key shrinkage from weekly raw cutlines toward season base cutlines."""
    lambdas = config["valuation"]["shrinkage_lambdas"]
    return {
        key: float(lambdas[key]) * float(base_cutlines[key])
        + (1.0 - float(lambdas[key])) * float(raw_cutlines[key])
        for key in keys
    }


def _take_top_players(
    remaining: pd.DataFrame,
    eligible_positions: list[str],
    required_count: int,
    slot_name: str,
) -> tuple[float, pd.DataFrame]:
    eligible = remaining[remaining["position"].isin(eligible_positions)].sort_values(
        "points",
        ascending=False,
    )
    if len(eligible) < required_count:
        raise ValueError(f"Insufficient eligible players for slot {slot_name}: need {required_count}, found {len(eligible)}")

    chosen = eligible.head(required_count)
    cutline = float(chosen["points"].iloc[-1])
    updated_remaining = remaining.drop(index=chosen.index)
    return cutline, updated_remaining
