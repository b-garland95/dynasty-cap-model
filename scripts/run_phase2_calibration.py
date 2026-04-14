"""Run Phase 2 ADP → RSV calibration with rolling backtest.

Usage:
    python scripts/run_phase2_calibration.py
    python scripts/run_phase2_calibration.py --variant baseline
    python scripts/run_phase2_calibration.py --variant v1_rookie_xp
    python scripts/run_phase2_calibration.py --variant v2_all_demo
    python scripts/run_phase2_calibration.py --variant v3_age_only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.player_dimensions import enrich_with_player_dimensions
from src.modeling.backtest import rolling_backtest
from src.modeling.training_data import build_phase2_training_data
from src.modeling.variant_config import load_variant_config

SEASON_VALUES_CSV = REPO_ROOT / "data" / "processed" / "phase1" / "phase1_season_values.csv"
RANKINGS_CSV = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"
TRAINING_OUTPUT = REPO_ROOT / "data" / "interim" / "phase2_training_dataset.csv"
DIMS_CACHE = REPO_ROOT / "data" / "interim" / "player_dimensions_raw.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 backtest for a named model variant.")
    parser.add_argument(
        "--variant",
        default="baseline",
        help="Registered variant name from league_config.yaml phase2_variants (default: baseline)",
    )
    args = parser.parse_args()

    variant = load_variant_config(args.variant)

    import pandas as pd

    season_values = pd.read_csv(SEASON_VALUES_CSV, dtype={"gsis_id": "string"})
    rankings = pd.read_csv(RANKINGS_CSV, dtype={"gsis_id": "string"})

    # 1. Build training dataset (shared across variants)
    training = build_phase2_training_data(season_values, rankings)

    dims_kwargs = {"cache_path": DIMS_CACHE} if DIMS_CACHE.exists() else {}
    try:
        training = enrich_with_player_dimensions(training, season_col="season", **dims_kwargs)
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment failed ({exc.__class__.__name__}); skipping")

    TRAINING_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    training.to_csv(TRAINING_OUTPUT, index=False)
    print(f"Training dataset: {len(training)} rows across {training['season'].nunique()} seasons")
    print(f"  → {TRAINING_OUTPUT}")

    # 2. Run rolling backtest with chosen variant
    preds_path = REPO_ROOT / "data" / "processed" / f"phase2_backtest_player_predictions_{variant.name}.csv"
    summary_path = REPO_ROOT / "data" / "processed" / f"phase2_backtest_summary_{variant.name}.csv"

    print(f"\nRunning backtest: variant={variant.name!r}, extra_features={variant.extra_features}")
    preds, summary = rolling_backtest(training, min_train_seasons=1, variant=variant)

    try:
        preds = enrich_with_player_dimensions(preds, season_col="season", **dims_kwargs)
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment on preds failed ({exc.__class__.__name__}); skipping")

    preds_path.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(preds_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(f"\nBacktest predictions: {len(preds)} scored player-seasons")
    print(f"  → {preds_path}")
    print(f"  → {summary_path}")

    # 3. Print summary
    print("\n" + "=" * 70)
    print(f"BACKTEST SUMMARY  [{variant.name}]")
    print("=" * 70)
    print(summary.to_string(index=False, float_format="%.3f"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
