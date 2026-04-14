"""Position-specific monotonic ADP → RSV calibration with quantile bands.

Fits a decreasing isotonic regression per position: lower ADP (better draft
capital) maps to higher expected RSV. Uncertainty is estimated via empirical
residual quantiles binned by log(ADP).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

if TYPE_CHECKING:
    from src.modeling.residual_corrector import ResidualCorrector

PREDICTION_COLUMNS = ["rsv_hat", "rsv_p25", "rsv_p50", "rsv_p75"]


@dataclass
class PositionCalibration:
    """Fitted isotonic model and residual-quantile bands for one position."""

    position: str
    model: IsotonicRegression
    residual_quantiles: pd.DataFrame
    n_train: int
    corrector: "ResidualCorrector | None" = field(default=None, repr=False)


def _fit_position_isotonic(
    log_adp: np.ndarray,
    rsv: np.ndarray,
) -> IsotonicRegression:
    """Fit a decreasing isotonic regression from log(ADP) to RSV."""
    model = IsotonicRegression(increasing=False, out_of_bounds="clip")
    model.fit(log_adp, rsv)
    return model


def _compute_residual_quantiles(
    log_adp: np.ndarray,
    residuals: np.ndarray,
    n_bins: int = 10,
    min_bin_size: int = 3,
) -> pd.DataFrame:
    """Compute empirical p25/p50/p75 of residuals binned by log_adp.

    Uses equal-frequency bins. Bins with fewer than ``min_bin_size``
    observations are merged with their neighbor.
    """
    n_bins = min(n_bins, len(log_adp) // max(min_bin_size, 1))
    n_bins = max(n_bins, 1)

    try:
        bins = pd.qcut(log_adp, q=n_bins, duplicates="drop")
    except ValueError:
        bins = pd.cut(log_adp, bins=max(n_bins, 1), duplicates="drop")

    df = pd.DataFrame({"log_adp": log_adp, "resid": residuals, "bin": bins})

    agg = df.groupby("bin", observed=True)["resid"].agg(
        p25_resid=lambda x: np.percentile(x, 25),
        p50_resid=lambda x: np.percentile(x, 50),
        p75_resid=lambda x: np.percentile(x, 75),
        count="count",
    ).reset_index()

    # Use bin midpoints for interpolation
    agg["bin_center"] = agg["bin"].apply(lambda b: (b.left + b.right) / 2)
    return agg[["bin_center", "p25_resid", "p50_resid", "p75_resid", "count"]]


def fit_calibration(
    train_df: pd.DataFrame,
    positions: list[str] | None = None,
    n_quantile_bins: int = 10,
) -> dict[str, PositionCalibration]:
    """Fit per-position isotonic models and residual-quantile bands.

    Parameters
    ----------
    train_df:
        Training data with columns ``position, log_adp, rsv``.
    positions:
        Positions to fit. Defaults to unique positions in *train_df*.
    n_quantile_bins:
        Number of equal-frequency bins for quantile estimation.

    Returns
    -------
    Dict mapping position string to its fitted ``PositionCalibration``.
    """
    if positions is None:
        positions = sorted(train_df["position"].unique())

    calibrations: dict[str, PositionCalibration] = {}
    for pos in positions:
        pos_df = train_df[train_df["position"] == pos]
        if pos_df.empty:
            continue

        log_adp = pos_df["log_adp"].values.astype(float)
        rsv = pos_df["rsv"].values.astype(float)

        model = _fit_position_isotonic(log_adp, rsv)
        rsv_hat = model.predict(log_adp)
        residuals = rsv - rsv_hat

        rq = _compute_residual_quantiles(log_adp, residuals, n_bins=n_quantile_bins)

        calibrations[pos] = PositionCalibration(
            position=pos,
            model=model,
            residual_quantiles=rq,
            n_train=len(pos_df),
        )
    return calibrations


def predict(
    calibrations: dict[str, PositionCalibration],
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate predictions with quantile bands for new data.

    Parameters
    ----------
    calibrations:
        Fitted calibrations from ``fit_calibration()``.
    df:
        DataFrame with at least ``position`` and ``log_adp`` columns.

    Returns
    -------
    Copy of *df* with added columns: ``rsv_hat, rsv_p25, rsv_p50, rsv_p75``.
    """
    out = df.copy()
    out["rsv_hat"] = np.nan
    out["rsv_p25"] = np.nan
    out["rsv_p50"] = np.nan
    out["rsv_p75"] = np.nan

    for pos, cal in calibrations.items():
        mask = out["position"] == pos
        if not mask.any():
            continue

        log_adp = out.loc[mask, "log_adp"].values.astype(float)
        rsv_hat = cal.model.predict(log_adp)

        rq = cal.residual_quantiles
        centers = rq["bin_center"].values
        p25_r = np.interp(log_adp, centers, rq["p25_resid"].values)
        p50_r = np.interp(log_adp, centers, rq["p50_resid"].values)
        p75_r = np.interp(log_adp, centers, rq["p75_resid"].values)

        p25 = rsv_hat + p25_r
        p50 = rsv_hat + p50_r
        p75 = rsv_hat + p75_r

        # Enforce quantile ordering
        p50 = np.maximum(p50, p25)
        p75 = np.maximum(p75, p50)

        out.loc[mask, "rsv_hat"] = rsv_hat
        out.loc[mask, "rsv_p25"] = p25
        out.loc[mask, "rsv_p50"] = p50
        out.loc[mask, "rsv_p75"] = p75

    return out


