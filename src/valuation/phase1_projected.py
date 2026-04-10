from __future__ import annotations

from typing import Any

import pandas as pd

from src.valuation.phase1_assignment import assign_leaguewide_starting_set
from src.valuation.phase1_cutlines import compute_weekly_raw_cutlines


def compute_projected_raw_cutlines(
    week_proj_df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, float]:
    """Compute projected weekly raw cutlines by slot using proj_points.

    Applies the same greedy leaguewide-allocation algorithm as Phase 1 cutlines
    but operates on projected points rather than actual points.

    Args:
        week_proj_df: Single-week projections with columns including
            player, position, proj_points (and optionally season, week).
        config: League config dict.

    Returns:
        Dict mapping slot name → projected cutline value.
    """
    return compute_weekly_raw_cutlines(
        week_proj_df.rename(columns={"proj_points": "points"}),
        config,
    )


def assign_projected_leaguewide_starting_set(
    week_proj_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Assign players into the projected leaguewide starting set for one week.

    Applies the same greedy optimal-allocation algorithm as Phase 1 assignment
    but uses projected points instead of actual points.

    Args:
        week_proj_df: Single-week projections with columns:
            season, week, player, position, proj_points.
        config: League config dict.

    Returns:
        DataFrame of projected starters with columns:
            season, week, player, position, proj_points, proj_assigned_slot.
    """
    temp = week_proj_df.rename(columns={"proj_points": "points"})
    started = assign_leaguewide_starting_set(temp, config)

    result_dict: dict = {
        "player": started["player"].values,
        "position": started["position"].values,
        "proj_points": started["points"].values,
        "proj_assigned_slot": started["assigned_slot"].values,
    }
    if "gsis_id" in started.columns:
        result_dict["gsis_id"] = started["gsis_id"].values
    result = pd.DataFrame(result_dict)

    for col in ("season", "week"):
        if col in week_proj_df.columns:
            result[col] = int(week_proj_df[col].iloc[0])

    ordered = [
        c for c in ("season", "week", "gsis_id", "player", "position", "proj_points", "proj_assigned_slot")
        if c in result.columns
    ]
    return result[ordered].reset_index(drop=True)
