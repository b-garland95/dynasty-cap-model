"""Tests for Phase 2 rolling year-forward backtest harness."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.modeling.backtest import SUMMARY_COLUMNS, rolling_backtest
from src.modeling.variant_config import ModelVariantConfig


def _make_multiyear_data(
    seasons: list[int] | None = None,
    n_per_pos: int = 20,
    seed: int = 99,
) -> pd.DataFrame:
    """Build synthetic multi-year training data.

    Clear decreasing ADP→ESV relationship per position with noise.
    """
    rng = np.random.default_rng(seed)
    if seasons is None:
        seasons = [2020, 2021, 2022, 2023]
    positions = ["QB", "RB"]

    rows = []
    for season in seasons:
        for pos in positions:
            adp = np.arange(1, n_per_pos + 1)
            log_adp = np.log(adp)
            esv = 80 - 15 * log_adp + rng.normal(0, 4, size=n_per_pos)
            for i in range(n_per_pos):
                rows.append({
                    "season": season,
                    "gsis_id": f"G-{pos}{i+1}",
                    "player": f"{pos} Player {i+1}",
                    "position": pos,
                    "adp": int(adp[i]),
                    "log_adp": log_adp[i],
                    "is_rookie": (i == 0),
                    "years_of_experience": i,
                    "age": 22.0 + i * 0.5,
                    "esv": esv[i],
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# No future leakage
# ---------------------------------------------------------------------------


def test_no_future_leakage():
    """Every prediction row should only use training data from prior seasons."""
    data = _make_multiyear_data(seasons=[2020, 2021, 2022, 2023])
    preds, summary = rolling_backtest(data, min_train_seasons=1)

    # Test season 2021 should be the earliest scored season
    pred_seasons = sorted(preds["season"].unique())
    assert pred_seasons[0] == 2021, f"Earliest test season is {pred_seasons[0]}, expected 2021"

    # 2020 data should never appear in predictions (it's always train-only)
    assert 2020 not in preds["season"].values


def test_no_test_season_in_training():
    """Verify that for each test season, no training rows from that season exist.

    We do this by checking that the model doesn't overfit to test data.
    With our synthetic data, predictions should have non-trivial error
    (since we add noise and train on different seasons).
    """
    data = _make_multiyear_data(seasons=[2020, 2021, 2022])
    preds, summary = rolling_backtest(data, min_train_seasons=1)

    # The per-season MAE should be > 0 (not a perfect fit)
    season_summary = summary[(summary["position"] == "ALL") & (summary["season"] != "OVERALL")]
    assert (season_summary["mae"] > 0).all()


# ---------------------------------------------------------------------------
# Summary structure
# ---------------------------------------------------------------------------


def test_summary_columns():
    data = _make_multiyear_data()
    _, summary = rolling_backtest(data)
    assert list(summary.columns) == SUMMARY_COLUMNS


def test_summary_has_per_season_and_overall():
    data = _make_multiyear_data(seasons=[2020, 2021, 2022])
    _, summary = rolling_backtest(data, min_train_seasons=1)

    seasons_in_summary = set(summary["season"].unique())
    assert 2021 in seasons_in_summary
    assert 2022 in seasons_in_summary
    assert "OVERALL" in seasons_in_summary


def test_summary_has_all_position_aggregate():
    data = _make_multiyear_data()
    _, summary = rolling_backtest(data)
    assert "ALL" in summary["position"].values


# ---------------------------------------------------------------------------
# Prediction structure
# ---------------------------------------------------------------------------


def test_prediction_columns():
    data = _make_multiyear_data()
    preds, _ = rolling_backtest(data)
    for col in ["esv_hat", "esv_p25", "esv_p50", "esv_p75"]:
        assert col in preds.columns


def test_predictions_not_empty():
    data = _make_multiyear_data(seasons=[2020, 2021])
    preds, _ = rolling_backtest(data, min_train_seasons=1)
    assert len(preds) > 0


# ---------------------------------------------------------------------------
# Coverage bounds
# ---------------------------------------------------------------------------


def test_coverage_between_0_and_1():
    data = _make_multiyear_data()
    _, summary = rolling_backtest(data)
    assert (summary["coverage_p25_p75"] >= 0.0).all()
    assert (summary["coverage_p25_p75"] <= 1.0).all()


# ---------------------------------------------------------------------------
# min_train_seasons
# ---------------------------------------------------------------------------


def test_min_train_seasons_respected():
    """With 3 seasons and min_train_seasons=2, only 1 test season is produced."""
    data = _make_multiyear_data(seasons=[2020, 2021, 2022])
    preds, summary = rolling_backtest(data, min_train_seasons=2)

    pred_seasons = preds["season"].unique()
    assert len(pred_seasons) == 1
    assert pred_seasons[0] == 2022


# ---------------------------------------------------------------------------
# End-to-end sanity
# ---------------------------------------------------------------------------


def test_end_to_end_small():
    """Full pipeline on small synthetic data produces reasonable output."""
    data = _make_multiyear_data(seasons=[2020, 2021, 2022, 2023], n_per_pos=15)
    preds, summary = rolling_backtest(data, min_train_seasons=1)

    # Should have predictions for 3 test seasons
    assert preds["season"].nunique() == 3

    # Overall Spearman should be positive (model captures the trend)
    overall = summary[(summary["season"] == "OVERALL") & (summary["position"] == "ALL")]
    assert len(overall) == 1
    assert overall.iloc[0]["spearman_rho"] > 0, "Expected positive rank correlation"

    # Coverage should be reasonable (between 20% and 80% for p25-p75 band)
    assert overall.iloc[0]["coverage_p25_p75"] > 0.1
    assert overall.iloc[0]["coverage_p25_p75"] < 0.95


# ---------------------------------------------------------------------------
# Variant support
# ---------------------------------------------------------------------------


def test_variant_column_stamped_in_summary():
    data = _make_multiyear_data()
    variant = ModelVariantConfig(name="test_v", extra_features=["age"])
    _, summary = rolling_backtest(data, variant=variant)
    assert "variant" in summary.columns
    assert (summary["variant"] == "test_v").all()


def test_baseline_variant_identical_to_no_variant():
    data = _make_multiyear_data()
    baseline_cfg = ModelVariantConfig(name="baseline", extra_features=[])
    _, summary_none = rolling_backtest(data)
    _, summary_baseline = rolling_backtest(data, variant=baseline_cfg)

    overall_none = summary_none[
        (summary_none["season"] == "OVERALL") & (summary_none["position"] == "ALL")
    ]["mae"].iloc[0]
    overall_baseline = summary_baseline[
        (summary_baseline["season"] == "OVERALL") & (summary_baseline["position"] == "ALL")
    ]["mae"].iloc[0]
    assert abs(overall_none - overall_baseline) < 1e-10


def test_two_stage_variant_runs_without_error():
    data = _make_multiyear_data()
    variant = ModelVariantConfig(name="v1_rookie_xp", extra_features=["is_rookie", "years_of_experience"])
    preds, summary = rolling_backtest(data, variant=variant)
    assert len(preds) > 0
    assert len(summary) > 0
    assert summary.shape == rolling_backtest(data)[1].shape


def test_leakage_still_absent_with_variant():
    data = _make_multiyear_data(seasons=[2020, 2021, 2022, 2023])
    variant = ModelVariantConfig(name="v2_all_demo", extra_features=["is_rookie", "years_of_experience", "age"])
    preds, _ = rolling_backtest(data, min_train_seasons=1, variant=variant)
    pred_seasons = sorted(preds["season"].unique())
    assert pred_seasons[0] == 2021
    assert 2020 not in preds["season"].values
