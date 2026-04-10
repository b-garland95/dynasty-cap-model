from pathlib import Path

import pandas as pd

from src.ingest.historical_weekly_points import (
    CANONICAL_COLUMNS,
    compute_weekly_fantasy_points,
    get_config_player_positions,
    normalize_historical_weekly_points,
    normalize_historical_weekly_points_csv,
)
from src.utils.config import load_league_config


def test_get_config_player_positions_reads_config_values():
    config = load_league_config()
    assert get_config_player_positions(config) == ["QB", "RB", "WR", "TE"]


def test_compute_weekly_fantasy_points_uses_half_ppr_scoring():
    config = load_league_config()
    raw_df = pd.DataFrame(
        {
            "fantasy_points": [10.0, 5.5],
            "receptions": [4, 0],
        }
    )

    points = compute_weekly_fantasy_points(raw_df, config)
    assert points.tolist() == [12.0, 5.5]


def test_normalize_historical_weekly_points_filters_and_renames():
    config = load_league_config()
    raw_df = pd.DataFrame(
        [
            {
                "season": 2015,
                "week": 1,
                "player_id": "p1",
                "player_display_name": "Alpha QB",
                "position": "QB",
                "recent_team": "BUF",
                "opponent_team": "NYJ",
                "season_type": "REG",
                "fantasy_points": 20.0,
                "receptions": 0,
            },
            {
                "season": 2015,
                "week": 15,
                "player_id": "p2",
                "player_display_name": "Beta WR",
                "position": "WR",
                "recent_team": "KC",
                "opponent_team": "LAC",
                "season_type": "REG",
                "fantasy_points": 10.0,
                "receptions": 6,
            },
            {
                "season": 2015,
                "week": 1,
                "player_id": "p3",
                "player_display_name": "Gamma K",
                "position": "K",
                "recent_team": "DAL",
                "opponent_team": "PHI",
                "season_type": "REG",
                "fantasy_points": 8.0,
                "receptions": 0,
            },
            {
                "season": 2016,
                "week": 1,
                "player_id": "p4",
                "player_display_name": "Delta RB",
                "position": "RB",
                "recent_team": "MIA",
                "opponent_team": "NE",
                "season_type": "POST",
                "fantasy_points": 12.0,
                "receptions": 2,
            },
        ]
    )

    normalized = normalize_historical_weekly_points(
        raw_df=raw_df,
        config=config,
        start_season=2015,
        end_season=2015,
        loaded_at="2026-03-16T00:00:00+00:00",
    )

    assert normalized.columns.tolist() == CANONICAL_COLUMNS
    assert normalized["player"].tolist() == ["Alpha QB", "Beta WR"]
    assert normalized["position"].tolist() == ["QB", "WR"]
    assert normalized["points"].tolist() == [20.0, 13.0]
    assert normalized["games_played"].tolist() == [1, 1]
    assert normalized["season_type"].tolist() == ["REG", "REG"]
    assert normalized["source"].nunique() == 1


def test_normalize_historical_weekly_points_accepts_player_name_fallback():
    config = load_league_config()
    raw_df = pd.DataFrame(
        [
            {
                "season": 2017,
                "week": 2,
                "player_id": "p9",
                "player_name": "Fallback Name",
                "position_group": "TE",
                "team": "BAL",
                "opponent": "PIT",
                "season_type": "REG",
                "fantasy_points": 4.0,
                "receptions": 2,
            }
        ]
    )

    normalized = normalize_historical_weekly_points(
        raw_df=raw_df,
        config=config,
        start_season=2017,
        end_season=2017,
        loaded_at="2026-03-16T00:00:00+00:00",
    )

    assert normalized.loc[0, "player"] == "Fallback Name"
    assert normalized.loc[0, "position"] == "TE"
    assert normalized.loc[0, "team"] == "BAL"
    assert normalized.loc[0, "opponent"] == "PIT"
    assert normalized.loc[0, "points"] == 5.0


def test_normalize_historical_weekly_points_csv_writes_output(tmp_path: Path):
    config = load_league_config()
    raw_csv_path = tmp_path / "raw.csv"
    output_path = tmp_path / "normalized.csv"

    pd.DataFrame(
        [
            {
                "season": 2020,
                "week": 1,
                "player_id": "p1",
                "player_display_name": "Alpha QB",
                "position": "QB",
                "recent_team": "BUF",
                "opponent_team": "NYJ",
                "season_type": "REG",
                "fantasy_points": 20.0,
                "receptions": 0,
            }
        ]
    ).to_csv(raw_csv_path, index=False)

    normalized = normalize_historical_weekly_points_csv(
        raw_csv_path=str(raw_csv_path),
        config=config,
        start_season=2015,
        end_season=2025,
        output_path=str(output_path),
    )

    written = pd.read_csv(output_path)
    assert output_path.exists()
    assert normalized.columns.tolist() == CANONICAL_COLUMNS
    assert written.columns.tolist() == CANONICAL_COLUMNS
    assert len(written) == 1
    assert written.loc[0, "player"] == "Alpha QB"
    assert float(written.loc[0, "points"]) == 20.0
