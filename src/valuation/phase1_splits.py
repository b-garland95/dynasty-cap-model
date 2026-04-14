from __future__ import annotations

from typing import Any

import pandas as pd

from src.utils.dataframe_utils import resolve_id_column



def add_season_phase(weekly_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Add regular/playoff/other phase labels to weekly rows."""
    regular_start, regular_end = [int(v) for v in config["season"]["regular_weeks"]]
    playoff_start, playoff_end = [int(v) for v in config["season"]["playoff_weeks"]]

    result = weekly_df.copy()
    result["phase"] = "other"
    result.loc[result["week"].between(regular_start, regular_end), "phase"] = "regular"
    result.loc[result["week"].between(playoff_start, playoff_end), "phase"] = "playoffs"
    return result



def aggregate_par_splits(par_weekly_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Aggregate weekly PAR into regular/playoff splits."""
    return _aggregate_by_phase(add_season_phase(par_weekly_df, config), "par_week", "par")



def aggregate_sav_splits(started_weekly_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Aggregate weekly SAV into regular/playoff splits."""
    return _aggregate_by_phase(add_season_phase(started_weekly_df, config), "wmsv", "sav")



def aggregate_esv_ld_splits(esv_weekly_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Aggregate weekly ESV and LD into regular/playoff splits."""
    phased = add_season_phase(esv_weekly_df, config)
    player_key = resolve_id_column(phased)
    group_cols = [col for col in ["season", player_key, "phase"] if col in phased.columns]
    if player_key not in group_cols:
        group_cols.append(player_key)
    return phased.groupby(group_cols, as_index=False).agg(
        esv=("esv_week", "sum"),
        ld=("ld_week", "sum"),
    )



def compute_capture_gap_splits(sav_splits_df: pd.DataFrame, esv_splits_df: pd.DataFrame) -> pd.DataFrame:
    """Compute split capture gap from split SAV and ESV tables."""
    player_key = resolve_id_column(sav_splits_df, esv_splits_df)
    join_cols = [col for col in ["season", player_key, "phase"] if col in sav_splits_df.columns and col in esv_splits_df.columns]
    if not join_cols:
        join_cols = [player_key, "phase"]
    merged = sav_splits_df.merge(esv_splits_df, on=join_cols, how="inner")
    merged["cg"] = merged["sav"] - merged["esv"]
    return merged



def _aggregate_by_phase(weekly_df: pd.DataFrame, value_col: str, output_col: str) -> pd.DataFrame:
    player_key = resolve_id_column(weekly_df)
    group_cols = [col for col in ["season", player_key, "phase"] if col in weekly_df.columns]
    if player_key not in group_cols:
        group_cols.append(player_key)
    return weekly_df.groupby(group_cols, as_index=False).agg(**{output_col: (value_col, "sum")})
