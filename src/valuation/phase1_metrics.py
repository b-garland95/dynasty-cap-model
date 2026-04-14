from __future__ import annotations

from typing import Any

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


def compute_dollar_values(
    season_values: pd.DataFrame,
    weekly_detail: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add implied cap dollar values to Phase 1 season and weekly outputs.

    dollar_value = (rsv / season_total_rsv) * (base_cap * n_teams)

    For weekly rows the same per-season RSV denominator is used, so a
    player's weekly dollar_values sum exactly to their season dollar_value.

    Parameters
    ----------
    season_values:
        Season-aggregated Phase 1 output; must contain ``season`` and ``rsv``.
    weekly_detail:
        Weekly Phase 1 output; must contain ``season`` and ``rsv_week``.
    config:
        League config dict (must have ``cap.base_cap`` and ``league.teams``).

    Returns
    -------
    (season_values, weekly_detail) with a ``dollar_value`` column added to each.
    """
    total_league_cap = config["cap"]["base_cap"] * config["league"]["teams"]

    season_rsv_totals = season_values.groupby("season")["rsv"].transform("sum")

    season_values = season_values.copy()
    season_values["dollar_value"] = (
        season_values["rsv"] / season_rsv_totals.clip(lower=1e-9)
    ) * total_league_cap

    season_totals_map = season_values.groupby("season")["rsv"].sum()
    weekly_detail = weekly_detail.copy()
    weekly_detail["dollar_value"] = (
        weekly_detail["rsv_week"]
        / weekly_detail["season"].map(season_totals_map).clip(lower=1e-9)
    ) * total_league_cap

    return season_values, weekly_detail
