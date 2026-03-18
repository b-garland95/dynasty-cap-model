from __future__ import annotations

import pandas as pd


def aggregate_sav(season_weekly_started: pd.DataFrame) -> pd.DataFrame:
    """Aggregate weekly positive start value into season SAV."""
    group_cols = ["player"]
    if "season" in season_weekly_started.columns:
        group_cols = ["season", "player"]

    grouped = season_weekly_started.groupby(group_cols, as_index=False).agg(
        sav=("wmsv", "sum"),
        total_points=("points", "sum"),
        weeks_started_in_leaguewide_set=("player", "size"),
    )

    sort_cols = [col for col in ["sav", "total_points", "season", "player"] if col in grouped.columns]
    ascending = [False, False] + [True] * (len(sort_cols) - 2)
    return grouped.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)
