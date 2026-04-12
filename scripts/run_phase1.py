"""Run the Phase 1 valuation pipeline and export results to CSV.

Usage:
    python scripts/run_phase1.py [--start-season 2020] [--end-season 2025]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.player_dimensions import enrich_with_player_dimensions
from src.ingest.player_ids import (
    build_name_crosswalk_from_points,
    harmonize_projection_names,
    harmonize_projection_names_by_name,
)
from src.utils.config import load_league_config
from src.valuation.phase1_pipeline import run_phase1_all_seasons

HISTORICAL_CSV = REPO_ROOT / "data" / "interim" / "historical_weekly_player_points_2015_2025.csv"
PROJECTIONS_CSV = REPO_ROOT / "data" / "interim" / "weekly_projections_2014_2025_master_normalized.csv"
RANKINGS_CSV = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "phase1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 valuation pipeline")
    parser.add_argument("--start-season", type=int, default=2020)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--points-csv", type=Path, default=HISTORICAL_CSV)
    parser.add_argument("--projections-csv", type=Path, default=PROJECTIONS_CSV)
    parser.add_argument("--rankings-csv", type=Path, default=RANKINGS_CSV)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    config = load_league_config()
    seasons = list(range(args.start_season, args.end_season + 1))

    # --- Load historical points ---------------------------------------------
    import pandas as pd

    if not args.points_csv.exists():
        print(f"ERROR: Historical points CSV not found at {args.points_csv}")
        print("Run: python scripts/load_historical_weekly_points.py")
        return 1

    print(f"Loading historical points from {args.points_csv} ...")
    hist_df = pd.read_csv(args.points_csv)
    # Rename player_id -> gsis_id (nflverse player_id IS the gsis_id)
    hist_df = hist_df.rename(columns={"player_id": "gsis_id"})
    hist_df = hist_df[hist_df["season_type"] == "REG"].copy()
    print(f"  {len(hist_df)} rows, seasons {hist_df['season'].min()}-{hist_df['season'].max()}")

    # --- Load and harmonize projections -------------------------------------
    projections = None
    if args.projections_csv.exists():
        print(f"Loading projections from {args.projections_csv} ...")
        proj_df = pd.read_csv(args.projections_csv, dtype={"player_id": "string"})
        print(f"  {len(proj_df)} rows, seasons {proj_df['season'].min()}-{proj_df['season'].max()}")
        print("Harmonizing projection names via player-ID crosswalk ...")
        try:
            projections = harmonize_projection_names(proj_df)
        except Exception as exc:
            print(f"  Live crosswalk unavailable ({exc.__class__.__name__}); falling back to local name-based matching")
            local_crosswalk = build_name_crosswalk_from_points(hist_df)
            projections = harmonize_projection_names_by_name(proj_df, crosswalk=local_crosswalk)
        n_matched = projections["gsis_id"].notna().sum()
        print(f"  {n_matched}/{len(projections)} projection rows matched to gsis_id")
    else:
        print(f"No projections CSV at {args.projections_csv} — using PerfectCaptureModel")

    # --- Load preseason redraft rankings -----------------------------------
    adp_rankings = None
    if args.rankings_csv.exists():
        print(f"Loading redraft rankings from {args.rankings_csv} ...")
        adp_rankings = pd.read_csv(args.rankings_csv, dtype={"gsis_id": "string"})
        print(f"  {len(adp_rankings)} rows, seasons {adp_rankings['season'].min()}-{adp_rankings['season'].max()}")

        missing_rankings = sorted(set(seasons) - set(adp_rankings["season"].unique()))
        if missing_rankings:
            print(
                "  Warning: no rankings for seasons "
                f"{missing_rankings}; those seasons will fall back to start-only capture if projections exist."
            )
    else:
        print(f"No rankings CSV at {args.rankings_csv} — using start-only capture when projections are available")

    # --- Run Phase 1 --------------------------------------------------------
    print(f"\nRunning Phase 1 for seasons {seasons} ...")
    results = run_phase1_all_seasons(hist_df, projections, adp_rankings, config, seasons=seasons)

    # --- Build consolidated season values -----------------------------------
    cg_df = results["cg"]
    par_df = results["par"]

    # Merge CG (has sav, rsv, cg, player, position, weeks) with PAR
    player_key = "gsis_id" if "gsis_id" in cg_df.columns else "player"
    merge_cols = ["season", player_key]
    season_values = cg_df.merge(
        par_df[merge_cols + ["par"]],
        on=merge_cols,
        how="left",
    )

    # --- Enrich season values with player dimensions -------------------------
    DIMS_CACHE = REPO_ROOT / "data" / "interim" / "player_dimensions_raw.csv"
    try:
        season_values = enrich_with_player_dimensions(
            season_values,
            season_col="season",
            cache_path=DIMS_CACHE if DIMS_CACHE.exists() else None,
        )
        print("Attached player dimensions (age, years_of_experience, draft info, …)")
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment failed ({exc.__class__.__name__}); skipping")

    # --- Export --------------------------------------------------------------
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sv_path = args.output_dir / "phase1_season_values.csv"
    season_values.to_csv(sv_path, index=False)
    print(f"\nWrote {len(season_values)} rows to {sv_path}")

    weekly_path = args.output_dir / "phase1_weekly_detail.csv"
    results["started_weekly"].to_csv(weekly_path, index=False)
    print(f"Wrote {len(results['started_weekly'])} rows to {weekly_path}")

    cl_path = args.output_dir / "phase1_cutlines.csv"
    results["cutlines"].to_csv(cl_path, index=False)
    print(f"Wrote {len(results['cutlines'])} rows to {cl_path}")

    # --- Quick summary ------------------------------------------------------
    print("\n--- Top 20 SAV leaders ---")
    top = season_values.sort_values("sav", ascending=False).head(20)
    for _, row in top.iterrows():
        pos = row.get("position", "?")
        par_val = row.get("par", float("nan"))
        print(
            f"  {row['season']}  {row['player']:<25s} {pos:<3s}  "
            f"SAV={row['sav']:7.1f}  RSV={row['rsv']:7.1f}  "
            f"CG={row['cg']:6.1f}  PAR={par_val:7.1f}  "
            f"TP={row['total_points']:7.1f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
