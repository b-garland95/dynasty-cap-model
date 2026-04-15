"""
Export a slim player headshots lookup CSV for the dashboard.

Joins:
  - data/processed/phase1/phase1_season_values.csv  (gsis_id + player name)
  - data/interim/player_dimensions_raw.csv          (gsis_id + headshot URL + bio)

Output: data/processed/player_headshots.csv
Columns: gsis_id, player, headshot_url, position, birth_date, height, weight,
         college_name, draft_year, draft_round, draft_pick, rookie_season
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
SEASON_VALUES = ROOT / "data/processed/phase1/phase1_season_values.csv"
PLAYER_DIMS   = ROOT / "data/interim/player_dimensions_raw.csv"
OUTPUT        = ROOT / "data/processed/player_headshots.csv"

DIM_COLS = [
    "gsis_id", "headshot", "birth_date", "height", "weight",
    "college_name", "draft_year", "draft_round", "draft_pick", "rookie_season",
]

def main():
    season = pd.read_csv(SEASON_VALUES, usecols=["gsis_id", "player", "position"])
    dims   = pd.read_csv(PLAYER_DIMS, usecols=DIM_COLS)

    # Unique player → gsis_id mapping; keep first occurrence if duplicates
    players = (
        season[["gsis_id", "player", "position"]]
        .drop_duplicates(subset=["gsis_id"])
        .reset_index(drop=True)
    )

    merged = players.merge(
        dims.rename(columns={"headshot": "headshot_url"}),
        on="gsis_id",
        how="left",
    )

    col_order = [
        "gsis_id", "player", "headshot_url", "position",
        "birth_date", "height", "weight", "college_name",
        "draft_year", "draft_round", "draft_pick", "rookie_season",
    ]
    merged = merged[col_order]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT, index=False)

    total     = len(merged)
    with_shot = merged["headshot_url"].notna().sum()
    print(f"Exported {total} players → {OUTPUT}")
    print(f"Headshots found: {with_shot}/{total} ({100*with_shot/total:.1f}%)")


if __name__ == "__main__":
    main()
