"""Dynasty ADP positional-rank calibration.

Derives within-position ranks from overall dynasty ADP (needed because non-SF
dynasty ADP compresses QB overall ranks, making positional rank the only
cross-position-safe input signal).

Reuses the standard isotonic calibration interface — ``build_dynasty_training_data``
produces a DataFrame whose ``log_adp`` column equals ``log(dynasty_pos_rank)``,
so ``fit_calibration`` / ``predict`` from ``isotonic.py`` work unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling.isotonic import (
    PositionCalibration,
    fit_calibration,
    predict,
)
from src.modeling.training_data import POSITIONS, _EXTRA_FEATURE_COLUMNS

DYNASTY_TRAINING_COLUMNS = [
    "season",
    "gsis_id",
    "player",
    "position",
    "dynasty_pos_rank",
    "log_adp",
    "is_rookie",
    "years_of_experience",
    "age",
    "esv",
]


def compute_positional_rank(
    rankings_df: pd.DataFrame,
    position_col: str = "position",
    season_col: str = "season",
    rank_col: str = "rank",
) -> pd.DataFrame:
    """Add ``dynasty_pos_rank`` column: ordinal rank within each position/season.

    Players are ranked by their overall dynasty rank (``rank_col``) within each
    ``(season, position)`` group, starting at 1 for the lowest (best) overall
    rank.  Ties are broken by the order they appear in ``rankings_df``.

    Parameters
    ----------
    rankings_df:
        Rankings DataFrame with at least ``season``, ``position``, and ``rank``
        columns (or the names given by the keyword arguments).
    position_col, season_col, rank_col:
        Column name overrides.

    Returns
    -------
    Copy of *rankings_df* with a new integer ``dynasty_pos_rank`` column.
    """
    df = rankings_df.copy()
    df["dynasty_pos_rank"] = (
        df.groupby([season_col, position_col])[rank_col]
        .rank(method="first", ascending=True)
        .astype(int)
    )
    return df


def build_dynasty_training_data(
    season_values: pd.DataFrame,
    dynasty_rankings: pd.DataFrame,
    positions: list[str] | None = None,
) -> pd.DataFrame:
    """Join dynasty positional ranks to Phase 1 season ESV values.

    Parameters
    ----------
    season_values:
        Phase 1 output with at least ``season, gsis_id, player, position, esv``.
        May optionally include ``is_rookie``, ``years_of_experience``, ``age``.
    dynasty_rankings:
        Dynasty rankings with at least ``season, gsis_id, rank``.  ``rank`` is
        the overall (non-SF) dynasty rank; positional rank is derived here.
    positions:
        Positions to include.  Defaults to QB/RB/WR/TE.

    Returns
    -------
    DataFrame with columns defined by ``DYNASTY_TRAINING_COLUMNS``.  ``log_adp``
    equals ``log(dynasty_pos_rank)`` so the output is directly compatible with
    ``fit_calibration()`` / ``predict()`` from ``isotonic.py``.
    """
    if positions is None:
        positions = POSITIONS

    sv_cols = ["season", "gsis_id", "player", "position", "esv"] + _EXTRA_FEATURE_COLUMNS
    sv = season_values.copy()
    for col in _EXTRA_FEATURE_COLUMNS:
        if col not in sv.columns:
            sv[col] = np.nan
    sv = sv[sv_cols].copy()
    sv = sv.dropna(subset=["gsis_id", "esv"])

    dynasty_with_pos_rank = compute_positional_rank(dynasty_rankings)
    dr = dynasty_with_pos_rank[["season", "gsis_id", "dynasty_pos_rank"]].copy()
    dr = dr.dropna(subset=["gsis_id"])

    merged = sv.merge(dr, on=["season", "gsis_id"], how="inner")
    merged = merged[merged["position"].isin(positions)].copy()
    merged["dynasty_pos_rank"] = merged["dynasty_pos_rank"].astype(int)
    merged["log_adp"] = np.log(merged["dynasty_pos_rank"])

    return (
        merged[DYNASTY_TRAINING_COLUMNS]
        .sort_values(["season", "position", "dynasty_pos_rank"])
        .reset_index(drop=True)
    )


def fit_dynasty_calibration(
    training_df: pd.DataFrame,
    positions: list[str] | None = None,
    n_quantile_bins: int = 10,
) -> dict[str, PositionCalibration]:
    """Fit per-position isotonic models on dynasty positional rank → ESV.

    Wraps ``fit_calibration()`` — the ``log_adp`` column in *training_df*
    must equal ``log(dynasty_pos_rank)`` as produced by
    ``build_dynasty_training_data()``.

    Returns
    -------
    Dict mapping position string to ``PositionCalibration``.
    """
    return fit_calibration(training_df, positions=positions, n_quantile_bins=n_quantile_bins)


def predict_dynasty_ceiling(
    calibrations: dict[str, PositionCalibration],
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Score players through dynasty calibration to get ceiling ESV estimates.

    *df* must have ``position`` and ``log_adp`` columns where ``log_adp`` equals
    ``log(dynasty_pos_rank)``.

    Returns
    -------
    Copy of *df* with added columns: ``esv_hat, esv_p25, esv_p50, esv_p75``.
    These represent the dynasty-ceiling point estimate and uncertainty bands.
    """
    return predict(calibrations, df)
