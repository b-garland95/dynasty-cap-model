from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.historical_weekly_points import export_historical_weekly_points
from src.utils.config import load_league_config


def main() -> int:
    config = load_league_config()
    start_season = int(sys.argv[1]) if len(sys.argv) > 1 else int(config["season"]["history_start_season"])
    end_season = int(sys.argv[2]) if len(sys.argv) > 2 else int(config["season"]["current_season"])
    output_path = REPO_ROOT / "data" / "interim" / f"historical_weekly_player_points_{start_season}_{end_season}.csv"
    weekly_df = export_historical_weekly_points(
        start_season=start_season,
        end_season=end_season,
        config=config,
        output_path=str(output_path),
    )
    print(f"Wrote {len(weekly_df)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
