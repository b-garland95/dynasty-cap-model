"""
Compute position-specific availability rates for the Roster-Adjusted Value (RAV) model.

Methodology:
  1. Take the top-150 pre-season ranked players in each historical season
     (from redraft_rankings_master.csv, filtered by rank <= 150).
  2. Count the number of regular-season weeks each player appeared in the
     historical weekly points data.
  3. Divide by the total number of regular-season games that season
     (17 for 2021+, 16 for prior years).
  4. Average availability rates by position across all seasons.

Output: data/processed/rav_availability_rates.csv
  Columns: position, avg_availability_rate, seasons_sampled, player_season_count

Run: python scripts/compute_rav_availability_rates.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent

RANKINGS_PATH = REPO_ROOT / "data/interim/redraft_rankings_master.csv"
WEEKLY_POINTS_PATH = REPO_ROOT / "data/interim/historical_weekly_player_points_2015_2025.csv"
OUTPUT_PATH = REPO_ROOT / "data/processed/rav_availability_rates.csv"

TOP_N = 150
POSITIONS = ["QB", "RB", "WR", "TE"]

# Season length by era
def season_games(season: int) -> int:
    return 17 if season >= 2021 else 16


def main() -> None:
    rankings = pd.read_csv(RANKINGS_PATH)
    weekly = pd.read_csv(WEEKLY_POINTS_PATH)

    # Keep only regular season weeks and relevant positions
    weekly = weekly[weekly["season_type"] == "REG"]
    weekly = weekly[weekly["position"].isin(POSITIONS)]

    # Count distinct weeks appeared per player per season
    games_played = (
        weekly.groupby(["season", "player_id", "position"])["week"]
        .nunique()
        .reset_index(name="weeks_appeared")
    )

    # Filter rankings to top-150 per season, known positions only
    rankings = rankings[rankings["position"].isin(POSITIONS)].copy()
    ranked = rankings[rankings["gsis_id"].notna()].sort_values(["season", "rank"])
    # Use rank-based filtering: keep rows where within-season rank position <= TOP_N
    ranked["_within_season_rank"] = ranked.groupby("season")["rank"].rank(method="first")
    top150 = ranked[ranked["_within_season_rank"] <= TOP_N].drop(columns=["_within_season_rank"]).reset_index(drop=True)

    # Join to get weeks appeared; players who didn't appear get 0
    merged = top150.merge(
        games_played,
        left_on=["season", "gsis_id", "position"],
        right_on=["season", "player_id", "position"],
        how="left",
    )
    merged["weeks_appeared"] = merged["weeks_appeared"].fillna(0).astype(int)
    merged["total_games"] = merged["season"].apply(season_games)
    merged["availability_rate"] = merged["weeks_appeared"] / merged["total_games"]

    # Aggregate by position
    summary = (
        merged.groupby("position")
        .agg(
            avg_availability_rate=("availability_rate", "mean"),
            seasons_sampled=("season", "nunique"),
            player_season_count=("gsis_id", "count"),
        )
        .reset_index()
        .sort_values("position")
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_PATH, index=False)

    print("RAV availability rates by position:")
    print(summary.to_string(index=False, float_format="%.4f"))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
