from pathlib import Path

import pandas as pd
import pytest

from src.ingest.weekly_projections import (
    CANONICAL_PROJECTION_COLUMNS,
    PROJECTION_KEY_COLUMNS,
    combine_normalized_weekly_projections,
    detect_projection_schema,
    find_duplicate_projection_rows,
    normalize_weekly_projections,
    normalize_weekly_projections_csv,
    resolve_projection_key_conflicts,
    validate_unique_projection_keys,
)
from src.utils.config import load_league_config



def test_normalize_weekly_projections_legacy_schema():
    config = load_league_config()
    raw_df = pd.DataFrame(
        [
            {
                "Unnamed: 0": 0,
                "PlayerID": 7328,
                "Name": "Peyton Manning",
                "Team": "DEN",
                "Position": "QB",
                "Opponent": "IND",
                "Year": 2014,
                "Week": 1,
                "FantasyPointsHalfPointPpr": 25.78,
            },
            {
                "Unnamed: 0": 1,
                "PlayerID": 9999,
                "Name": "Kicker Guy",
                "Team": "BUF",
                "Position": "K",
                "Opponent": "NYJ",
                "Year": 2014,
                "Week": 1,
                "FantasyPointsHalfPointPpr": 10.0,
            },
        ]
    )

    normalized = normalize_weekly_projections(
        raw_df=raw_df,
        config=config,
        loaded_at="2026-03-17T00:00:00+00:00",
    )

    assert detect_projection_schema(raw_df) == "legacy"
    assert normalized.columns.tolist() == CANONICAL_PROJECTION_COLUMNS
    assert len(normalized) == 1
    assert normalized.loc[0, "season"] == 2014
    assert normalized.loc[0, "week"] == 1
    assert normalized.loc[0, "player_id"] == "7328"
    assert normalized.loc[0, "projected_points"] == 25.78



def test_normalize_weekly_projections_current_schema_requires_season_and_maps_fields():
    config = load_league_config()
    raw_df = pd.DataFrame(
        [
            {
                "rank": 1,
                "id": 19781,
                "player": "Lamar Jackson",
                "team": "BAL",
                "pos": "QB",
                "game.week": 1,
                "opp": "BUF",
                "fpts_half_ppr": 21.6,
            },
            {
                "rank": 2,
                "id": 77,
                "player": "Linebacker Guy",
                "team": "BAL",
                "pos": "LB",
                "game.week": 1,
                "opp": "BUF",
                "fpts_half_ppr": 8.0,
            },
        ]
    )

    with pytest.raises(ValueError, match="season is required"):
        normalize_weekly_projections(
            raw_df=raw_df,
            config=config,
            loaded_at="2026-03-17T00:00:00+00:00",
        )

    normalized = normalize_weekly_projections(
        raw_df=raw_df,
        config=config,
        loaded_at="2026-03-17T00:00:00+00:00",
        season=2025,
    )

    assert detect_projection_schema(raw_df) == "current"
    assert normalized.columns.tolist() == CANONICAL_PROJECTION_COLUMNS
    assert len(normalized) == 1
    assert normalized.loc[0, "season"] == 2025
    assert normalized.loc[0, "week"] == 1
    assert normalized.loc[0, "player"] == "Lamar Jackson"
    assert normalized.loc[0, "projected_points"] == 21.6



def test_normalize_weekly_projections_csv_writes_output(tmp_path: Path):
    config = load_league_config()
    raw_csv_path = tmp_path / "raw.csv"
    output_path = tmp_path / "normalized.csv"

    pd.DataFrame(
        [
            {
                "id": 19801,
                "player": "Josh Allen",
                "team": "BUF",
                "pos": "QB",
                "game.week": 1,
                "opp": "BAL",
                "fpts_half_ppr": 20.6,
            }
        ]
    ).to_csv(raw_csv_path, index=False)

    normalized = normalize_weekly_projections_csv(
        raw_csv_path=str(raw_csv_path),
        config=config,
        output_path=str(output_path),
        season=2025,
    )

    written = pd.read_csv(output_path)
    assert output_path.exists()
    assert normalized.columns.tolist() == CANONICAL_PROJECTION_COLUMNS
    assert written.columns.tolist() == CANONICAL_PROJECTION_COLUMNS
    assert len(written) == 1
    assert int(written.loc[0, "season"]) == 2025
    assert float(written.loc[0, "projected_points"]) == 20.6



def test_validate_unique_projection_keys_raises_for_duplicate_rows():
    df = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
        ]
    )

    with pytest.raises(ValueError, match="Duplicate projection keys detected"):
        validate_unique_projection_keys(df, context="test")



