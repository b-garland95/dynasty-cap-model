from __future__ import annotations

import pandas as pd


def aggregate_sav(season_weekly_started: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weekly positive start value into season SAV."""
    has_gsis = "gsis_id" in season_weekly_started.columns
    player_key = "gsis_id" if has_gsis else "player"

    group_cols = [player_key]
    if "season" in season_weekly_started.columns:
        group_cols = ["season", player_key]

    agg_spec: dict = {
        "sav": ("wmsv", "sum"),
        "total_points": ("points", "sum"),
        "weeks_started_in_leaguewide_set": (player_key, "size"),
    }
    if has_gsis:
        agg_spec["player"] = ("player", "first")
        agg_spec["position"] = ("position", "first")

    grouped = season_weekly_started.groupby(group_cols, as_index=False).agg(**agg_spec)

    sort_cols = [col for col in ["sav", "total_points", "season", player_key] if col in grouped.columns]
    ascending = [False, False] + [True] * (len(sort_cols) - 2)
    return grouped.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
