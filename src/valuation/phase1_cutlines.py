from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

SLOTS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FLEX", "SF")


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


def compute_season_base_cutlines(raw_cutlines_by_week: list[dict[str, float]]) -> dict[str, float]:
    """Compute season base cutlines as the median raw cutline for each slot."""
    if not raw_cutlines_by_week:
        raise ValueError("raw_cutlines_by_week must contain at least one week")

    return {
        slot: float(median(week_cutlines[slot] for week_cutlines in raw_cutlines_by_week))
        for slot in SLOTS
    }


def apply_shrinkage(
    raw_cutlines: dict[str, float],
    base_cutlines: dict[str, float],
    config: dict[str, Any],
) -> dict[str, float]:
    """Apply per-slot shrinkage from weekly raw cutlines toward season base cutlines."""
    lambdas = config["valuation"]["shrinkage_lambdas"]
    return {
        slot: float(lambdas[slot]) * float(base_cutlines[slot])
        + (1.0 - float(lambdas[slot])) * float(raw_cutlines[slot])
        for slot in SLOTS
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