def test_find_duplicate_projection_rows_returns_duplicate_rows_sorted():
    df = pd.DataFrame(
        [
            {"season": 2025, "week": 2, "player_id": "2", "player": "B", "team": "KC", "position": "RB", "opponent": "LAC", "projected_points": 8.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "MIA", "position": "QB", "opponent": "BUF", "projected_points": 11.0, "source": "x", "loaded_at": "t"},
        ]
    )

    duplicate_rows = find_duplicate_projection_rows(df)

    assert len(duplicate_rows) == 2
    assert duplicate_rows[["season", "week", "player_id"]].drop_duplicates().values.tolist() == [[2025, 1, "1"]]
    assert duplicate_rows.iloc[0]["team"] == "BUF"
    assert duplicate_rows.iloc[1]["team"] == "MIA"



def test_resolve_projection_key_conflicts_keeps_highest_projection():
    df = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "MIA", "position": "QB", "opponent": "BUF", "projected_points": 11.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "2", "player": "B", "team": "KC", "position": "RB", "opponent": "LAC", "projected_points": 8.0, "source": "x", "loaded_at": "t"},
        ]
    )

    resolved = resolve_projection_key_conflicts(df)

    assert len(resolved) == 2
    assert resolved.loc[0, "team"] == "MIA"
    assert resolved.loc[0, "projected_points"] == 11.0
    validate_unique_projection_keys(resolved, context="resolved")



def test_resolve_projection_key_conflicts_keeps_first_row_on_tie():
    df = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "MIA", "position": "QB", "opponent": "BUF", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
        ]
    )

    resolved = resolve_projection_key_conflicts(df)

    assert len(resolved) == 1
    assert resolved.loc[0, "team"] == "BUF"



def test_normalize_weekly_projections_can_skip_validation_for_conflict_reporting():
    config = load_league_config()
    raw_df = pd.DataFrame(
        [
            {
                "PlayerID": 7328,
                "Name": "Peyton Manning",
                "Team": "DEN",
                "Position": "QB",
                "Opponent": "IND",
                "Year": 2014,
                "Week": 1,
                "FantasyPointsHalfPointPpr": 25.78,
            },
            {
                "PlayerID": 7328,
                "Name": "Peyton Manning",
                "Team": "NYJ",
                "Position": "QB",
                "Opponent": "BUF",
                "Year": 2014,
                "Week": 1,
                "FantasyPointsHalfPointPpr": 24.0,
            },
        ]
    )

    normalized = normalize_weekly_projections(
        raw_df=raw_df,
        config=config,
        loaded_at="2026-03-17T00:00:00+00:00",
        validate_keys=False,
    )

    assert len(normalized) == 2
    assert len(find_duplicate_projection_rows(normalized)) == 2



def test_combine_normalized_weekly_projections_raises_when_same_file_is_combined_twice():
    base = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
            {"season": 2025, "week": 1, "player_id": "2", "player": "B", "team": "KC", "position": "RB", "opponent": "LAC", "projected_points": 8.0, "source": "x", "loaded_at": "t"},
        ]
    )

    with pytest.raises(ValueError, match="Duplicate projection keys detected"):
        combine_normalized_weekly_projections([base, base.copy()])



def test_combine_normalized_weekly_projections_accepts_non_overlapping_weeks():
    week1 = pd.DataFrame(
        [
            {"season": 2025, "week": 1, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "NYJ", "projected_points": 10.0, "source": "x", "loaded_at": "t"},
        ]
    )
    week2 = pd.DataFrame(
        [
            {"season": 2025, "week": 2, "player_id": "1", "player": "A", "team": "BUF", "position": "QB", "opponent": "MIA", "projected_points": 11.0, "source": "x", "loaded_at": "t"},
        ]
    )

    combined = combine_normalized_weekly_projections([week2, week1])

    assert combined.columns.tolist() == CANONICAL_PROJECTION_COLUMNS
    assert PROJECTION_KEY_COLUMNS == ["season", "week", "player_id"]
    assert len(combined) == 2
    assert combined[["season", "week", "player_id"]].values.tolist() == [[2025, 1, "1"], [2025, 2, "1"]]



def test_combine_normalized_weekly_projections_raises_on_duplicate_weekly_uploads_from_files(tmp_path: Path):
    config = load_league_config()
    raw_week1 = tmp_path / "week1.csv"

    pd.DataFrame(
        [
            {
                "id": 19781,
                "player": "Lamar Jackson",
                "team": "BAL",
                "pos": "QB",
                "game.week": 1,
                "opp": "BUF",
                "fpts_half_ppr": 21.6,
            }
        ]
    ).to_csv(raw_week1, index=False)

    df1 = normalize_weekly_projections_csv(str(raw_week1), config=config, season=2025)
    df2 = normalize_weekly_projections_csv(str(raw_week1), config=config, season=2025)

    with pytest.raises(ValueError, match="Duplicate projection keys detected"):
        combine_normalized_weekly_projections([df1, df2])
