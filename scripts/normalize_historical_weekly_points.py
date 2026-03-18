from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.historical_weekly_points import normalize_historical_weekly_points_csv
from src.utils.config import load_league_config



def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/normalize_historical_weekly_points.py "
            "<raw_nflverse_csv_path> [output_path]"
        )
        return 1

    raw_csv_path = Path(sys.argv[1])
    output_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else REPO_ROOT / "data" / "interim" / "historical_weekly_player_points_2015_2025.csv"
    )

    weekly_df = normalize_historical_weekly_points_csv(
        raw_csv_path=str(raw_csv_path),
        config=load_league_config(),
        start_season=2015,
        end_season=2025,
        output_path=str(output_path),
    )
    print(f"Wrote {len(weekly_df)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
