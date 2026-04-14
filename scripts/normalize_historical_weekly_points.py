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
            "<raw_nflverse_csv_path> [start_season] [end_season] [output_path]"
        )
        return 1

    raw_csv_path = Path(sys.argv[1])
    config = load_league_config()
    start_season = int(sys.argv[2]) if len(sys.argv) > 2 else int(config["season"]["history_start_season"])
    end_season = int(sys.argv[3]) if len(sys.argv) > 3 else int(config["season"]["current_season"])
    output_path = (
        Path(sys.argv[4])
        if len(sys.argv) > 4
        else REPO_ROOT / "data" / "interim" / f"historical_weekly_player_points_{start_season}_{end_season}.csv"
    )

    weekly_df = normalize_historical_weekly_points_csv(
        raw_csv_path=str(raw_csv_path),
        config=config,
        start_season=start_season,
        end_season=end_season,
        output_path=str(output_path),
    )
    print(f"Wrote {len(weekly_df)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
