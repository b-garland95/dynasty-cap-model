from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.weekly_projections import normalize_weekly_projections_csv
from src.utils.config import load_league_config



def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/normalize_weekly_projections.py "
            "<raw_csv_path> [output_path] [season_for_new_schema]"
        )
        return 1

    raw_csv_path = Path(sys.argv[1])
    output_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else REPO_ROOT / "data" / "interim" / "weekly_projections_normalized.csv"
    )
    season = int(sys.argv[3]) if len(sys.argv) > 3 else None

    normalized_df = normalize_weekly_projections_csv(
        raw_csv_path=str(raw_csv_path),
        config=load_league_config(),
        output_path=str(output_path),
        season=season,
    )
    print(f"Wrote {len(normalized_df)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