def fit_calibration_two_stage(
    train_df: pd.DataFrame,
    extra_features: list[str],
    alpha: float = 1.0,
    positions: list[str] | None = None,
    n_quantile_bins: int = 10,
) -> dict[str, PositionCalibration]:
    """Fit per-position two-stage calibrations: isotonic + Ridge residual corrector.

    Stage 1 is the standard isotonic regression (ADP → RSV).
    Stage 2 fits a Ridge regression on Stage 1 residuals using ``extra_features``.
    When ``extra_features`` is empty this is identical to ``fit_calibration()``.

    Parameters
    ----------
    train_df:
        Training data with ``position, log_adp, rsv`` plus any ``extra_features``.
    extra_features:
        Column names from ``train_df`` to use in Stage 2. Empty list → no Stage 2.
    alpha:
        Ridge regularization strength for Stage 2.
    positions:
        Positions to fit. Defaults to unique positions in *train_df*.
    n_quantile_bins:
        Number of equal-frequency bins for residual quantile estimation.

    Returns
    -------
    Dict mapping position to ``PositionCalibration`` with optional ``corrector``.
    """
    from src.modeling.residual_corrector import fit_residual_corrector

    calibrations = fit_calibration(train_df, positions=positions, n_quantile_bins=n_quantile_bins)

    if not extra_features:
        return calibrations

    if positions is None:
        positions = sorted(train_df["position"].unique())

    for pos in positions:
        if pos not in calibrations:
            continue
        cal = calibrations[pos]
        pos_df = train_df[train_df["position"] == pos]
        log_adp = pos_df["log_adp"].values.astype(float)
        rsv = pos_df["rsv"].values.astype(float)

        stage1_residuals = rsv - cal.model.predict(log_adp)

        corrector = fit_residual_corrector(pos_df, stage1_residuals, extra_features, alpha=alpha)
        if corrector is None:
            continue

        # Recompute residual quantile bands on two-stage residuals
        corrections = corrector.model.predict(
            corrector.scaler.transform(
                _extract_valid_features(pos_df, extra_features)
            )
        ) if corrector is not None else np.zeros(len(pos_df))

        two_stage_residuals = stage1_residuals - corrections
        rq = _compute_residual_quantiles(log_adp, two_stage_residuals, n_bins=n_quantile_bins)

        calibrations[pos] = PositionCalibration(
            position=pos,
            model=cal.model,
            residual_quantiles=rq,
            n_train=cal.n_train,
            corrector=corrector,
        )

    return calibrations


def predict_two_stage(
    calibrations: dict[str, PositionCalibration],
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate two-stage predictions with quantile bands.

    Applies Stage 1 isotonic prediction then Stage 2 Ridge residual correction
    for calibrations that have a ``corrector``. Falls back to Stage 1 only
    for positions without a corrector, matching the behaviour of ``predict()``.

    Parameters
    ----------
    calibrations:
        Fitted calibrations from ``fit_calibration_two_stage()``.
    df:
        DataFrame with at least ``position`` and ``log_adp`` columns.

    Returns
    -------
    Copy of *df* with added columns: ``rsv_hat, rsv_p25, rsv_p50, rsv_p75``.
    """
    from src.modeling.residual_corrector import apply_residual_corrector

    out = df.copy()
    out["rsv_hat"] = np.nan
    out["rsv_p25"] = np.nan
    out["rsv_p50"] = np.nan
    out["rsv_p75"] = np.nan

    for pos, cal in calibrations.items():
        mask = out["position"] == pos
        if not mask.any():
            continue

        pos_df = out.loc[mask]
        log_adp = pos_df["log_adp"].values.astype(float)
        stage1_hat = cal.model.predict(log_adp)
        corrections = apply_residual_corrector(cal.corrector, pos_df)
        rsv_hat = stage1_hat + corrections

        rq = cal.residual_quantiles
        centers = rq["bin_center"].values
        p25_r = np.interp(log_adp, centers, rq["p25_resid"].values)
        p50_r = np.interp(log_adp, centers, rq["p50_resid"].values)
        p75_r = np.interp(log_adp, centers, rq["p75_resid"].values)

        p25 = rsv_hat + p25_r
        p50 = rsv_hat + p50_r
        p75 = rsv_hat + p75_r

        p50 = np.maximum(p50, p25)
        p75 = np.maximum(p75, p50)

        out.loc[mask, "rsv_hat"] = rsv_hat
        out.loc[mask, "rsv_p25"] = p25
        out.loc[mask, "rsv_p50"] = p50
        out.loc[mask, "rsv_p75"] = p75

    return out


def _extract_valid_features(df: pd.DataFrame, feature_names: list[str]) -> np.ndarray:
    """Extract feature matrix for rows with no NaN — used in fit_calibration_two_stage."""
    from src.modeling.residual_corrector import _build_feature_matrix
    X = _build_feature_matrix(df, feature_names)
    valid_mask = ~np.isnan(X).any(axis=1)
    return X[valid_mask]
