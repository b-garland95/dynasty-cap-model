"""Build the master pre-season redraft ADP file.

Reads per-year FantasyData 2QB ADP CSVs from
``data/raw/rankings/redraft_adp/``, normalizes them, attaches nflverse IDs,
and writes the combined result to
``data/interim/redraft_rankings_master.csv``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.redraft_rankings import build_master_redraft_adp

RAW_DIR = REPO_ROOT / "data" / "raw" / "rankings" / "redraft_adp"
OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"


def main() -> int:
    master = build_master_redraft_adp(RAW_DIR)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUTPUT_PATH, index=False)

    n_seasons = master["season"].nunique()
    n_matched = master["gsis_id"].notna().sum()
    n_total = len(master)
    print(f"Wrote {n_total} rows across {n_seasons} seasons to {OUTPUT_PATH}")
    print(f"  gsis_id matched: {n_matched}/{n_total} ({n_matched/n_total:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
