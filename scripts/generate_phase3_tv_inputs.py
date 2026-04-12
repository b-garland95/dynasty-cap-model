from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.tv_inputs import build_phase2_tv_inputs
from src.ingest.player_dimensions import enrich_with_player_dimensions
from src.ingest.player_ids import attach_gsis_id_by_name, load_player_id_crosswalk

DEFAULT_ROSTER_CSV = REPO_ROOT / "data" / "raw" / "roster_exports" / "lbb_rosters_2025.csv"
DEFAULT_TRAINING_CSV = REPO_ROOT / "data" / "interim" / "phase2_training_dataset.csv"
DEFAULT_RANKINGS_CSV = REPO_ROOT / "data" / "interim" / "redraft_rankings_master.csv"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "data" / "interim" / "phase3" / "tv_inputs.csv"
DEFAULT_TARGET_SEASON = 2026
DIMS_CACHE = REPO_ROOT / "data" / "interim" / "player_dimensions_raw.csv"


def main() -> int:
    roster_csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROSTER_CSV
    output_csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_CSV

    training_df = pd.read_csv(DEFAULT_TRAINING_CSV, dtype={"gsis_id": "string"})
    rankings_df = pd.read_csv(DEFAULT_RANKINGS_CSV, dtype={"gsis_id": "string"})

    tv_inputs_df = build_phase2_tv_inputs(
        roster_csv_path=str(roster_csv_path),
        training_df=training_df,
        redraft_rankings_df=rankings_df,
        target_season=DEFAULT_TARGET_SEASON,
    )

    # Attach gsis_id via player-name crosswalk so we can join player dimensions.
    # tv_inputs have no id column (League Tycoon roster exports are name-only).
    try:
        crosswalk = load_player_id_crosswalk()
        tv_inputs_df = attach_gsis_id_by_name(
            tv_inputs_df, name_col="player", position_col="position", crosswalk=crosswalk
        )
        # Drop housekeeping columns added by the attach helper.
        drop_cols = [c for c in ("id_match_source", "fantasy_data_id", "fantasypros_id")
                     if c in tv_inputs_df.columns]
        tv_inputs_df = tv_inputs_df.drop(columns=drop_cols)

        # Enrich with player dimensions using a temporary season column.
        dims_kwargs = {"cache_path": DIMS_CACHE} if DIMS_CACHE.exists() else {}
        tv_inputs_df["_season"] = DEFAULT_TARGET_SEASON
        tv_inputs_df = enrich_with_player_dimensions(tv_inputs_df, season_col="_season", **dims_kwargs)
        tv_inputs_df = tv_inputs_df.drop(columns=["_season"])
        print("Attached gsis_id and player dimensions (age, draft info, …)")
    except Exception as exc:
        print(f"  Warning: player dimensions enrichment failed ({exc.__class__.__name__}); skipping")

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    tv_inputs_df.to_csv(output_csv_path, index=False)

    matched = int(tv_inputs_df["matched_rankings"].sum())
    rostered = int(tv_inputs_df["is_rostered"].sum())
    print(f"Wrote {len(tv_inputs_df)} Phase 3 TV input rows to {output_csv_path}")
    print(f"Scored 2026 redraft ranks for {matched} of {len(tv_inputs_df)} projected players")
    print(f"Matched fantasy-roster slots for {rostered} of {len(tv_inputs_df)} projected players")
    print(f"Unscored players defaulted to zero TV for v1: {len(tv_inputs_df) - matched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
