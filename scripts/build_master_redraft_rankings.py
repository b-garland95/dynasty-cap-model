"""Build the master pre-season redraft ADP/rankings file.

Primary source: FantasyData 2QB ADP CSVs from ``data/raw/rankings/redraft_adp/``.
Fallback source (target season): live FantasyPros ECR feed via nflreadpy when
the target season is not yet covered by FantasyData ADP.
Historical fallback: FantasyPros OP Rankings CSVs from ``data/raw/rankings/redraft/``
for any prior season not covered by FantasyData.

Output: ``data/interim/redraft_rankings_master.csv`` with a ``ranking_source``
column indicating which source was used per row.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.redraft_rankings import build_master_redraft_adp_with_fallback
from src.utils.config import load_league_config

ADP_DIR = REPO_ROOT / "data" / "raw" / "rankings" / "redraft_adp"
RANKINGS_FALLBACK_DIR = REPO_ROOT / "data" / "raw" / "rankings" / "redraft"
OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"


def main() -> int:
    config = load_league_config()
    target_season = int(config["season"]["target_season"])

    master = build_master_redraft_adp_with_fallback(
        adp_dir=ADP_DIR,
        rankings_fallback_dir=RANKINGS_FALLBACK_DIR,
        target_season=target_season,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUTPUT_PATH, index=False)

    n_seasons = master["season"].nunique()
    n_matched = master["gsis_id"].notna().sum()
    n_total = len(master)
    for source, grp in master.groupby("ranking_source"):
        s_seasons = sorted(grp["season"].unique())
        print(f"  [{source}] {len(grp)} rows across seasons {s_seasons}")
    print(f"Wrote {n_total} rows across {n_seasons} seasons to {OUTPUT_PATH}")
    print(f"  gsis_id matched: {n_matched}/{n_total} ({n_matched/n_total:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
