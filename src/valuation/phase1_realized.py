from __future__ import annotations

import pandas as pd

from src.valuation.capture_model import CaptureModel



def compute_rsv_ld_weekly(started_weekly_df: pd.DataFrame, capture_model: CaptureModel) -> pd.DataFrame:
    """Compute weekly RSV and LD from started weekly rows and a capture model."""
    weekly_df = started_weekly_df.copy()
    weekly_df["roster_prob"] = capture_model.roster_prob(weekly_df)
    weekly_df["start_prob"] = capture_model.start_prob(weekly_df)
    weekly_df["rsv_week"] = weekly_df["roster_prob"] * weekly_df["start_prob"] * weekly_df["wmsv"]
    weekly_df["ld_week"] = weekly_df["roster_prob"] * weekly_df["start_prob"] * weekly_df["wdrag"]
    return weekly_df



def compute_rsv_ld_from_started_weekly(started_weekly_df: pd.DataFrame, capture_model: CaptureModel) -> pd.DataFrame:
    """Aggregate RSV and LD per player-season from weekly started rows."""
    weekly_df = compute_rsv_ld_weekly(started_weekly_df, capture_model)

    group_cols = ["player"]
    if "season" in weekly_df.columns:
        group_cols = ["season", "player"]

    return weekly_df.groupby(group_cols, as_index=False).agg(
        rsv=("rsv_week", "sum"),
        ld=("ld_week", "sum"),
    )



def compute_capture_gap(sav_df: pd.DataFrame, rsv_df: pd.DataFrame) -> pd.DataFrame:
    """Join SAV and RSV outputs and compute capture gap."""
    join_cols = [col for col in ["season", "player"] if col in sav_df.columns and col in rsv_df.columns]
    if not join_cols:
        join_cols = ["player"]

    merged = sav_df.merge(rsv_df, on=join_cols, how="inner")
    merged["cg"] = merged["sav"] - merged["rsv"]
    return merged
