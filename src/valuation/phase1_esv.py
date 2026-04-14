from __future__ import annotations

import pandas as pd

from src.valuation.capture_model import CaptureModel



def compute_esv_ld_weekly(started_weekly_df: pd.DataFrame, capture_model: CaptureModel) -> pd.DataFrame:
    """Compute weekly ESV and LD from weekly player rows and a capture model.

    ESV = start_prob × margin (full margin, not just positive).
    A high-start_prob player who underperforms the cutline delivers negative
    ESV, reflecting the real cost of starting a disappointing player.
    """
    weekly_df = started_weekly_df.copy()
    weekly_df["roster_prob"] = capture_model.roster_prob(weekly_df)
    weekly_df["start_prob"] = capture_model.start_prob(weekly_df)
    weekly_df["esv_week"] = weekly_df["roster_prob"] * weekly_df["start_prob"] * weekly_df["margin"]
    weekly_df["ld_week"] = weekly_df["roster_prob"] * weekly_df["start_prob"] * weekly_df["wdrag"]
    return weekly_df



def compute_esv_ld_from_started_weekly(started_weekly_df: pd.DataFrame, capture_model: CaptureModel) -> pd.DataFrame:
    """Aggregate ESV and LD per player-season from weekly started rows."""
    weekly_df = compute_esv_ld_weekly(started_weekly_df, capture_model)

    player_key = "gsis_id" if "gsis_id" in weekly_df.columns else "player"
    group_cols = [player_key]
    if "season" in weekly_df.columns:
        group_cols = ["season", player_key]

    return weekly_df.groupby(group_cols, as_index=False).agg(
        esv=("esv_week", "sum"),
        ld=("ld_week", "sum"),
    )



def compute_capture_gap(sav_df: pd.DataFrame, esv_df: pd.DataFrame) -> pd.DataFrame:
    """Join SAV and ESV outputs and compute capture gap."""
    player_key = "gsis_id" if "gsis_id" in sav_df.columns and "gsis_id" in esv_df.columns else "player"
    join_cols = [col for col in ["season", player_key] if col in sav_df.columns and col in esv_df.columns]
    if not join_cols:
        join_cols = [player_key]

    merged = sav_df.merge(esv_df, on=join_cols, how="inner")
    merged["cg"] = merged["sav"] - merged["esv"]
    return merged
