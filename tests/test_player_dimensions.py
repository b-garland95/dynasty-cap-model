"""Unit tests for the player dimensions ingest layer."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ingest.player_dimensions import (
    DIMENSION_COLUMNS,
    load_player_dimensions,
    enrich_with_player_dimensions,
)

FIXTURE = Path(__file__).parent / "fixtures" / "player_dimensions_sample.csv"

TRAVIS_GSIS = "00-0036973"
MAC_GSIS = "00-0037013"
AJ_GSIS = "00-0035676"
UNDRAFTED_GSIS = "00-0099001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dims() -> pd.DataFrame:
    """Load dimensions from the sample fixture CSV (no live network call)."""
    df = pd.read_csv(FIXTURE)
    missing = [c for c in DIMENSION_COLUMNS if c not in df.columns]
    assert not missing, f"fixture missing columns: {missing}"
    return df


# ---------------------------------------------------------------------------
# load_player_dimensions
# ---------------------------------------------------------------------------

def test_load_player_dimensions_returns_dimension_columns(tmp_path):
    """Reading from a cache file (the fixture copy) returns exactly DIMENSION_COLUMNS."""
    import shutil
    cache = tmp_path / "dims.csv"
    shutil.copy(FIXTURE, cache)

    result = load_player_dimensions(cache_path=cache)

    assert list(result.columns) == DIMENSION_COLUMNS
    assert TRAVIS_GSIS in result["gsis_id"].values


def test_load_player_dimensions_reads_from_cache_without_network(tmp_path, monkeypatch):
    """When a valid cache file exists the live nflreadpy call is never made."""
    import shutil
    cache = tmp_path / "dims.csv"
    shutil.copy(FIXTURE, cache)

    # Poison the nflreadpy entry in sys.modules so any import would fail.
    monkeypatch.setitem(sys.modules, "nflreadpy", None)

    result = load_player_dimensions(cache_path=cache)  # must not raise
    assert len(result) > 0


def test_load_player_dimensions_raises_on_missing_columns(tmp_path):
    """Missing required columns raise a ValueError with the column names."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("gsis_id,display_name\n00-0000001,Test Player\n")

    with pytest.raises(ValueError, match="missing expected columns"):
        load_player_dimensions(cache_path=bad_csv)


# ---------------------------------------------------------------------------
# enrich_with_player_dimensions — age calculation
# ---------------------------------------------------------------------------

def test_age_travis_etienne_season_2021(dims):
    """Travis Etienne born 1999-06-13; integer age at Sep 1 2021 == 22."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert out.iloc[0]["age"] == 22.0


def test_age_aj_brown_season_2023(dims):
    """A.J. Brown born 1997-06-30; integer age at Sep 1 2023 == 26."""
    df = pd.DataFrame([{"gsis_id": AJ_GSIS, "season": 2023}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert out.iloc[0]["age"] == 26.0


def test_age_sep1_boundary(dims):
    """Dynasty convention: a player born on Sep 2 has NOT turned that age yet
    at the Sep 1 cutoff; a player born on Sep 1 has just turned it."""
    # Use a synthetic dims table so we don't depend on real fixture players.
    synthetic_dims = pd.DataFrame([
        {"gsis_id": "SYN-SEPT1", "birth_date": "1995-09-01",
         "display_name": "Sep1 Player", "rookie_season": 2017,
         "draft_year": 2017, "draft_round": 1, "draft_pick": 10,
         "height": 72, "weight": 200, "college_name": "Test",
         "status": "Active", "pfr_id": None, "espn_id": None},
        {"gsis_id": "SYN-SEPT2", "birth_date": "1995-09-02",
         "display_name": "Sep2 Player", "rookie_season": 2017,
         "draft_year": 2017, "draft_round": 1, "draft_pick": 11,
         "height": 72, "weight": 200, "college_name": "Test",
         "status": "Active", "pfr_id": None, "espn_id": None},
    ])
    df = pd.DataFrame([
        {"gsis_id": "SYN-SEPT1", "season": 2024},
        {"gsis_id": "SYN-SEPT2", "season": 2024},
    ])
    out = enrich_with_player_dimensions(df, dims=synthetic_dims)

    sep1_age = float(out.loc[out["gsis_id"] == "SYN-SEPT1", "age"].iloc[0])
    sep2_age = float(out.loc[out["gsis_id"] == "SYN-SEPT2", "age"].iloc[0])

    # Born Sep 1 1995: turns 29 on Sep 1 2024 — exactly at the cutoff
    assert sep1_age == 29.0, f"Expected 29, got {sep1_age}"
    # Born Sep 2 1995: turns 29 on Sep 2 2024 — one day AFTER the cutoff → still 28
    assert sep2_age == 28.0, f"Expected 28, got {sep2_age}"


def test_age_is_nan_for_unmatched_gsis(dims):
    """A gsis_id not in the fixture produces NaN age."""
    df = pd.DataFrame([{"gsis_id": "XX-UNKNOWN", "season": 2022}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert pd.isna(out.iloc[0]["age"])


# ---------------------------------------------------------------------------
# enrich_with_player_dimensions — years_of_experience
# ---------------------------------------------------------------------------

def test_yoe_zero_in_rookie_season(dims):
    """years_of_experience == 0 in the player's rookie season."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert out.iloc[0]["years_of_experience"] == 0


