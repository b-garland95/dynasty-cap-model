"""Dynasty multi-year TV path backtest.

For each available test season t (min_train_seasons + 1 … max_season):
  - Train dynasty calibration on seasons < t
  - Predict Y1, Y2, Y3 ESV for players whose dynasty positional rank is
    known k seasons before season t
  - Compare predicted to actual Phase 1 ESV

Outputs a CSV with per-(season, position, year_offset) summary metrics and
a per-player predictions CSV, mirroring the Phase 2 backtest outputs.

Usage
-----
    python scripts/run_dynasty_backtest.py [training_csv] [dynasty_csv] [output_dir]

Defaults:
    training_csv  = data/interim/phase2_training_dataset.csv
    dynasty_csv   = data/interim/dynasty_rankings_master.csv
    output_dir    = data/processed/dynasty_backtest/
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modeling.age_curve import get_age_multiplier, load_age_curves
from src.modeling.dynasty_calibration import (
    build_dynasty_training_data,
    compute_positional_rank,
    fit_dynasty_calibration,
    predict_dynasty_ceiling,
)
from src.utils.config import load_league_config

DEFAULT_TRAINING_CSV = REPO_ROOT / "data" / "interim" / "phase2_training_dataset.csv"
DEFAULT_DYNASTY_CSV = REPO_ROOT / "data" / "interim" / "dynasty_rankings_master.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "dynasty_backtest"
MIN_TRAIN_SEASONS = 3


def _predict_year_offset(
    dynasty_pos_rank: np.ndarray,
    positions: np.ndarray,
    ages: np.ndarray,
    calibrations: dict,
    age_curves: dict,
    year_offset: int,
    delta_alpha: float = 0.05,
    n_pos: dict | None = None,
    deltas: np.ndarray | None = None,
) -> np.ndarray:
    """Compute dynasty TV path point estimates for a single year offset."""
    esv_hat = np.full(len(dynasty_pos_rank), np.nan)
    for i, (pos, rank, age) in enumerate(zip(positions, dynasty_pos_rank, ages)):
        if np.isnan(rank) or pos not in calibrations:
            continue
        log_adp = np.log(max(rank, 1))
        row_df = pd.DataFrame({"position": [pos], "log_adp": [log_adp]})
        scored = predict_dynasty_ceiling(calibrations, row_df)
        ceiling = float(scored["esv_hat"].iloc[0])

        params = age_curves.get(pos, age_curves.get("WR"))
        mult = get_age_multiplier(params, float(age) if np.isfinite(age) else float("nan"), year_offset)

        delta_correction = 1.0
        if deltas is not None and n_pos is not None and not np.isnan(deltas[i]):
            n = n_pos.get(pos, 24)
            norm_delta = max(-1.0, min(1.0, float(deltas[i]) / n))
            delta_correction = 1.0 + delta_alpha * norm_delta * year_offset

        esv_hat[i] = max(0.0, ceiling * mult * delta_correction)
    return esv_hat


def run_backtest(
    training_df: pd.DataFrame,
    dynasty_df: pd.DataFrame,
    config: dict,
    min_train_seasons: int = MIN_TRAIN_SEASONS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling backtest for the dynasty multi-year TV path.

    For year_offset k in {1, 2, 3}:
    - Join dynasty positional rank from season (t - k) to actual ESV in season t
    - Predict using calibration fit on seasons < t

    Returns
    -------
    player_preds : per-player predictions DataFrame
    summary      : per-(season, position, year_offset) metrics DataFrame
    """
    age_curves = load_age_curves(config)
    delta_alpha = float(config.get("dynasty_delta_alpha", 0.05))

    dynasty_with_pos = compute_positional_rank(dynasty_df)

    all_seasons = sorted(training_df["season"].unique())
    if len(all_seasons) < min_train_seasons + 1:
        raise ValueError(
            f"Need at least {min_train_seasons + 1} seasons for backtest, "
            f"got {len(all_seasons)}"
        )

    player_rows: list[dict] = []
    summary_rows: list[dict] = []

    for test_season in all_seasons[min_train_seasons:]:
        train_mask = training_df["season"] < test_season
        train_slice = training_df[train_mask]

        dynasty_train_mask = dynasty_df["season"] < test_season
        dynasty_train_slice = dynasty_df[dynasty_train_mask]

        if dynasty_train_slice.empty:
            continue

        dynasty_training = build_dynasty_training_data(train_slice, dynasty_train_slice)
        if dynasty_training.empty:
            continue

        calibrations = fit_dynasty_calibration(dynasty_training)

        # Actual ESV in test season
        actual = training_df[training_df["season"] == test_season][
            ["season", "gsis_id", "player", "position", "age", "adp", "esv"]
        ].copy()
        if actual.empty:
            continue

        # Redraft positional rank in test season for delta computation
        actual["redraft_pos_rank"] = (
            actual.groupby("position")["adp"]
            .rank(method="first", ascending=True)
        ).astype(int)

        # Number of players per position in test-season dynasty rankings
        test_dynasty = dynasty_with_pos[dynasty_with_pos["season"] == test_season]
        n_pos = test_dynasty.groupby("position")["dynasty_pos_rank"].max().to_dict()

        for year_offset in (1, 2, 3):
            source_season = test_season - year_offset
            dynasty_source = dynasty_with_pos[
                dynasty_with_pos["season"] == source_season
            ][["gsis_id", "dynasty_pos_rank"]].rename(
                columns={"dynasty_pos_rank": f"dpr_{source_season}"}
            )
            if dynasty_source.empty:
                continue

            merged = actual.merge(dynasty_source, on="gsis_id", how="inner")
            if merged.empty:
                continue

            dpr_col = f"dpr_{source_season}"
            merged_dpr = merged[dpr_col].values.astype(float)
            merged_ages = merged["age"].fillna(float("nan")).values.astype(float)
            merged_pos = merged["position"].values

            # Compute delta from source season dynasty positional rank vs test-season redraft
            # (rough approximation since the positions may differ in ranking source year)
            deltas = merged["redraft_pos_rank"].values - merged_dpr

            esv_hat = _predict_year_offset(
                merged_dpr, merged_pos, merged_ages,
                calibrations, age_curves,
                year_offset=year_offset,
                delta_alpha=delta_alpha,
                n_pos=n_pos,
                deltas=deltas,
            )

            valid = ~np.isnan(esv_hat) & ~np.isnan(merged["esv"].values)
            if valid.sum() < 2:
                continue

            merged[f"esv_hat_y{year_offset}"] = esv_hat

            # Flat baseline: esv_hat at year_offset=0 (same-season redraft calibration)
            # Use year_offset=1 with age_mult=1, delta_correction=1 as naive flat baseline
            flat_baseline = _predict_year_offset(
                merged_dpr, merged_pos, merged_ages,
                calibrations, age_curves, year_offset=0,
                delta_alpha=0.0,
            )
            merged["esv_flat_baseline"] = flat_baseline

            for _, row in merged[valid].iterrows():
                player_rows.append({
                    "test_season": test_season,
                    "year_offset": year_offset,
                    "source_season": source_season,
                    "gsis_id": row["gsis_id"],
                    "player": row["player"],
                    "position": row["position"],
                    "age": row.get("age"),
                    "dynasty_pos_rank": row[dpr_col],
                    "redraft_pos_rank": row["redraft_pos_rank"],
                    "dynasty_delta": row["redraft_pos_rank"] - row[dpr_col],
                    "esv_actual": row["esv"],
                    f"esv_hat_y{year_offset}": row[f"esv_hat_y{year_offset}"],
                    "esv_flat_baseline": row.get("esv_flat_baseline"),
                })

            actual_vals = merged.loc[valid, "esv"].values
            hat_vals = esv_hat[valid]
            flat_vals = flat_baseline[valid] if flat_baseline is not None else np.zeros_like(actual_vals)

            for pos in [None] + list(set(merged.loc[valid, "position"])):
                if pos is not None:
                    pos_valid = valid & (merged["position"] == pos)
                    if pos_valid.sum() < 2:
                        continue
                    av = merged.loc[pos_valid, "esv"].values
                    hv = esv_hat[pos_valid]
                    fv = flat_baseline[pos_valid]
                else:
                    av, hv, fv = actual_vals, hat_vals, flat_vals

                from scipy.stats import spearmanr
                rho, _ = spearmanr(av, hv)
                rho_flat, _ = spearmanr(av, fv)

                summary_rows.append({
                    "test_season": test_season,
                    "year_offset": year_offset,
                    "position": pos if pos is not None else "ALL",
                    "n": len(av),
                    "mae_dynasty": float(np.abs(hv - av).mean()),
                    "mae_flat": float(np.abs(fv - av).mean()),
                    "spearman_rho_dynasty": float(rho),
                    "spearman_rho_flat": float(rho_flat),
                    "mae_improvement": float(np.abs(fv - av).mean() - np.abs(hv - av).mean()),
                })

    if not player_rows:
        raise ValueError("No backtest predictions generated — check data alignment.")

    player_preds = pd.DataFrame(player_rows)
    summary = pd.DataFrame(summary_rows)
    return player_preds, summary


