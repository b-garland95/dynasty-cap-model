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
CURRENT_2025_DIR = REPO_ROOT / "data" / "interim" / "weekly_projections_2025"
CURRENT_2025_ALL_WEEKS_PATH = REPO_ROOT / "data" / "interim" / "weekly_projections_2025_all_weeks_normalized.csv"
MASTER_OUTPUT_PATH = REPO_ROOT / "data" / "interim" / "weekly_projections_2014_2025_master_normalized.csv"
DUPLICATE_REPORT_PATH = REPO_ROOT / "data" / "processed" / "projection_duplicate_conflicts" / "legacy_projection_key_conflicts_2014_2024.csv"



def build_master_weekly_projections(config: dict) -> tuple[object, object, object]:
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
    for week in range(1, 19):
        raw_path = REPO_ROOT / "data" / "raw" / f"fantasydata_weekly_projections_2025_week{week}_raw.csv"
        normalized_path = CURRENT_2025_DIR / f"weekly_projections_2025_week{week}_normalized.csv"
        current_frames.append(
            normalize_weekly_projections_csv(
                raw_csv_path=str(raw_path),
                config=config,
                output_path=str(normalized_path),
                season=2025,
            )
        )

    current_df = combine_normalized_weekly_projections(current_frames)
    CURRENT_2025_ALL_WEEKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current_df.to_csv(CURRENT_2025_ALL_WEEKS_PATH, index=False)

    master_df = combine_normalized_weekly_projections([legacy_df, current_df])
    MASTER_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    master_df.to_csv(MASTER_OUTPUT_PATH, index=False)
    return legacy_df, current_df, master_df



def main() -> int:
    config = load_league_config()
    legacy_df, current_df, master_df = build_master_weekly_projections(config)
    print(f"Wrote {len(legacy_df)} rows to {LEGACY_NORMALIZED_PATH}")
    print(f"Wrote {len(current_df)} rows to {CURRENT_2025_ALL_WEEKS_PATH}")
    print(f"Wrote {len(master_df)} rows to {MASTER_OUTPUT_PATH}")
    if DUPLICATE_REPORT_PATH.exists():
        print(f"Wrote legacy conflict report to {DUPLICATE_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
