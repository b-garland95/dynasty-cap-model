"""Tests for src/contracts/draft_picks.py — pick ownership management.

Coverage:
- generate_picks: correct pick IDs, years, salaries, order_known, comp picks
- load_ownership / save_ownership: round-trip persistence + legacy migration
- get_team_picks: filtering by current owner
- build_inventory_table: merge of picks + ownership (original_team + owner)
- set_owner: trade ownership without changing original assignment
- make_pick_record: default owner equals original_team
- all_teams_from_ownership: unique current owners
- Edge cases: missing file, partial ownership, comp pick default empty owner
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
    make_pick_record,
    save_ownership,
    set_owner,
)
from src.utils.config import load_league_config


# ---------------------------------------------------------------------------
# Minimal config fixture
# ---------------------------------------------------------------------------

def _minimal_config(
    target_season: int = 2026,
    future_years: int = 2,
    rounds: int = 4,
    picks_per_round: int = 4,
    years_with_known_order: list[int] | None = None,
    compensatory_picks: list[dict] | None = None,
) -> dict:
    dp: dict = {
        "future_years_tracked": future_years,
        "rounds": rounds,
        "picks_per_round": picks_per_round,
        "years_with_known_order": years_with_known_order or [],
        "compensatory_picks": compensatory_picks or [],
    }
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
        "draft_picks": dp,
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
        "lineup": {
            "qb": 1, "rb": 2, "wr": 3, "te": 1, "flex": 2, "superflex": 1,
            "fallback_slots": {"QB": "SF", "RB": "FLEX", "WR": "FLEX", "TE": "FLEX"},
        },
        "roster": {"bench": 8, "ir_slots": 3, "practice_squad_slots": 10},
        "cap": {"base_cap": 300, "annual_inflation": 0.10, "discount_rate": 0.25},
        "valuation": {
            "shrinkage_lambdas": {
                "QB": 0.55, "RB": 0.45, "WR": 0.45, "TE": 0.60, "FLEX": 0.40, "SF": 0.50,
            },
            "unranked_start_prob": 0.0,
        },
        "capture_model": {
            "tau_by_slot": {
                "QB": 2.0, "RB": 2.5, "WR": 3.0, "TE": 2.5, "FLEX": 3.0, "SF": 2.5,
            },
            "roster_model": {
                "active_roster_spots_per_team": 18, "kappa": 1.5, "gamma": 0.03,
                "salary_beta": 0.75, "cap_scale": 300, "stickiness_bonus": 0.15,
            },
            "practice_squad_model": {
                "enabled": True, "cap_percent": 0.25, "rookie_draft_only": True,
                "assume_rookies_ps_eligible": True, "delta": 0.5, "kappa_ps": 1.5,
            },
            "tau_margin_scaling": 0.3,
        },
        "player_positions": ["QB", "RB", "WR", "TE"],
    }


# ---------------------------------------------------------------------------
# generate_picks
# ---------------------------------------------------------------------------

class TestGeneratePicks:

    def test_total_pick_count_no_comp(self):
        config = _minimal_config(future_years=2, rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        # 3 years × 4 rounds × 4 slots = 48
        assert len(picks) == 48

    def test_default_future_years_is_two(self):
        config = _minimal_config()
        config.pop("draft_picks")
        picks = generate_picks(config)
        years = sorted({p["year"] for p in picks})
        assert len(years) == 3

    def test_pick_ids_are_unique(self):
        config = _minimal_config()
        picks = generate_picks(config)
        ids = [p["pick_id"] for p in picks]
        assert len(ids) == len(set(ids))

    def test_pick_id_format(self):
        config = _minimal_config(target_season=2026, rounds=2, picks_per_round=3)
        picks = generate_picks(config)
        assert any(p["pick_id"] == "2026_1_01" for p in picks)
        assert all(len(p["pick_id"].split("_")[2]) == 2 for p in picks)

    def test_year_range_matches_target_plus_future(self):
        config = _minimal_config(target_season=2026, future_years=2)
        picks = generate_picks(config)
        years = sorted({p["year"] for p in picks})
        assert years == [2026, 2027, 2028]

    def test_round1_salaries_from_rookie_scale(self):
        config = _minimal_config(rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        r1 = [p for p in picks if p["round"] == 1 and p["year"] == 2026]
        salaries = {p["slot"]: p["salary"] for p in r1}
        assert salaries[1] == 14
        assert salaries[2] == 12
        assert salaries[3] == 10
        assert salaries[4] == 8

    def test_round2_3_4_flat_salaries(self):
        config = _minimal_config(rounds=4, picks_per_round=4)
        picks = generate_picks(config)
        year = 2026
        assert all(p["salary"] == 4 for p in picks if p["year"] == year and p["round"] == 2)
        assert all(p["salary"] == 2 for p in picks if p["year"] == year and p["round"] == 3)
        assert all(p["salary"] == 1 for p in picks if p["year"] == year and p["round"] == 4)

    def test_uses_full_league_config(self):
        config = load_league_config()
        picks = generate_picks(config)
        dp = config["draft_picks"]
        comp_count = len(dp.get("compensatory_picks", []))
        years = dp["future_years_tracked"] + 1
        expected = years * (dp["rounds"] * dp["picks_per_round"] + comp_count)
        assert len(picks) == expected

    # --- order_known ---

    def test_order_unknown_by_default(self):
        config = _minimal_config(future_years=1)
        picks = generate_picks(config)
        assert all(not p["order_known"] for p in picks)

    def test_order_known_for_listed_year(self):
        config = _minimal_config(
            target_season=2026,
            future_years=1,
            years_with_known_order=[2026],
        )
        picks = generate_picks(config)
        picks_2026 = [p for p in picks if p["year"] == 2026]
        picks_2027 = [p for p in picks if p["year"] == 2027]
        assert all(p["order_known"] for p in picks_2026)
        assert all(not p["order_known"] for p in picks_2027)

    def test_all_picks_have_order_known_field(self):
        config = _minimal_config()
        picks = generate_picks(config)
        assert all("order_known" in p for p in picks)

    # --- compensatory picks ---

    def test_comp_picks_appear_in_output(self):
        config = _minimal_config(
            rounds=4,
            picks_per_round=4,
            compensatory_picks=[{"round": 2, "slot": 5}],
        )
        picks = generate_picks(config)
        comp = [p for p in picks if p["is_compensatory"]]
        assert len(comp) == 3  # one per tracked year (3 years)
        assert all(p["round"] == 2 and p["slot"] == 5 for p in comp)

    def test_comp_picks_have_is_compensatory_true(self):
        config = _minimal_config(
            compensatory_picks=[{"round": 3, "slot": 5}],
        )
        picks = generate_picks(config)
        comp_ids = {p["pick_id"] for p in picks if p["is_compensatory"]}
        assert "2026_3_05" in comp_ids

    def test_regular_picks_have_is_compensatory_false(self):
        config = _minimal_config(
            compensatory_picks=[{"round": 2, "slot": 5}],
        )
        picks = generate_picks(config)
        regular = [p for p in picks if not p["is_compensatory"]]
        assert all(p["slot"] <= 4 for p in regular)

    def test_standard_comp_picks_2_11_3_11_4_11_4_12(self):
        """The four configured league comp picks must be representable."""
        config = _minimal_config(
            rounds=4,
            picks_per_round=10,
            future_years=0,
            compensatory_picks=[
                {"round": 2, "slot": 11},
                {"round": 3, "slot": 11},
                {"round": 4, "slot": 11},
                {"round": 4, "slot": 12},
            ],
        )
        picks = generate_picks(config)
        comp = [p for p in picks if p["is_compensatory"]]
        slots_by_round = {(p["round"], p["slot"]) for p in comp}
        assert (2, 11) in slots_by_round
        assert (3, 11) in slots_by_round
        assert (4, 11) in slots_by_round
        assert (4, 12) in slots_by_round

    def test_no_comp_picks_by_default(self):
        config = _minimal_config()  # no compensatory_picks key
        picks = generate_picks(config)
        assert not any(p["is_compensatory"] for p in picks)


# ---------------------------------------------------------------------------
# make_pick_record
# ---------------------------------------------------------------------------

class TestMakePickRecord:

    def test_owner_defaults_to_original_team(self):
        rec = make_pick_record("Team Alpha")
        assert rec["original_team"] == "Team Alpha"
        assert rec["owner"] == "Team Alpha"

    def test_explicit_owner_differs_from_original(self):
        rec = make_pick_record("Team Alpha", owner="Team Beta")
        assert rec["original_team"] == "Team Alpha"
        assert rec["owner"] == "Team Beta"

    def test_null_original_team(self):
        rec = make_pick_record(None)
        assert rec["original_team"] is None
        assert rec["owner"] is None

    def test_null_original_explicit_owner(self):
        rec = make_pick_record(None, owner="Team X")
        assert rec["original_team"] is None
        assert rec["owner"] == "Team X"


# ---------------------------------------------------------------------------
# set_owner
# ---------------------------------------------------------------------------

class TestSetOwner:

    def test_updates_owner_preserves_original_team(self):
        ownership = {"2026_1_01": {"original_team": "Team A", "owner": "Team A"}}
        set_owner(ownership, "2026_1_01", "Team B")
        assert ownership["2026_1_01"]["owner"] == "Team B"
        assert ownership["2026_1_01"]["original_team"] == "Team A"

    def test_set_owner_on_new_pick_creates_record(self):
        ownership: dict = {}
        set_owner(ownership, "2027_1_01", "Team C")
        assert ownership["2027_1_01"]["owner"] == "Team C"
        assert ownership["2027_1_01"]["original_team"] is None

    def test_set_owner_to_none(self):
        ownership = {"2026_1_01": {"original_team": "Team A", "owner": "Team A"}}
        set_owner(ownership, "2026_1_01", None)
        assert ownership["2026_1_01"]["owner"] is None
        assert ownership["2026_1_01"]["original_team"] == "Team A"


# ---------------------------------------------------------------------------
# load_ownership / save_ownership
# ---------------------------------------------------------------------------

class TestOwnershipPersistence:

    def test_load_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            result = load_ownership(path)
            assert result == {}

    def test_save_and_reload_ownership(self):
        ownership = {
            "2026_1_01": {"original_team": "Team Alpha", "owner": "Team Alpha"},
            "2026_1_02": {"original_team": None, "owner": None},
            "2026_2_03": {"original_team": "Team Beta", "owner": "Team Gamma"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "picks.json"
            save_ownership(ownership, path)
            reloaded = load_ownership(path)
        assert reloaded == ownership

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "picks.json"
            save_ownership({"2026_1_01": {"original_team": "X", "owner": "X"}}, path)
            assert path.exists()

    def test_save_produces_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "picks.json"
            ownership = {"2026_1_01": {"original_team": "Team A", "owner": "Team A"}}
            save_ownership(ownership, path)
            parsed = json.loads(path.read_text())
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
            assert load_ownership(path) == {}

    def test_legacy_string_format_migrated_on_load(self):
        """Old-format files (pick_id → string) are auto-migrated."""
        legacy = {"2026_1_01": "Team A", "2026_1_02": None}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(legacy))
            result = load_ownership(path)
        assert result["2026_1_01"] == {"original_team": "Team A", "owner": "Team A"}
        assert result["2026_1_02"] == {"original_team": None, "owner": None}


# ---------------------------------------------------------------------------
# get_team_picks
# ---------------------------------------------------------------------------

class TestGetTeamPicks:

    def _make_ownership(self) -> dict:
        return {
            "2026_1_01": {"original_team": "Team Alpha", "owner": "Team Alpha"},
            "2026_1_02": {"original_team": "Team Beta", "owner": "Team Beta"},
            "2026_1_03": {"original_team": "Team Alpha", "owner": "Team Alpha"},
            "2026_2_01": {"original_team": None, "owner": None},
            "2027_1_01": {"original_team": "Team Alpha", "owner": "Team Alpha"},
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
            "2027_1_01": {"original_team": "A", "owner": "A"},
            "2026_1_01": {"original_team": "A", "owner": "A"},
            "2026_2_01": {"original_team": "A", "owner": "A"},
        }
        result = get_team_picks(ownership, "A")
        assert result == sorted(result)

    def test_universe_filter_excludes_picks_not_in_list(self):
        ownership = {
            "2026_1_01": {"original_team": "A", "owner": "A"},
            "2026_1_02": {"original_team": "A", "owner": "A"},
            "9999_1_01": {"original_team": "A", "owner": "A"},
        }
        picks = [{"pick_id": "2026_1_01"}, {"pick_id": "2026_1_02"}]
        result = get_team_picks(ownership, "A", picks=picks)
        assert "9999_1_01" not in result
        assert "2026_1_01" in result

    def test_none_owners_excluded(self):
        ownership = {
            "2026_1_01": {"original_team": None, "owner": None},
            "2026_1_02": {"original_team": "Team A", "owner": "Team A"},
        }
        assert get_team_picks(ownership, "Team A") == ["2026_1_02"]

    def test_traded_pick_found_under_new_owner(self):
        """A pick traded from Team A to Team B is found under Team B."""
        ownership = {
            "2026_1_01": {"original_team": "Team A", "owner": "Team B"},
        }
        assert get_team_picks(ownership, "Team B") == ["2026_1_01"]
        assert get_team_picks(ownership, "Team A") == []


# ---------------------------------------------------------------------------
# build_inventory_table
# ---------------------------------------------------------------------------

class TestBuildInventoryTable:

    def test_merges_original_team_and_owner(self):
        picks = [
            {"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1,
             "salary": 14, "order_known": True, "is_compensatory": False},
        ]
        ownership = {"2026_1_01": {"original_team": "Team A", "owner": "Team B"}}
        table = build_inventory_table(picks, ownership)
        assert table[0]["original_team"] == "Team A"
        assert table[0]["owner"] == "Team B"

    def test_unowned_pick_has_none_fields(self):
        picks = [{"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1,
                  "salary": 14, "order_known": False, "is_compensatory": False}]
        table = build_inventory_table(picks, {})
        assert table[0]["original_team"] is None
        assert table[0]["owner"] is None

    def test_preserves_pick_order(self):
        config = _minimal_config(rounds=2, picks_per_round=3, future_years=0)
        picks = generate_picks(config)
        table = build_inventory_table(picks, {})
        assert [r["pick_id"] for r in table] == [p["pick_id"] for p in picks]

    def test_preserves_all_pick_fields(self):
        picks = [{"pick_id": "2026_1_01", "year": 2026, "round": 1, "slot": 1,
                  "salary": 14, "order_known": True, "is_compensatory": False}]
        ownership = {"2026_1_01": {"original_team": "Team X", "owner": "Team X"}}
        row = build_inventory_table(picks, ownership)[0]
        assert row["year"] == 2026
        assert row["round"] == 1
        assert row["slot"] == 1
        assert row["salary"] == 14
        assert row["order_known"] is True
        assert row["is_compensatory"] is False
        assert row["original_team"] == "Team X"
        assert row["owner"] == "Team X"

    def test_comp_pick_default_owner_is_empty(self):
        """Comp picks start with no owner by default."""
        config = _minimal_config(
            rounds=2,
            picks_per_round=4,
            future_years=0,
            compensatory_picks=[{"round": 2, "slot": 5}],
        )
        picks = generate_picks(config)
        comp_picks = [p for p in picks if p["is_compensatory"]]
        table = build_inventory_table(comp_picks, {})
        assert all(r["original_team"] is None and r["owner"] is None for r in table)


# ---------------------------------------------------------------------------
# all_teams_from_ownership
# ---------------------------------------------------------------------------

class TestAllTeamsFromOwnership:

    def test_returns_sorted_unique_teams(self):
        ownership = {
            "2026_1_01": {"original_team": "Zebra FC", "owner": "Zebra FC"},
            "2026_1_02": {"original_team": "Alpha United", "owner": "Alpha United"},
            "2026_1_03": {"original_team": "Alpha United", "owner": "Alpha United"},
            "2026_1_04": {"original_team": None, "owner": None},
        }
        result = all_teams_from_ownership(ownership)
        assert result == ["Alpha United", "Zebra FC"]

    def test_uses_owner_field_not_original_team(self):
        """After a trade, the traded-away team should not appear as an owner."""
        ownership = {
            "2026_1_01": {"original_team": "Team A", "owner": "Team B"},
        }
        result = all_teams_from_ownership(ownership)
        assert result == ["Team B"]
        assert "Team A" not in result

    def test_empty_ownership_returns_empty_list(self):
        assert all_teams_from_ownership({}) == []

    def test_all_unowned_returns_empty_list(self):
        assert all_teams_from_ownership({"2026_1_01": {"original_team": None, "owner": None}}) == []


# ---------------------------------------------------------------------------
# Future-year unknown-order behavior
# ---------------------------------------------------------------------------

class TestUnknownOrderBehavior:

    def test_future_years_are_order_unknown(self):
        config = _minimal_config(
            target_season=2026,
            future_years=2,
            years_with_known_order=[2026],
        )
        picks = generate_picks(config)
        for p in picks:
            if p["year"] == 2026:
                assert p["order_known"] is True
            else:
                assert p["order_known"] is False

    def test_unknown_order_picks_still_have_slot_field(self):
        """Slot exists as a placeholder but is not a real draft position."""
        config = _minimal_config(future_years=1, years_with_known_order=[])
        picks = generate_picks(config)
        assert all("slot" in p for p in picks)

    def test_original_team_and_owner_can_be_set_independently_of_order(self):
        """We can record team assignments for future-year picks before order is known."""
        ownership: dict = {}
        set_owner(ownership, "2028_1_01", "Team Future")
        ownership["2028_1_01"]["original_team"] = "Team Future"

        config = _minimal_config(target_season=2026, future_years=2, years_with_known_order=[])
        picks = generate_picks(config)
        table = build_inventory_table(picks, ownership)
        row = next(r for r in table if r["pick_id"] == "2028_1_01")
        assert not row["order_known"]
        assert row["owner"] == "Team Future"
        assert row["original_team"] == "Team Future"
