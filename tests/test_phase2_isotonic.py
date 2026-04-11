"""Tests for Phase 2 isotonic calibration and quantile bands."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.isotonic import PREDICTION_COLUMNS, fit_calibration, predict


def _make_synthetic_training(
    n_per_pos: int = 40,
    positions: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Build synthetic training data with a clear ADP→RSV relationship.

    Lower ADP → higher RSV, with some Gaussian noise.
    """
    rng = np.random.default_rng(seed)
    if positions is None:
        positions = ["QB", "RB", "WR", "TE"]

    rows = []
    for pos in positions:
        adp = np.arange(1, n_per_pos + 1)
        log_adp = np.log(adp)
        # Decreasing relationship: RSV = 100 - 20*log(ADP) + noise
        rsv = 100 - 20 * log_adp + rng.normal(0, 5, size=n_per_pos)
        for i in range(n_per_pos):
            rows.append({
                "season": 2022,
                "gsis_id": f"G-{pos}{i+1}",
                "player": f"{pos} Player {i+1}",
                "position": pos,
                "adp": int(adp[i]),
                "log_adp": log_adp[i],
                "rsv": rsv[i],
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------


def test_predictions_monotonic_per_position():
    train = _make_synthetic_training()
    cals = fit_calibration(train)

    for pos in ["QB", "RB", "WR", "TE"]:
        test = pd.DataFrame({
            "position": pos,
            "log_adp": np.linspace(0.0, 5.0, 50),
        })
        scored = predict(cals, test)
        # Predictions should be non-increasing as log_adp increases
        rsv_hat = scored["rsv_hat"].values
        diffs = np.diff(rsv_hat)
        assert (diffs <= 1e-10).all(), (
            f"{pos}: monotonicity violated, max increase = {diffs.max():.4f}"
        )


def test_better_adp_not_worse_rsv():
    """A player with ADP=1 should never have worse expected RSV than ADP=50."""
    train = _make_synthetic_training()
    cals = fit_calibration(train)

    for pos in ["QB", "RB", "WR", "TE"]:
        test = pd.DataFrame({
            "position": [pos, pos],
            "log_adp": [np.log(1), np.log(50)],
        })
        scored = predict(cals, test)
        assert scored.iloc[0]["rsv_hat"] >= scored.iloc[1]["rsv_hat"]


# ---------------------------------------------------------------------------
# Quantile ordering
# ---------------------------------------------------------------------------


def test_quantile_ordering():
    train = _make_synthetic_training()
    cals = fit_calibration(train)
    scored = predict(cals, train)

    assert (scored["rsv_p25"] <= scored["rsv_p50"] + 1e-10).all()
    assert (scored["rsv_p50"] <= scored["rsv_p75"] + 1e-10).all()


def test_quantile_bands_non_degenerate():
    """The interquartile range should not be zero everywhere."""
    train = _make_synthetic_training()
    cals = fit_calibration(train)
    scored = predict(cals, train)
    iqr = scored["rsv_p75"] - scored["rsv_p25"]
    assert iqr.mean() > 0


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


def test_predict_adds_expected_columns():
    train = _make_synthetic_training(n_per_pos=20)
    cals = fit_calibration(train)
    scored = predict(cals, train)
    for col in PREDICTION_COLUMNS:
        assert col in scored.columns


def test_predict_preserves_input_rows():
    train = _make_synthetic_training(n_per_pos=20)
    cals = fit_calibration(train)
    scored = predict(cals, train)
    assert len(scored) == len(train)


# ---------------------------------------------------------------------------
# Interpolation / extrapolation
# ---------------------------------------------------------------------------


def test_predict_on_unseen_adp():
    """Model should handle ADP values outside the training range."""
    train = _make_synthetic_training(n_per_pos=20)
    cals = fit_calibration(train)

    # ADP values well beyond training range
    test = pd.DataFrame({
        "position": ["QB"] * 3,
        "log_adp": [np.log(0.5), np.log(100), np.log(500)],
    })
    scored = predict(cals, test)
    assert scored["rsv_hat"].notna().all()
    assert scored["rsv_p25"].notna().all()


# ---------------------------------------------------------------------------
# Regression sanity
# ---------------------------------------------------------------------------


def test_synthetic_monotone_recovery():
    """On perfectly monotonic data, isotonic fit should match closely."""
    n = 30
    log_adp = np.log(np.arange(1, n + 1))
    rsv = 100 - 20 * log_adp  # perfectly decreasing

    train = pd.DataFrame({
        "season": 2022,
        "gsis_id": [f"G-{i}" for i in range(n)],
        "player": [f"P{i}" for i in range(n)],
        "position": "QB",
        "adp": np.arange(1, n + 1),
        "log_adp": log_adp,
        "rsv": rsv,
    })
    cals = fit_calibration(train)
    scored = predict(cals, train)

    # Should recover nearly exactly
    mae = (scored["rsv_hat"] - scored["rsv"]).abs().mean()
    assert mae < 1.0, f"MAE on perfect data = {mae:.2f}, expected < 1.0"


def test_fit_calibration_empty_position_skipped():
    """If a requested position has no data, it should be skipped."""
    train = _make_synthetic_training(positions=["QB"])
    cals = fit_calibration(train, positions=["QB", "RB"])
    assert "QB" in cals
    assert "RB" not in cals
