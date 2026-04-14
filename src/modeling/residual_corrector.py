"""Stage 2 Ridge residual corrector for Phase 2 two-stage forecasting."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


@dataclass
class ResidualCorrector:
    """Ridge regression fit on Stage 1 residuals using extra player features."""

    feature_names: list[str]
    model: Ridge
    scaler: StandardScaler
    n_train: int


def fit_residual_corrector(
    train_df: pd.DataFrame,
    residuals: np.ndarray,
    feature_names: list[str],
    alpha: float = 1.0,
) -> ResidualCorrector | None:
    """Fit a Ridge corrector predicting Stage 1 residuals from extra features.

    Parameters
    ----------
    train_df:
        Training DataFrame containing ``feature_names`` columns.
    residuals:
        Stage 1 residuals (``rsv - rsv_hat``) aligned to ``train_df`` rows.
    feature_names:
        Columns from ``train_df`` to use as features.
    alpha:
        Ridge regularization strength.

    Returns
    -------
    ``ResidualCorrector`` or ``None`` if ``feature_names`` is empty or all
    feature values are null.
    """
    if not feature_names:
        return None

    X = _build_feature_matrix(train_df, feature_names)
    valid_mask = ~np.isnan(X).any(axis=1)

    if valid_mask.sum() < 2:
        return None

    X_valid = X[valid_mask]
    y_valid = residuals[valid_mask]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_valid)

    model = Ridge(alpha=alpha)
    model.fit(X_scaled, y_valid)

    return ResidualCorrector(
        feature_names=list(feature_names),
        model=model,
        scaler=scaler,
        n_train=int(valid_mask.sum()),
    )


def apply_residual_corrector(
    corrector: ResidualCorrector | None,
    df: pd.DataFrame,
) -> np.ndarray:
    """Return per-row correction values.

    Returns zeros when ``corrector`` is ``None`` or when feature values are
    missing (conservative fallback).
    """
    corrections = np.zeros(len(df))

    if corrector is None:
        return corrections

    X = _build_feature_matrix(df, corrector.feature_names)
    valid_mask = ~np.isnan(X).any(axis=1)

    if valid_mask.any():
        X_scaled = corrector.scaler.transform(X[valid_mask])
        corrections[valid_mask] = corrector.model.predict(X_scaled)

    return corrections


def _build_feature_matrix(df: pd.DataFrame, feature_names: list[str]) -> np.ndarray:
    """Extract and coerce feature columns to a float matrix."""
    cols = []
    for col in feature_names:
        if col not in df.columns:
            cols.append(np.full(len(df), np.nan))
        else:
            series = df[col]
            # Handle boolean-as-string (e.g. "True"/"False" from CSV round-trip)
            # Check for object or string dtypes (including ArrowStringArray)
            if series.dtype == object or hasattr(series, "str") and pd.api.types.is_string_dtype(series):
                arr = np.array([
                    1.0 if str(v).strip().lower() == "true"
                    else (0.0 if str(v).strip().lower() == "false" else np.nan)
                    for v in series
                ], dtype=float)
                cols.append(arr)
            else:
                cols.append(series.astype(float).to_numpy())
    return np.column_stack(cols)
