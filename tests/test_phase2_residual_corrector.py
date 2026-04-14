"""Tests for Phase 2 Stage 2 residual corrector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.residual_corrector import (
    ResidualCorrector,
    apply_residual_corrector,
    fit_residual_corrector,
)
from src.modeling.isotonic import (
    fit_calibration,
    fit_calibration_two_stage,
    predict,
    predict_two_stage,
)


def _make_train_df(n: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "position": ["RB"] * n,
        "log_adp": np.linspace(0.5, 5.0, n),
        "esv": 100 - np.linspace(0.5, 5.0, n) * 10 + rng.normal(0, 5, n),
        "is_rookie": ([True] * 5 + [False] * (n - 5)),
        "years_of_experience": list(range(n)),
        "age": np.linspace(22.0, 32.0, n),
    })


def test_none_corrector_on_empty_features():
    df = _make_train_df()
    residuals = np.random.default_rng(0).normal(0, 1, len(df))
    result = fit_residual_corrector(df, residuals, feature_names=[])
    assert result is None


def test_zero_correction_from_none_corrector():
    df = _make_train_df()
    corrections = apply_residual_corrector(None, df)
    assert isinstance(corrections, np.ndarray)
    assert len(corrections) == len(df)
    assert (corrections == 0.0).all()


def test_correction_shape_matches_input():
    df = _make_train_df(20)
    residuals = np.zeros(20)
    corrector = fit_residual_corrector(df, residuals, feature_names=["age"])
    assert corrector is not None
    corrections = apply_residual_corrector(corrector, df)
    assert corrections.shape == (20,)


def test_quantile_ordering_preserved_two_stage():
    df = _make_train_df(40)
    calibrations = fit_calibration_two_stage(
        df, extra_features=["is_rookie", "years_of_experience", "age"], alpha=1.0
    )
    scored = predict_two_stage(calibrations, df)
    assert (scored["esv_p25"] <= scored["esv_p50"]).all()
    assert (scored["esv_p50"] <= scored["esv_p75"]).all()


def test_two_stage_with_no_features_equals_baseline():
    df = _make_train_df(40)
    cal_baseline = fit_calibration(df)
    scored_baseline = predict(cal_baseline, df)

    cal_two_stage = fit_calibration_two_stage(df, extra_features=[])
    scored_two_stage = predict_two_stage(cal_two_stage, df)

    np.testing.assert_array_almost_equal(
        scored_baseline["esv_hat"].values,
        scored_two_stage["esv_hat"].values,
        decimal=10,
    )


def test_is_rookie_string_input_handled():
    df = _make_train_df(20)
    # Simulate CSV round-trip: is_rookie stored as strings
    df["is_rookie"] = df["is_rookie"].astype(str)  # "True" / "False"
    residuals = np.zeros(len(df))
    corrector = fit_residual_corrector(df, residuals, feature_names=["is_rookie"])
    assert corrector is not None
    corrections = apply_residual_corrector(corrector, df)
    assert np.isfinite(corrections).all()
