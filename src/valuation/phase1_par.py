from __future__ import annotations

from statistics import median
from typing import Any

import pandas as pd

from src.utils.dataframe_utils import resolve_id_column


POSITION_SLOTS: tuple[str, ...] = ("QB", "RB", "WR", "TE")


def compute_position_replacement_level_par(
    season_points_df: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, float]:
    """Compute naive PAR replacement levels by position as median weekly Nth score."""
    teams = int(config["league"]["teams"])
    lineup = config["lineup"]
    required_counts = {
        "QB": teams * int(lineup["qb"]),
        "RB": teams * int(lineup["rb"]),
        "WR": teams * int(lineup["wr"]),
        "TE": teams * int(lineup["te"]),
    }

    replacement_levels: dict[str, float] = {}
    for position in POSITION_SLOTS:
        nth_values: list[float] = []
        for _, week_df in season_points_df.loc[season_points_df["position"] == position].groupby("week"):
            weekly_points = week_df["points"].sort_values(ascending=False).reset_index(drop=True)
            required_count = required_counts[position]
            if len(weekly_points) < required_count:
                raise ValueError(
                    f"Insufficient players for PAR replacement at {position}: need {required_count}, found {len(weekly_points)}"
                )
            nth_values.append(float(weekly_points.iloc[required_count - 1]))
        replacement_levels[position] = float(median(nth_values))

    return replacement_levels



def compute_par_by_player(season_points_df: pd.DataFrame, r_par: dict[str, float]) -> pd.DataFrame:
    """Compute weekly and aggregated PAR by player."""
    weekly_df = season_points_df.copy()
    weekly_df["par_week"] = weekly_df.apply(
        lambda row: float(row["points"]) - float(r_par[row["position"]]),
        axis=1,
    )

    player_key = resolve_id_column(weekly_df)
    group_cols = [player_key]
    if "season" in weekly_df.columns:
        group_cols = ["season", player_key]

    return weekly_df.groupby(group_cols, as_index=False).agg(
        par=("par_week", "sum"),
        total_points=("points", "sum"),
    )