def main() -> int:
    training_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRAINING_CSV
    dynasty_csv = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DYNASTY_CSV
    output_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_OUTPUT_DIR

    if not training_csv.exists():
        print(f"ERROR: training CSV not found: {training_csv}")
        return 1
    if not dynasty_csv.exists():
        print(f"ERROR: dynasty rankings CSV not found: {dynasty_csv}")
        return 1

    training_df = pd.read_csv(training_csv, dtype={"gsis_id": "string"})
    dynasty_df = pd.read_csv(dynasty_csv, dtype={"gsis_id": "string"})
    config = load_league_config()

    print(
        f"Running dynasty backtest: {len(training_df['season'].unique())} seasons of ESV, "
        f"{len(dynasty_df['season'].unique())} seasons of dynasty ADP"
    )

    player_preds, summary = run_backtest(training_df, dynasty_df, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    player_preds_path = output_dir / "dynasty_backtest_player_predictions.csv"
    summary_path = output_dir / "dynasty_backtest_summary.csv"
    player_preds.to_csv(player_preds_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"\nBacktest complete — {len(player_preds)} player-season-offset predictions")
    print(f"  Player predictions → {player_preds_path}")
    print(f"  Summary metrics    → {summary_path}\n")

    # Print summary to console
    for offset in sorted(summary["year_offset"].unique()):
        row = summary[(summary["year_offset"] == offset) & (summary["position"] == "ALL")]
        if row.empty:
            continue
        r = row.iloc[0]
        print(
            f"  Y+{offset}  n={int(r['n']):4d}  "
            f"MAE dynasty={r['mae_dynasty']:.1f}  "
            f"MAE flat={r['mae_flat']:.1f}  "
            f"MAE improvement={r['mae_improvement']:.1f}  "
            f"Spearman ρ dynasty={r['spearman_rho_dynasty']:.3f}  "
            f"flat={r['spearman_rho_flat']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
