from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.weekly_projections import (
    combine_normalized_weekly_projections,
    find_duplicate_projection_rows,
    normalize_weekly_projections_csv,
    resolve_projection_key_conflicts,
)
from src.utils.config import load_league_config


LEGACY_RAW_PATH = REPO_ROOT / "data" / "raw" / "fantasydata_weekly_projections_2014_2024_raw.csv"
LEGACY_NORMALIZED_PATH = REPO_ROOT / "data" / "interim" / "weekly_projections_2014_2024_normalized.csv"
DUPLICATE_REPORT_PATH = REPO_ROOT / "data" / "processed" / "projection_duplicate_conflicts" / "legacy_projection_key_conflicts_2014_2024.csv"


def build_master_weekly_projections(config: dict) -> tuple[object, object, object]:
    current_season = int(config["season"]["current_season"])
    num_regular_weeks = int(config["season"]["num_regular_weeks"])

    current_dir = REPO_ROOT / "data" / "interim" / f"weekly_projections_{current_season}"
    current_all_weeks_path = REPO_ROOT / "data" / "interim" / f"weekly_projections_{current_season}_all_weeks_normalized.csv"
    master_output_path = REPO_ROOT / "data" / "interim" / f"weekly_projections_2014_{current_season}_master_normalized.csv"

    legacy_df = normalize_weekly_projections_csv(
        raw_csv_path=str(LEGACY_RAW_PATH),
        config=config,
        validate_keys=False,
    )

    legacy_duplicates = find_duplicate_projection_rows(legacy_df)
    if not legacy_duplicates.empty:
        DUPLICATE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        legacy_duplicates.to_csv(DUPLICATE_REPORT_PATH, index=False)
        legacy_df = resolve_projection_key_conflicts(legacy_df)

    LEGACY_NORMALIZED_PATH.parent.mkdir(parents=True, exist_ok=True)
    legacy_df.to_csv(LEGACY_NORMALIZED_PATH, index=False)

    current_frames = []
    for week in range(1, num_regular_weeks + 1):
        raw_path = REPO_ROOT / "data" / "raw" / f"fantasydata_weekly_projections_{current_season}_week{week}_raw.csv"
        if not raw_path.exists():
            continue
        normalized_path = current_dir / f"weekly_projections_{current_season}_week{week}_normalized.csv"
        current_frames.append(
            normalize_weekly_projections_csv(
                raw_csv_path=str(raw_path),
                config=config,
                output_path=str(normalized_path),
                season=current_season,
            )
        )

    current_df = combine_normalized_weekly_projections(current_frames)
    current_all_weeks_path.parent.mkdir(parents=True, exist_ok=True)
    current_df.to_csv(current_all_weeks_path, index=False)

    master_df = combine_normalized_weekly_projections([legacy_df, current_df])
    master_output_path.parent.mkdir(parents=True, exist_ok=True)
    master_df.to_csv(master_output_path, index=False)
    return legacy_df, current_df, master_df


def main() -> int:
    config = load_league_config()
    current_season = int(config["season"]["current_season"])
    legacy_df, current_df, master_df = build_master_weekly_projections(config)
    print(f"Wrote {len(legacy_df)} legacy rows to {LEGACY_NORMALIZED_PATH}")
    print(f"Wrote {len(current_df)} current-season rows ({current_season})")
    print(f"Wrote {len(master_df)} master rows")
    if DUPLICATE_REPORT_PATH.exists():
        print(f"Wrote legacy conflict report to {DUPLICATE_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