def test_yoe_three_after_three_seasons(dims):
    """years_of_experience == 3 in the fourth season (rookie + 3)."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2024}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert out.iloc[0]["years_of_experience"] == 3


def test_yoe_never_negative(dims):
    """years_of_experience clips at 0 — never returns a negative value."""
    # Season before rookie year (shouldn't happen in practice but must be safe).
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2019}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert out.iloc[0]["years_of_experience"] == 0


def test_yoe_is_na_for_unmatched_gsis(dims):
    """Unmatched player has NA years_of_experience (not 0 or negative)."""
    df = pd.DataFrame([{"gsis_id": "XX-UNKNOWN", "season": 2022}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert pd.isna(out.iloc[0]["years_of_experience"])


# ---------------------------------------------------------------------------
# enrich_with_player_dimensions — is_rookie
# ---------------------------------------------------------------------------

def test_is_rookie_true_in_rookie_season(dims):
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert bool(out.iloc[0]["is_rookie"]) is True


def test_is_rookie_false_year_after_rookie_season(dims):
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2022}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert bool(out.iloc[0]["is_rookie"]) is False


def test_is_rookie_false_for_unmatched_gsis(dims):
    """Safe default: unmatched players are not considered rookies."""
    df = pd.DataFrame([{"gsis_id": "XX-UNKNOWN", "season": 2022}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert bool(out.iloc[0]["is_rookie"]) is False


# ---------------------------------------------------------------------------
# enrich_with_player_dimensions — log_draft_number
# ---------------------------------------------------------------------------

def test_log_draft_number_drafted_player(dims):
    """Travis Etienne: pick 54 → log(54) ≈ 3.989."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert abs(out.iloc[0]["log_draft_number"] - np.log(54)) < 1e-6


def test_log_draft_number_first_overall_pick(dims):
    """Mac Jones: pick 15 → log(15) ≈ 2.708."""
    df = pd.DataFrame([{"gsis_id": MAC_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert abs(out.iloc[0]["log_draft_number"] - np.log(15)) < 1e-6


def test_log_draft_number_nan_for_undrafted(dims):
    """Undrafted player (null draft_pick) produces NaN log_draft_number."""
    df = pd.DataFrame([{"gsis_id": UNDRAFTED_GSIS, "season": 2023}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert pd.isna(out.iloc[0]["log_draft_number"])


def test_log_draft_number_nan_for_unmatched_gsis(dims):
    df = pd.DataFrame([{"gsis_id": "XX-UNKNOWN", "season": 2022}])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert pd.isna(out.iloc[0]["log_draft_number"])


# ---------------------------------------------------------------------------
# enrich_with_player_dimensions — join behavior
# ---------------------------------------------------------------------------

def test_unmatched_gsis_id_not_dropped(dims):
    """Players missing from the dimension table are kept; dim cols are NaN."""
    df = pd.DataFrame([
        {"gsis_id": TRAVIS_GSIS, "season": 2021},  # matched
        {"gsis_id": "XX-UNKNOWN", "season": 2021},  # unmatched
    ])
    out = enrich_with_player_dimensions(df, dims=dims)

    assert len(out) == 2
    unmatched = out[out["gsis_id"] == "XX-UNKNOWN"].iloc[0]
    assert pd.isna(unmatched["birth_date"])
    assert pd.isna(unmatched["age"])
    assert pd.isna(unmatched["log_draft_number"])


def test_all_static_dimension_columns_present(dims):
    """Enriched output contains every column from DIMENSION_COLUMNS (except gsis_id which was already there)."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)

    for col in DIMENSION_COLUMNS:
        assert col in out.columns, f"missing dimension column: {col}"


def test_derived_columns_present(dims):
    """All four derived columns are added to the output."""
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021}])
    out = enrich_with_player_dimensions(df, dims=dims)

    for col in ("age", "years_of_experience", "is_rookie", "log_draft_number"):
        assert col in out.columns, f"missing derived column: {col}"


def test_original_columns_unchanged(dims):
    """Enrichment does not remove or rename any of the caller's existing columns."""
    original_cols = ["gsis_id", "season", "sav", "esv"]
    df = pd.DataFrame([{"gsis_id": TRAVIS_GSIS, "season": 2021, "sav": 42.0, "esv": 30.0}])
    out = enrich_with_player_dimensions(df, dims=dims)

    for col in original_cols:
        assert col in out.columns


def test_row_count_preserved_multi_season(dims):
    """Enriching a multi-season DataFrame does not change the row count."""
    df = pd.DataFrame([
        {"gsis_id": TRAVIS_GSIS, "season": 2021},
        {"gsis_id": TRAVIS_GSIS, "season": 2022},
        {"gsis_id": TRAVIS_GSIS, "season": 2023},
        {"gsis_id": AJ_GSIS, "season": 2022},
    ])
    out = enrich_with_player_dimensions(df, dims=dims)
    assert len(out) == len(df)


def test_missing_gsis_id_column_raises(dims):
    """DataFrame without gsis_id raises ValueError."""
    df = pd.DataFrame([{"player": "Travis Etienne", "season": 2021}])
    with pytest.raises(ValueError, match="gsis_id"):
        enrich_with_player_dimensions(df, dims=dims)
