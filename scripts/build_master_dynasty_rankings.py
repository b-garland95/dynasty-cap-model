"""Build the master pre-season dynasty ADP file.

Primary source: FantasyData dynasty ADP CSVs from ``data/raw/rankings/dynasty_adp/``.

Output: ``data/interim/dynasty_rankings_master.csv`` with columns:
    season, rank, tier, player, team, position, pos_rank, merge_name, gsis_id

Once this file exists, ``scripts/generate_phase3_tv_inputs.py`` will automatically
apply the dynasty multi-year TV trajectory (age curves + delta correction) instead
of the flat tv_y0 = tv_y1 = tv_y2 = tv_y3 fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.redraft_rankings import build_master_dynasty_adp

DYNASTY_ADP_DIR = REPO_ROOT / "data" / "raw" / "rankings" / "dynasty_adp"
OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "dynasty_rankings_master.csv"


def main() -> int:
    master = build_master_dynasty_adp(DYNASTY_ADP_DIR)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUTPUT_PATH, index=False)

    n_seasons = master["season"].nunique()
    n_matched = master["gsis_id"].notna().sum()
    n_total = len(master)
    seasons = sorted(master["season"].unique())
    print(f"Wrote {n_total} rows across {n_seasons} seasons {seasons} to {OUTPUT_PATH}")
    print(f"  gsis_id matched: {n_matched}/{n_total} ({n_matched/n_total:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
