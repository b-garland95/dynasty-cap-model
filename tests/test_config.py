"""Structural tests for league_config.yaml.

These tests check that required keys exist, values are within plausible ranges,
and cross-key invariants hold — not that specific hardcoded values match.
Changing a config value should not break these tests unless it goes out of range.
"""

from __future__ import annotations

import pytest

from src.utils.config import load_league_config, validate_league_config


# ---------------------------------------------------------------------------
# Config loads and validates without error
# ---------------------------------------------------------------------------

def test_load_league_config_succeeds():
    config = load_league_config()
    assert isinstance(config, dict)


def test_validate_league_config_passes_on_default():
    config = load_league_config()
    validate_league_config(config)  # must not raise


# ---------------------------------------------------------------------------
# Top-level required keys exist
# ---------------------------------------------------------------------------

def test_required_top_level_keys_present():
    config = load_league_config()
    for key in ("league", "lineup", "roster", "cap", "valuation",
                "capture_model", "season", "player_positions"):
        assert key in config, f"Missing top-level config key: {key!r}"


# ---------------------------------------------------------------------------
# League section
# ---------------------------------------------------------------------------

def test_league_teams_is_positive_integer():
    teams = load_league_config()["league"]["teams"]
    assert isinstance(teams, int)
    assert teams > 0


# ---------------------------------------------------------------------------
# Lineup section
# ---------------------------------------------------------------------------

def test_lineup_slot_counts_are_positive():
    lineup = load_league_config()["lineup"]
    for slot in ("qb", "rb", "wr", "te", "flex", "superflex"):
        assert slot in lineup, f"Missing lineup slot: {slot!r}"
        assert int(lineup[slot]) >= 0, f"Lineup slot {slot!r} is negative"


def test_lineup_total_starters_is_positive():
    lineup = load_league_config()["lineup"]
    total = sum(int(lineup[s]) for s in ("qb", "rb", "wr", "te", "flex", "superflex"))
    assert total > 0, "Total lineup starters must be > 0"


def test_lineup_has_fallback_slots_for_all_positions():
    config = load_league_config()
    fallback = config["lineup"].get("fallback_slots", {})
    for pos in config["player_positions"]:
        assert pos in fallback, f"No fallback_slot defined for position {pos!r}"


# ---------------------------------------------------------------------------
# Cap section
# ---------------------------------------------------------------------------

def test_cap_base_cap_is_positive():
    cap = load_league_config()["cap"]
    assert float(cap["base_cap"]) > 0


def test_cap_inflation_is_in_plausible_range():
    inflation = float(load_league_config()["cap"]["annual_inflation"])
    assert 0.0 <= inflation <= 0.50, f"annual_inflation={inflation} outside [0, 0.5]"


def test_cap_discount_rate_is_in_plausible_range():
    dr = float(load_league_config()["cap"]["discount_rate"])
    assert 0.0 < dr < 1.0, f"discount_rate={dr} not in (0, 1)"


# ---------------------------------------------------------------------------
# Player positions
# ---------------------------------------------------------------------------

def test_player_positions_is_non_empty_list():
    positions = load_league_config()["player_positions"]
    assert isinstance(positions, list)
    assert len(positions) > 0


def test_player_positions_are_strings():
    for pos in load_league_config()["player_positions"]:
        assert isinstance(pos, str), f"Non-string position: {pos!r}"


# ---------------------------------------------------------------------------
# Season section
# ---------------------------------------------------------------------------

def test_season_has_required_keys():
    season = load_league_config()["season"]
    for key in ("current_season", "target_season", "history_start_season", "num_regular_weeks"):
        assert key in season, f"Missing season key: {key!r}"


def test_target_season_gte_current_season():
    season = load_league_config()["season"]
    assert int(season["target_season"]) >= int(season["current_season"])


def test_history_start_season_lte_current_season():
    season = load_league_config()["season"]
    assert int(season["history_start_season"]) <= int(season["current_season"])


def test_num_regular_weeks_is_plausible():
    nw = int(load_league_config()["season"]["num_regular_weeks"])
    assert 1 <= nw <= 22, f"num_regular_weeks={nw} outside plausible NFL range"


# ---------------------------------------------------------------------------
# Valuation section — shrinkage lambdas
# ---------------------------------------------------------------------------

def test_shrinkage_lambdas_are_in_unit_interval():
    lambdas = load_league_config()["valuation"]["shrinkage_lambdas"]
    for slot, lam in lambdas.items():
        assert 0.0 <= float(lam) <= 1.0, f"shrinkage_lambda[{slot!r}]={lam} outside [0,1]"
