"""Rolling year-forward backtests for Phase 2 ADP → RSV calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.modeling.isotonic import fit_calibration, predict

SUMMARY_COLUMNS = [
    "season",
    "position",
    "n",
    "mae",
    "spearman_rho",
    "coverage_p25_p75",
]


def _compute_metrics(scored: pd.DataFrame) -> dict:
    """Compute MAE, Spearman rho, and interval coverage for a scored group."""
    rsv = scored["rsv"]
    rsv_hat = scored["rsv_hat"]
    n = len(scored)

    mae = (rsv - rsv_hat).abs().mean()

    if n >= 3:
        spearman_rho = rsv.rank().corr(rsv_hat.rank())
    else:
        spearman_rho = np.nan

    in_band = (rsv >= scored["rsv_p25"]) & (rsv <= scored["rsv_p75"])
    coverage = in_band.mean()

    return {
        "n": n,
        "mae": mae,
        "spearman_rho": spearman_rho,
        "coverage_p25_p75": coverage,
    }


def rolling_backtest(
    training_data: pd.DataFrame,
    min_train_seasons: int = 1,
    n_quantile_bins: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run rolling year-forward backtests.

    For each test season *t* where at least ``min_train_seasons`` prior
    seasons are available, fit on seasons ``< t`` and score season ``t``.

    Parameters
    ----------
    training_data:
        Full training dataset from ``build_phase2_training_data()``.
        Must include ``season, position, log_adp, rsv``.
    min_train_seasons:
        Minimum number of training seasons before testing begins.
    n_quantile_bins:
        Passed to ``fit_calibration()`` for quantile estimation.

    Returns
    -------
    (player_predictions, summary)

    player_predictions
        One row per player-season scored, with columns from the input
        plus ``rsv_hat, rsv_p25, rsv_p50, rsv_p75``.
    summary
        Per-season per-position metrics plus an ``ALL`` aggregate per
        season and an overall row.
    """
    seasons = sorted(training_data["season"].unique())
    all_preds: list[pd.DataFrame] = []
    all_metrics: list[dict] = []

    for i, test_season in enumerate(seasons):
        if i < min_train_seasons:
            continue

        train = training_data[training_data["season"] < test_season]
        test = training_data[training_data["season"] == test_season]

        if train.empty or test.empty:
            continue

        calibrations = fit_calibration(train, n_quantile_bins=n_quantile_bins)
        scored = predict(calibrations, test)
        all_preds.append(scored)

        # Per-position metrics
        for pos in sorted(scored["position"].unique()):
            pos_scored = scored[scored["position"] == pos]
            if len(pos_scored) < 1:
                continue
            m = _compute_metrics(pos_scored)
            m["season"] = test_season
            m["position"] = pos
            all_metrics.append(m)

        # ALL-positions aggregate
        m_all = _compute_metrics(scored)
        m_all["season"] = test_season
        m_all["position"] = "ALL"
        all_metrics.append(m_all)

    player_predictions = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
    summary = pd.DataFrame(all_metrics)

    # Add overall row across all test seasons
    if not player_predictions.empty:
        for pos in sorted(player_predictions["position"].unique()):
            pos_all = player_predictions[player_predictions["position"] == pos]
            m = _compute_metrics(pos_all)
            m["season"] = "OVERALL"
            m["position"] = pos
            all_metrics.append(m)

        m_overall = _compute_metrics(player_predictions)
        m_overall["season"] = "OVERALL"
        m_overall["position"] = "ALL"
        all_metrics.append(m_overall)

        summary = pd.DataFrame(all_metrics)

    if not summary.empty:
        summary = summary[SUMMARY_COLUMNS].reset_index(drop=True)

    return player_predictions, summary
