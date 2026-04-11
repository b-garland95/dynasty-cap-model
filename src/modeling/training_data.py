"""Build the Phase 2 training dataset: preseason ADP joined to realized RSV."""

from __future__ import annotations

import numpy as np
import pandas as pd

POSITIONS = ["QB", "RB", "WR", "TE"]

TRAINING_COLUMNS = [
    "season",
    "gsis_id",
    "player",
    "position",
    "adp",
    "log_adp",
    "rsv",
]


def build_phase2_training_data(
    season_values: pd.DataFrame,
    redraft_rankings: pd.DataFrame,
    positions: list[str] | None = None,
) -> pd.DataFrame:
    """Join preseason ADP rankings to Phase 1 season RSV values.

    Parameters
    ----------
    season_values:
        Phase 1 output with at least ``season, gsis_id, player, position, rsv``.
    redraft_rankings:
        Redraft rankings with at least ``season, gsis_id, rank``.
        The ``rank`` column is the overall FantasyPros ADP.
    positions:
        Positions to include. Defaults to QB/RB/WR/TE.

    Returns
    -------
    DataFrame with columns defined by ``TRAINING_COLUMNS``.
    """
    if positions is None:
        positions = POSITIONS

    sv = season_values[["season", "gsis_id", "player", "position", "rsv"]].copy()
    sv = sv.dropna(subset=["gsis_id", "rsv"])

    rr = redraft_rankings[["season", "gsis_id", "rank"]].copy()
    rr = rr.dropna(subset=["gsis_id"])
    rr = rr.rename(columns={"rank": "adp"})

    merged = sv.merge(rr, on=["season", "gsis_id"], how="inner")
    merged = merged[merged["position"].isin(positions)].copy()
    merged["adp"] = merged["adp"].astype(int)
    merged["log_adp"] = np.log(merged["adp"])

    merged = merged[TRAINING_COLUMNS].sort_values(
        ["season", "position", "adp"]
    ).reset_index(drop=True)
    return merged
