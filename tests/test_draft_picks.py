"""Tests for src/contracts/draft_picks.py — pick ownership management.

Coverage:
- generate_picks: correct pick IDs, years, salaries from config
- load_ownership / save_ownership: round-trip persistence
- get_team_picks: filtering and ordering
- build_inventory_table: merge of picks + ownership
- Edge cases: missing file, partial ownership, top-of-draft edge pick salaries
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.contracts.draft_picks import (
    all_teams_from_ownership,
    build_inventory_table,
    generate_picks,
    get_team_picks,
    load_ownership,
    save_ownership,
)
from src.utils.config import load_league_config


# ---------------------------------------------------------------------------
# Minimal config fixture (avoids file I/O for most tests)
# ---------------------------------------------------------------------------

def _minimal_config(
    target_season: int = 2026,
    future_years: int = 2,
    rounds: int = 4,
    picks_per_round: int = 4,  # small for fast tests
) -> dict:
    return {
        "league": {"teams": picks_per_round, "scoring": {"half_ppr": True}},
        "season": {
            "current_season": 2025,
            "target_season": target_season,
            "history_start_season": 2015,
            "num_regular_weeks": 18,
            "regular_weeks": [1, 14],
            "playoff_weeks": [15, 17],
        },
        "draft_picks": {
            "future_years_tracked": future_years,
            "rounds": rounds,
            "picks_per_round": picks_per_round,
        },
        "rookie_scale": {
            "round1": {
                "1.01": 14,
                "1.02": 12,
                "1.03": 10,
                "1.04": 8,
            },
            "round2_salary": 4,
            "round3_salary": 2,
            "round4_salary": 1,
            "contract_years": 3,
            "option_years": 1,
            "option_use_it_or_lose_it": True,
            "options_per_team_per_year": 1,
        },
        "lineup": {"qb": 1, "rb": 2, "wr": 3, "te": 1, "flex": 2, "superflex": 1,
                   "fallback_slots": {"QB": "SF", "RB": "FLEX", "WR": "FLEX", "TE": "FLEX"}},
        "roster": {"bench": 8, "ir_slots": 3, "practice_squad_slots": 10},
        "cap": {"base_cap": 300, "annual_inflation": 0.10, "discount_rate": 0.25},
        "valuation": {"shrinkage_lambdas": {"QB": 0.55, "RB": 0.45, "WR": 0.45, "TE": 0.60,
                                            "FLEX": 0.40, "SF": 0.50},
                      "unranked_start_prob": 0.0},
        "capture_model": {
            "tau_by_slot": {"QB": 2.0, "RB": 2.5, "WR": 3.0, "TE": 2.5, "FLEX": 3.0, "SF": 2.5},
            "roster_model": {"active_roster_spots_per_team": 18, "kappa": 1.5, "gamma": 0.03,
                             "salary_beta": 0.75, "cap_scale": 300, "stickiness_bonus": 0.15},
            "practice_squad_model": {"enabled": True, "cap_percent": 0.25, "rookie_draft_only": True,
                                     "assume_rookies_ps_eligible": True, "delta": 0.5, "kappa_ps": 1.5},
            "tau_margin_scaling": 0.3,
        },
        "player_positions": ["QB", "RB", "WR", "TE"],
    }


# ---------------------------------------------------------------------------
# generate_picks
# ---------------------------------------------------------------------------

class TestGeneratePicks:

    def test_total_pick_count(self):
        config = _minimal_config(future_years=2, rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        # 3 years × 4 rounds × 4 slots = 48
        assert len(picks) == 48

    def test_default_future_years_is_two(self):
        config = _minimal_config()
        config.pop("draft_picks")  # remove draft_picks so module uses default
        picks = generate_picks(config)
        years = sorted({p["year"] for p in picks})
        # default future_years_tracked=2 means 3 years total
        assert len(years) == 3

    def test_pick_ids_are_unique(self):
        config = _minimal_config()
        picks = generate_picks(config)
        ids = [p["pick_id"] for p in picks]
        assert len(ids) == len(set(ids))

    def test_pick_id_format(self):
        config = _minimal_config(target_season=2026, rounds=2, picks_per_round=3)
        picks = generate_picks(config)
        expected_prefix = "2026_1_01"
        assert any(p["pick_id"] == expected_prefix for p in picks)
        # Slot zero-padded to 2 digits
        assert all(len(p["pick_id"].split("_")[2]) == 2 for p in picks)

    def test_year_range_matches_target_plus_future(self):
        config = _minimal_config(target_season=2026, future_years=2)
        picks = generate_picks(config)
        years = sorted({p["year"] for p in picks})
        assert years == [2026, 2027, 2028]

    def test_round1_salaries_from_rookie_scale(self):
        config = _minimal_config(rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        r1_picks = [p for p in picks if p["round"] == 1 and p["year"] == config["season"]["target_season"]]
        salaries = {p["slot"]: p["salary"] for p in r1_picks}
        assert salaries[1] == 14
        assert salaries[2] == 12
        assert salaries[3] == 10
        assert salaries[4] == 8

    def test_round2_3_4_flat_salaries(self):
        config = _minimal_config(rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        year = config["season"]["target_season"]
        r2 = [p for p in picks if p["year"] == year and p["round"] == 2]
        r3 = [p for p in picks if p["year"] == year and p["round"] == 3]
        r4 = [p for p in picks if p["year"] == year and p["round"] == 4]
        assert all(p["salary"] == 4 for p in r2)
        assert all(p["salary"] == 2 for p in r3)
        assert all(p["salary"] == 1 for p in r4)

    def test_uses_full_league_config(self):
        """generate_picks should work with the real league config."""
        config = load_league_config()
        picks = generate_picks(config)
        # With 10 teams, 4 rounds, 3 years tracked → 3 × 4 × 10 = 120
        dp = config["draft_picks"]
        expected = (dp["future_years_tracked"] + 1) * dp["rounds"] * dp["picks_per_round"]
        assert len(picks) == expected


# ---------------------------------------------------------------------------
# load_ownership / save_ownership round-trip
# ---------------------------------------------------------------------------

class TestOwnershipPersistence:

    def test_load_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            result = load_ownership(path)
            assert result == {}

    def test_save_and_reload_ownership(self):
        ownership = {
            "2026_1_01": "Team Alpha",
            "2026_1_02": None,
            "2026_2_03": "Team Beta",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "picks.json"
            save_ownership(ownership, path)
            assert path.exists()
            reloaded = load_ownership(path)
        assert reloaded == ownership

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "picks.json"
            save_ownership({"2026_1_01": "Team X"}, path)
            assert path.exists()

    def test_save_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "picks.json"
            ownership = {"2026_1_01": "Team A", "2026_1_02": None}
            save_ownership(ownership, path)
            raw = path.read_text()
            parsed = json.loads(raw)
        assert parsed == ownership

    def test_load_invalid_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text("[1, 2, 3]")
            with pytest.raises(ValueError, match="JSON object"):
                load_ownership(path)

    def test_save_empty_ownership(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "picks.json"
            save_ownership({}, path)
            reloaded = load_ownership(path)
        assert reloaded == {}


# ---------------------------------------------------------------------------
# get_team_picks
# ---------------------------------------------------------------------------

class TestGetTeamPicks:

    def _make_ownership(self) -> dict:
        return {
            "2026_1_01": "Team Alpha",
            "2026_1_02": "Team Beta",
            "2026_1_03": "Team Alpha",
            "2026_2_01": None,
            "2027_1_01": "Team Alpha",
        }

    def test_returns_correct_picks_for_team(self):
        ownership = self._make_ownership()
        result = get_team_picks(ownership, "Team Alpha")
        assert result == ["2026_1_01", "2026_1_03", "2027_1_01"]

    def test_returns_empty_for_unknown_team(self):
        ownership = self._make_ownership()
        assert get_team_picks(ownership, "Team Zzz") == []

    def test_result_is_sorted(self):
        ownership = {
            "2027_1_01": "Team A",
            "2026_1_01": "Team A",
            "2026_2_01": "Team A",
        }
        result = get_team_picks(ownership, "Team A")
        assert result == sorted(result)

    def test_universe_filter_excludes_picks_not_in_list(self):
        ownership = {
            "2026_1_01": "Team A",
            "2026_1_02": "Team A",
            "9999_1_01": "Team A",  # outside normal universe
        }
        picks = [
            {"pick_id": "2026_1_01"},
            {"pick_id": "2026_1_02"},
        ]
        result = get_team_picks(ownership, "Team A", picks=picks)
        assert "9999_1_01" not in result
        assert "2026_1_01" in result

    def test_none_owners_excluded(self):
        ownership = {"2026_1_01": None, "2026_1_02": "Team A"}
        result = get_team_picks(ownership, "Team A")
        assert result == ["2026_1_02"]


# ---------------------------------------------------------------------------
# build_inventory_table
# ---------------------------------------------------------------------------

class TestBuildInventoryTable:

    def test_merges_owner_into_picks(self):
        picks = [
            {"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1, "salary": 14},
            {"pick_id": "2026_1_02", "year": 2026, "round": 1, "slot": 2, "salary": 12},
        ]
        ownership = {"2026_1_01": "Team A", "2026_1_02": None}
        table = build_inventory_table(picks, ownership)
        assert table[0]["owner"] == "Team A"
        assert table[1]["owner"] is None

    def test_unowned_pick_has_none_owner(self):
        picks = [{"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1, "salary": 14}]
        table = build_inventory_table(picks, {})
        assert table[0]["owner"] is None

    def test_preserves_pick_order(self):
        config = _minimal_config(rounds=2, picks_per_round=3, future_years=0)
        picks = generate_picks(config)
        table = build_inventory_table(picks, {})
        assert [r["pick_id"] for r in table] == [p["pick_id"] for p in picks]

    def test_preserves_all_pick_fields(self):
        picks = [{"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1, "salary": 14}]
        ownership = {"2026_1_01": "Team X"}
        table = build_inventory_table(picks, ownership)
        row = table[0]
        assert row["year"] == 2026
        assert row["round"] == 1
        assert row["slot"] == 1
        assert row["salary"] == 14
        assert row["owner"] == "Team X"


# ---------------------------------------------------------------------------
# all_teams_from_ownership
# ---------------------------------------------------------------------------

class TestAllTeamsFromOwnership:

    def test_returns_sorted_unique_teams(self):
        ownership = {
            "2026_1_01": "Zebra FC",
            "2026_1_02": "Alpha United",
            "2026_1_03": "Alpha United",
            "2026_1_04": None,
        }
        result = all_teams_from_ownership(ownership)
        assert result == ["Alpha United", "Zebra FC"]

    def test_empty_ownership_returns_empty_list(self):
        assert all_teams_from_ownership({}) == []

    def test_all_unowned_returns_empty_list(self):
        assert all_teams_from_ownership({"2026_1_01": None}) == []
