"""Compare Phase 2 backtest summaries across named model variants.

Reads all phase2_backtest_summary_*.csv files in data/processed/ and prints
a side-by-side table ranked by MAE, then writes a combined comparison CSV.

Usage:
    python scripts/compare_phase2_variants.py
    python scripts/compare_phase2_variants.py --variants baseline v1_rookie_xp v2_all_demo
    python scripts/compare_phase2_variants.py --position QB --season OVERALL
    python scripts/compare_phase2_variants.py --position ALL --season OVERALL
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
COMPARISON_OUTPUT = PROCESSED_DIR / "phase2_backtest_comparison.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Phase 2 backtest summaries across variants.")
    parser.add_argument(
        "--variants",
        nargs="*",
        default=None,
        help="Variant names to compare. Defaults to all discovered summary files.",
    )
    parser.add_argument(
        "--position",
        default="ALL",
        help="Position to show in printed table (default: ALL)",
    )
    parser.add_argument(
        "--season",
        default="OVERALL",
        help="Season to show in printed table (default: OVERALL)",
    )
    args = parser.parse_args()

    import pandas as pd

    # Discover summary files
    if args.variants:
        paths = [PROCESSED_DIR / f"phase2_backtest_summary_{v}.csv" for v in args.variants]
        missing = [p for p in paths if not p.exists()]
        if missing:
            for p in missing:
                print(f"  Missing: {p}")
            print("Run run_phase2_calibration.py --variant <name> to generate missing summaries.")
            return 1
    else:
        paths = sorted(PROCESSED_DIR.glob("phase2_backtest_summary_*.csv"))
        if not paths:
            print("No phase2_backtest_summary_*.csv files found in data/processed/.")
            print("Run: python scripts/run_phase2_calibration.py --variant baseline")
            return 1

    frames = []
    for p in paths:
        df = pd.read_csv(p)
        # Ensure variant column is present (backfill from filename if missing)
        if "variant" not in df.columns:
            variant_name = p.stem.replace("phase2_backtest_summary_", "")
            df.insert(0, "variant", variant_name)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Write full comparison CSV
    COMPARISON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(COMPARISON_OUTPUT, index=False)
    print(f"Full comparison written → {COMPARISON_OUTPUT}")
    print(f"  {len(combined)} rows across {combined['variant'].nunique()} variant(s)\n")

    # Print filtered table
    table = combined[
        (combined["position"] == args.position) &
        (combined["season"].astype(str) == args.season)
    ].copy()

    if table.empty:
        print(f"No rows match position={args.position!r}, season={args.season!r}.")
        print(f"Available positions: {sorted(combined['position'].unique())}")
        print(f"Available seasons:   {sorted(combined['season'].astype(str).unique())}")
        return 0

    table = table.sort_values("mae").reset_index(drop=True)

    # Formatted print
    header = f"  Position={args.position}  Season={args.season}"
    print("=" * 70)
    print(f"VARIANT COMPARISON{header}")
    print("=" * 70)
    col_w = {"variant": max(len("variant"), table["variant"].str.len().max()),
              "n": 6, "mae": 10, "spearman_rho": 13, "coverage_p25_p75": 18}
    fmt_header = (
        f"{'variant':<{col_w['variant']}}  "
        f"{'n':>{col_w['n']}}  "
        f"{'mae':>{col_w['mae']}}  "
        f"{'spearman_rho':>{col_w['spearman_rho']}}  "
        f"{'coverage_p25_p75':>{col_w['coverage_p25_p75']}}"
    )
    print(fmt_header)
    print("-" * len(fmt_header))
    for _, row in table.iterrows():
        spearman = f"{row['spearman_rho']:.4f}" if pd.notna(row["spearman_rho"]) else "     N/A"
        print(
            f"{str(row['variant']):<{col_w['variant']}}  "
            f"{int(row['n']):>{col_w['n']}}  "
            f"{row['mae']:>{col_w['mae']}.4f}  "
            f"{spearman:>{col_w['spearman_rho']}}  "
            f"{row['coverage_p25_p75']:>{col_w['coverage_p25_p75']}.4f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
