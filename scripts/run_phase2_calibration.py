"""Run Phase 2 v0 ADP → RSV calibration with rolling backtest.

Usage:
    python scripts/run_phase2_calibration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.player_dimensions import enrich_with_player_dimensions
from src.modeling.backtest import rolling_backtest
from src.modeling.training_data import build_phase2_training_data

SEASON_VALUES_CSV = REPO_ROOT / "data" / "processed" / "phase1" / "phase1_season_values.csv"
RANKINGS_CSV = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"
TRAINING_OUTPUT = REPO_ROOT / "data" / "interim" / "phase2_training_dataset.csv"
PREDICTIONS_OUTPUT = REPO_ROOT / "data" / "processed" / "phase2_backtest_player_predictions.csv"
SUMMARY_OUTPUT = REPO_ROOT / "data" / "processed" / "phase2_backtest_summary.csv"
DIMS_CACHE = REPO_ROOT / "data" / "interim" / "player_dimensions_raw.csv"


def main() -> int:
    import pandas as pd

    season_values = pd.read_csv(SEASON_VALUES_CSV, dtype={"gsis_id": "string"})
    rankings = pd.read_csv(RANKINGS_CSV, dtype={"gsis_id": "string"})

    # 1. Build training dataset
    training = build_phase2_training_data(season_values, rankings)

    # Enrich training data with player dimensions
    dims_kwargs = {"cache_path": DIMS_CACHE} if DIMS_CACHE.exists() else {}
    try:
        training = enrich_with_player_dimensions(training, season_col="season", **dims_kwargs)
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment failed ({exc.__class__.__name__}); skipping")

    TRAINING_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    training.to_csv(TRAINING_OUTPUT, index=False)
    print(f"Training dataset: {len(training)} rows across {training['season'].nunique()} seasons")
    print(f"  → {TRAINING_OUTPUT}")

    # 2. Run rolling backtest
    preds, summary = rolling_backtest(training, min_train_seasons=1)

    # Enrich backtest predictions with player dimensions
    try:
        preds = enrich_with_player_dimensions(preds, season_col="season", **dims_kwargs)
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment on preds failed ({exc.__class__.__name__}); skipping")

    PREDICTIONS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(PREDICTIONS_OUTPUT, index=False)
    summary.to_csv(SUMMARY_OUTPUT, index=False)
    print(f"\nBacktest predictions: {len(preds)} scored player-seasons")
    print(f"  → {PREDICTIONS_OUTPUT}")
    print(f"  → {SUMMARY_OUTPUT}")

    # 3. Print summary
    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    print(summary.to_string(index=False, float_format="%.3f"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
