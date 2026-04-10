"""Unit tests for the player name/ID normalization layer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ingest.player_ids import (
    CROSSWALK_COLUMNS,
    attach_gsis_id_by_fantasy_data_id,
    attach_gsis_id_by_name,
    normalize_name,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ff_playerids_sample.csv"


@pytest.fixture(scope="module")
def crosswalk() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE, dtype={"fantasy_data_id": "string"})
    missing = [c for c in CROSSWALK_COLUMNS if c not in df.columns]
    assert not missing, f"fixture missing columns: {missing}"
    return df


def test_normalize_name_strips_suffix_and_punct():
    assert normalize_name("Travis Etienne Jr.") == "travis etienne"
    assert normalize_name("A.J. Brown") == "a j brown"
    assert normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert normalize_name("  Justin   Jefferson  ") == "justin jefferson"
    assert normalize_name("Patrick Mahomes II") == "patrick mahomes"


def test_attach_gsis_by_fantasy_data_id_travis_etienne(crosswalk):
    df = pd.DataFrame(
        [
            {
                "player_id": "21696",
                "player": "Travis Etienne Jr.",
                "position": "RB",
            }
        ]
    )
    out = attach_gsis_id_by_fantasy_data_id(df, crosswalk=crosswalk)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["gsis_id"] == "00-0036973"
    assert int(row["fantasypros_id"]) == 19231
    assert row["id_match_source"] == "fantasy_data_id"


def test_attach_gsis_by_fantasy_data_id_unmatched(crosswalk):
    df = pd.DataFrame(
        [{"player_id": "999999", "player": "Nobody Real", "position": "QB"}]
    )
    out = attach_gsis_id_by_fantasy_data_id(df, crosswalk=crosswalk)
    row = out.iloc[0]
    assert pd.isna(row["gsis_id"])
    assert pd.isna(row["id_match_source"])


def test_attach_gsis_by_name_travis_etienne(crosswalk):
    df = pd.DataFrame(
        [{"player": "Travis Etienne Jr.", "position": "RB"}]
    )
    out = attach_gsis_id_by_name(df, crosswalk=crosswalk)
    row = out.iloc[0]
    assert row["gsis_id"] == "00-0036973"
    assert row["fantasy_data_id"] == "21696"
    assert row["id_match_source"] == "merge_name+position"


def test_attach_gsis_by_name_unmatched_is_null(crosswalk):
    df = pd.DataFrame([{"player": "Completely Made Up", "position": "WR"}])
    out = attach_gsis_id_by_name(df, crosswalk=crosswalk)
    row = out.iloc[0]
    assert pd.isna(row["gsis_id"])
    assert pd.isna(row["id_match_source"])


def test_attach_gsis_by_name_ambiguous_position_collision(crosswalk):
    # Fixture contains two "Michael Pittman" rows at different positions
    # (WR = Michael Pittman Jr., RB = an older player). A WR query must
    # resolve uniquely to the WR row, not collide.
    df = pd.DataFrame(
        [{"player": "Michael Pittman Jr.", "position": "WR"}]
    )
    out = attach_gsis_id_by_name(df, crosswalk=crosswalk)
    row = out.iloc[0]
    assert row["gsis_id"] == "00-0036252"
    assert row["id_match_source"] == "merge_name+position"
