"""Rolling year-forward backtests for Phase 2 ADP → ESV calibration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from src.modeling.isotonic import fit_calibration, fit_calibration_two_stage, predict, predict_two_stage

if TYPE_CHECKING:
    from src.modeling.variant_config import ModelVariantConfig

SUMMARY_COLUMNS = [
    "variant",
    "season",
    "position",
    "n",
    "mae",
    "spearman_rho",
    "coverage_p25_p75",
]


def _compute_metrics(scored: pd.DataFrame) -> dict:
    """Compute MAE, Spearman rho, and interval coverage for a scored group."""
    esv = scored["esv"]
    esv_hat = scored["esv_hat"]
    n = len(scored)

    mae = (esv - esv_hat).abs().mean()

    if n >= 3:
        spearman_rho = esv.rank().corr(esv_hat.rank())
    else:
        spearman_rho = np.nan

    in_band = (esv >= scored["esv_p25"]) & (esv <= scored["esv_p75"])
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
    variant: "ModelVariantConfig | None" = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run rolling year-forward backtests.

    For each test season *t* where at least ``min_train_seasons`` prior
    seasons are available, fit on seasons ``< t`` and score season ``t``.

    Parameters
    ----------
    training_data:
        Full training dataset from ``build_phase2_training_data()``.
        Must include ``season, position, log_adp, esv``.
    min_train_seasons:
        Minimum number of training seasons before testing begins.
    n_quantile_bins:
        Passed to ``fit_calibration()`` for quantile estimation.
    variant:
        Optional ``ModelVariantConfig``. When ``extra_features`` is non-empty
        the two-stage (isotonic + Ridge residual corrector) path is used.
        ``None`` or an empty ``extra_features`` list uses the baseline path.

    Returns
    -------
    (player_predictions, summary)

    player_predictions
        One row per player-season scored, with columns from the input
        plus ``esv_hat, esv_p25, esv_p50, esv_p75``.
    summary
        Per-season per-position metrics plus an ``ALL`` aggregate per
        season and an overall row. Includes a ``variant`` column.
    """
    variant_name = variant.name if variant is not None else "baseline"
    use_two_stage = variant is not None and len(variant.extra_features) > 0

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

        if use_two_stage:
            calibrations = fit_calibration_two_stage(
                train,
                extra_features=variant.extra_features,
                alpha=variant.stage2_alpha,
                n_quantile_bins=n_quantile_bins,
            )
            scored = predict_two_stage(calibrations, test)
        else:
            calibrations = fit_calibration(train, n_quantile_bins=n_quantile_bins)
            scored = predict(calibrations, test)

        all_preds.append(scored)

        # Per-position metrics
        for pos in sorted(scored["position"].unique()):
            pos_scored = scored[scored["position"] == pos]
            if len(pos_scored) < 1:
                continue
            m = _compute_metrics(pos_scored)
            m["variant"] = variant_name
            m["season"] = test_season
            m["position"] = pos
            all_metrics.append(m)

        # ALL-positions aggregate
        m_all = _compute_metrics(scored)
        m_all["variant"] = variant_name
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
            m["variant"] = variant_name
            m["season"] = "OVERALL"
            m["position"] = pos
            all_metrics.append(m)

        m_overall = _compute_metrics(player_predictions)
        m_overall["variant"] = variant_name
        m_overall["season"] = "OVERALL"
        m_overall["position"] = "ALL"
        all_metrics.append(m_overall)

        summary = pd.DataFrame(all_metrics)

    if not summary.empty:
        summary = summary[SUMMARY_COLUMNS].reset_index(drop=True)

    return player_predictions, summary
