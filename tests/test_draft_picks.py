"""Tests for src/contracts/draft_picks.py — team-based pick model.

Coverage:
- normalize_team_key: slug generation
- make_team_pick_id / make_comp_pick_id: ID construction
- generate_picks: comp picks from config; team picks from ownership; salaries
- load_ownership: new-format round-trip; legacy string migration;
  legacy slot-based ID migration (with and without original_team)
- save_ownership: persistence and JSON validity
- make_pick_record: default owner equals original_team
- set_owner: trade ownership without changing original_team
- set_draft_order: assigns slots across all rounds for a year
- register_teams: idempotent initialization
- get_team_picks: filter by current owner
- build_inventory_table: merges original_team + owner; defaults owner to original_team
- all_teams_from_ownership: unique current owners
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
    make_comp_pick_id,
    make_pick_record,
    make_team_pick_id,
    normalize_team_key,
    register_teams,
    save_ownership,
    set_draft_order,
    set_owner,
)
from src.utils.config import load_league_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_config(
    target_season: int = 2026,
    future_years: int = 2,
    rounds: int = 4,
    picks_per_round: int = 4,
    years_with_known_order: list[int] | None = None,
    compensatory_picks: list[dict] | None = None,
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
            "years_with_known_order": years_with_known_order or [],
            "compensatory_picks": compensatory_picks or [],
        },
        "rookie_scale": {
            "round1": {"1.01": 14, "1.02": 12, "1.03": 10, "1.04": 8},
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


def _two_team_ownership(year: int = 2026) -> dict:
    """Minimal ownership with two teams across 4 rounds for a single year."""
    teams = ["Team Alpha", "Team Beta"]
    ow = {}
    for rnd in range(1, 5):
        for team in teams:
            pid = make_team_pick_id(year, rnd, team)
            ow[pid] = make_pick_record(team)
    return ow


# ---------------------------------------------------------------------------
# normalize_team_key
# ---------------------------------------------------------------------------

class TestNormalizeTeamKey:

    def test_lowercases_and_slugifies(self):
        assert normalize_team_key("Big Boom Machine") == "big_boom_machine"

    def test_special_chars_become_underscores(self):
        assert normalize_team_key("Turner | Banana Breath") == "turner_banana_breath"

    def test_leading_trailing_underscores_stripped(self):
        k = normalize_team_key("---Team---")
        assert not k.startswith("_")
        assert not k.endswith("_")

    def test_pipes_and_numbers(self):
        assert normalize_team_key("BG | 2 Rice 2 Addison") == "bg_2_rice_2_addison"


# ---------------------------------------------------------------------------
# make_team_pick_id / make_comp_pick_id
# ---------------------------------------------------------------------------

class TestPickIdConstruction:

    def test_team_pick_id_format(self):
        pid = make_team_pick_id(2026, 1, "Big Boom Machine")
        assert pid == "2026_1_t_big_boom_machine"

    def test_comp_pick_id_format(self):
        pid = make_comp_pick_id(2026, 2, 1)
        assert pid == "2026_2_comp_01"

    def test_comp_pick_id_two_digit_index(self):
        pid = make_comp_pick_id(2027, 4, 12)
        assert pid == "2027_4_comp_12"


# ---------------------------------------------------------------------------
# generate_picks
# ---------------------------------------------------------------------------

class TestGeneratePicks:

    def test_no_ownership_returns_only_comp_picks(self):
        config = _minimal_config(
            future_years=0,
            compensatory_picks=[{"round": 2, "slot": 5}],
        )
        picks = generate_picks(config)
        assert all(p["is_compensatory"] for p in picks)
        assert len(picks) == 1  # 1 year × 1 comp pick

    def test_team_picks_derived_from_ownership(self):
        config = _minimal_config(future_years=0, rounds=2)
        ownership = {}
        for rnd in (1, 2):
            for team in ("Team A", "Team B"):
                pid = make_team_pick_id(2026, rnd, team)
                ownership[pid] = make_pick_record(team)
        picks = generate_picks(config, ownership)
        team_picks = [p for p in picks if not p["is_compensatory"]]
        assert len(team_picks) == 4  # 2 rounds × 2 teams

    def test_comp_picks_always_generated_regardless_of_ownership(self):
        config = _minimal_config(
            future_years=0,
            compensatory_picks=[{"round": 3, "slot": 5}],
        )
        picks = generate_picks(config, {})
        comp = [p for p in picks if p["is_compensatory"]]
        assert len(comp) == 1
        assert comp[0]["slot"] == 5

    def test_team_picks_carry_original_team(self):
        config = _minimal_config(future_years=0, rounds=1)
        ownership = {make_team_pick_id(2026, 1, "Team Alpha"): make_pick_record("Team Alpha")}
        picks = generate_picks(config, ownership)
        team_picks = [p for p in picks if not p["is_compensatory"]]
        assert team_picks[0]["original_team"] == "Team Alpha"

    def test_slot_is_none_for_unknown_order(self):
        config = _minimal_config(future_years=0, rounds=1, years_with_known_order=[])
        ownership = {make_team_pick_id(2026, 1, "T"): make_pick_record("T")}
        picks = generate_picks(config, ownership)
        assert picks[0]["slot"] is None
        assert picks[0]["order_known"] is False

    def test_slot_read_from_ownership_when_set(self):
        config = _minimal_config(future_years=0, rounds=1, years_with_known_order=[2026])
        pid = make_team_pick_id(2026, 1, "T")
        ownership = {pid: {**make_pick_record("T"), "slot": 3}}
        picks = generate_picks(config, ownership)
        team_pick = next(p for p in picks if not p["is_compensatory"])
        assert team_pick["slot"] == 3
        assert team_pick["order_known"] is True

    def test_salary_none_when_slot_unknown(self):
        config = _minimal_config(future_years=0, rounds=1)
        ownership = {make_team_pick_id(2026, 1, "T"): make_pick_record("T")}
        picks = generate_picks(config, ownership)
        assert picks[0]["salary"] is None

    def test_round1_salary_from_slot(self):
        config = _minimal_config(future_years=0, rounds=1, years_with_known_order=[2026])
        pid = make_team_pick_id(2026, 1, "T")
        ownership = {pid: {**make_pick_record("T"), "slot": 2}}
        picks = generate_picks(config, ownership)
        # slot 2 → "1.02" → 12
        assert picks[0]["salary"] == 12

    def test_flat_salary_for_rounds_2_through_4(self):
        config = _minimal_config(future_years=0, rounds=4, years_with_known_order=[2026])
        pid2 = make_team_pick_id(2026, 2, "T")
        pid3 = make_team_pick_id(2026, 3, "T")
        pid4 = make_team_pick_id(2026, 4, "T")
        ownership = {
            pid2: {**make_pick_record("T"), "slot": 1},
            pid3: {**make_pick_record("T"), "slot": 1},
            pid4: {**make_pick_record("T"), "slot": 1},
        }
        picks = generate_picks(config, ownership)
        by_rnd = {p["round"]: p["salary"] for p in picks if not p["is_compensatory"]}
        assert by_rnd[2] == 4
        assert by_rnd[3] == 2
        assert by_rnd[4] == 1

    def test_years_tracked(self):
        config = _minimal_config(target_season=2026, future_years=2, rounds=1)
        ownership = {make_team_pick_id(yr, 1, "T"): make_pick_record("T") for yr in (2026, 2027, 2028)}
        picks = generate_picks(config, ownership)
        years = sorted({p["year"] for p in picks})
        assert years == [2026, 2027, 2028]

    def test_standard_comp_picks_represented(self):
        config = _minimal_config(
            rounds=4,
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
        slots_by_rnd = [(p["round"], p["slot"]) for p in comp]
        assert (2, 11) in slots_by_rnd
        assert (3, 11) in slots_by_rnd
        assert (4, 11) in slots_by_rnd
        assert (4, 12) in slots_by_rnd

    def test_uses_full_league_config(self):
        config = load_league_config()
        picks = generate_picks(config)
        # No ownership → only comp picks (4 comp picks × 3 years = 12)
        dp = config["draft_picks"]
        comp_count = len(dp.get("compensatory_picks", []))
        expected = (dp["future_years_tracked"] + 1) * comp_count
        assert len(picks) == expected


# ---------------------------------------------------------------------------
# load_ownership / save_ownership
# ---------------------------------------------------------------------------

class TestOwnershipPersistence:

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            assert load_ownership(Path(d) / "missing.json") == {}

    def test_round_trip(self):
        ow = {
            "2026_1_t_alpha": {"original_team": "Alpha", "owner": "Alpha", "slot": 1},
            "2026_2_comp_01": {"original_team": None, "owner": None, "slot": 11},
        }
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "picks.json"
            save_ownership(ow, p)
            assert load_ownership(p) == ow

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a" / "b" / "picks.json"
            save_ownership({}, p)
            assert p.exists()

    def test_invalid_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("[1,2]")
            with pytest.raises(ValueError, match="JSON object"):
                load_ownership(p)

    def test_legacy_string_migrated(self):
        legacy = {"2026_1_t_alpha": "Alpha Team"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.json"
            p.write_text(json.dumps(legacy))
            result = load_ownership(p)
        rec = result["2026_1_t_alpha"]
        assert rec["original_team"] == "Alpha Team"
        assert rec["owner"] == "Alpha Team"

    def test_legacy_slot_id_with_team_migrated(self):
        """Old format: "2026_1_03" → "Team A" becomes "2026_1_t_team_a" with slot=3."""
        legacy = {"2026_1_03": "Team A"}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.json"
            p.write_text(json.dumps(legacy))
            result = load_ownership(p)
        assert "2026_1_t_team_a" in result
        assert result["2026_1_t_team_a"]["slot"] == 3
        assert result["2026_1_t_team_a"]["original_team"] == "Team A"

    def test_legacy_slot_id_without_team_dropped(self):
        """Old placeholder nulls like "2027_1_01": null are silently dropped."""
        legacy = {"2027_1_01": None, "2027_1_02": None}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.json"
            p.write_text(json.dumps(legacy))
            result = load_ownership(p)
        assert result == {}

    def test_legacy_slot_id_dict_format_migrated(self):
        """Old new-format dict with slot-based ID gets re-keyed."""
        legacy = {"2026_2_05": {"original_team": "Box Team", "owner": "Box Team"}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.json"
            p.write_text(json.dumps(legacy))
            result = load_ownership(p)
        assert "2026_2_t_box_team" in result
        assert result["2026_2_t_box_team"]["slot"] == 5


# ---------------------------------------------------------------------------
# make_pick_record
# ---------------------------------------------------------------------------

class TestMakePickRecord:

    def test_owner_defaults_to_original_team(self):
        rec = make_pick_record("Team Alpha")
        assert rec["owner"] == "Team Alpha"
        assert rec["original_team"] == "Team Alpha"

    def test_explicit_owner(self):
        rec = make_pick_record("Team A", owner="Team B")
        assert rec["original_team"] == "Team A"
        assert rec["owner"] == "Team B"

    def test_slot_defaults_none(self):
        assert make_pick_record("T")["slot"] is None

    def test_explicit_slot(self):
        assert make_pick_record("T", slot=3)["slot"] == 3

    def test_null_original_team(self):
        rec = make_pick_record(None)
        assert rec["original_team"] is None
        assert rec["owner"] is None


# ---------------------------------------------------------------------------
# set_owner
# ---------------------------------------------------------------------------

class TestSetOwner:

    def test_updates_owner_preserves_original_team(self):
        ow = {"2026_1_t_a": {"original_team": "A", "owner": "A", "slot": 1}}
        set_owner(ow, "2026_1_t_a", "B")
        assert ow["2026_1_t_a"]["owner"] == "B"
        assert ow["2026_1_t_a"]["original_team"] == "A"
        assert ow["2026_1_t_a"]["slot"] == 1

    def test_new_pick_created_with_null_original(self):
        ow: dict = {}
        set_owner(ow, "2027_1_t_x", "Team X")
        assert ow["2027_1_t_x"]["owner"] == "Team X"
        assert ow["2027_1_t_x"]["original_team"] is None

    def test_set_to_none(self):
        ow = {"p": {"original_team": "A", "owner": "A", "slot": None}}
        set_owner(ow, "p", None)
        assert ow["p"]["owner"] is None
        assert ow["p"]["original_team"] == "A"


# ---------------------------------------------------------------------------
# set_draft_order
# ---------------------------------------------------------------------------

class TestSetDraftOrder:

    def test_assigns_slots_to_all_teams_in_round(self):
        ow = _two_team_ownership(2026)
        set_draft_order(ow, 2026, 1, ["Team Beta", "Team Alpha"])
        assert ow[make_team_pick_id(2026, 1, "Team Beta")]["slot"] == 1
        assert ow[make_team_pick_id(2026, 1, "Team Alpha")]["slot"] == 2

    def test_does_not_affect_other_rounds(self):
        ow = _two_team_ownership(2026)
        set_draft_order(ow, 2026, 1, ["Team Alpha", "Team Beta"])
        pid_r2 = make_team_pick_id(2026, 2, "Team Alpha")
        assert ow[pid_r2]["slot"] is None

    def test_creates_record_if_not_present(self):
        ow: dict = {}
        set_draft_order(ow, 2027, 1, ["New Team"])
        pid = make_team_pick_id(2027, 1, "New Team")
        assert pid in ow
        assert ow[pid]["slot"] == 1


# ---------------------------------------------------------------------------
# register_teams
# ---------------------------------------------------------------------------

class TestRegisterTeams:

    def test_creates_records_for_all_combinations(self):
        ow: dict = {}
        register_teams(ow, ["A", "B"], years=[2026, 2027], rounds=2)
        assert len(ow) == 8  # 2 teams × 2 years × 2 rounds

    def test_does_not_overwrite_existing(self):
        pid = make_team_pick_id(2026, 1, "A")
        ow = {pid: {"original_team": "A", "owner": "B", "slot": 3}}
        register_teams(ow, ["A"], years=[2026], rounds=1)
        assert ow[pid]["owner"] == "B"  # unchanged
        assert ow[pid]["slot"] == 3     # unchanged

    def test_idempotent(self):
        ow: dict = {}
        register_teams(ow, ["A"], years=[2026], rounds=1)
        register_teams(ow, ["A"], years=[2026], rounds=1)
        assert len(ow) == 1


# ---------------------------------------------------------------------------
# get_team_picks
# ---------------------------------------------------------------------------

class TestGetTeamPicks:

    def test_returns_picks_by_current_owner(self):
        ow = {
            make_team_pick_id(2026, 1, "A"): make_pick_record("A"),
            make_team_pick_id(2026, 1, "B"): {"original_team": "B", "owner": "A", "slot": None},
            make_team_pick_id(2027, 1, "A"): make_pick_record("A"),
        }
        result = get_team_picks(ow, "A")
        assert make_team_pick_id(2026, 1, "A") in result
        assert make_team_pick_id(2026, 1, "B") in result  # traded to A
        assert make_team_pick_id(2027, 1, "A") in result
        assert len(result) == 3

    def test_traded_pick_found_under_new_owner(self):
        pid = make_team_pick_id(2026, 1, "Original")
        ow = {pid: {"original_team": "Original", "owner": "New Owner", "slot": None}}
        assert get_team_picks(ow, "New Owner") == [pid]
        assert get_team_picks(ow, "Original") == []

    def test_universe_filter(self):
        pid_valid = make_team_pick_id(2026, 1, "A")
        pid_extra = make_team_pick_id(9999, 1, "A")
        ow = {pid_valid: make_pick_record("A"), pid_extra: make_pick_record("A")}
        result = get_team_picks(ow, "A", picks=[{"pick_id": pid_valid}])
        assert pid_extra not in result

    def test_result_sorted(self):
        ow = {
            make_team_pick_id(2027, 1, "A"): make_pick_record("A"),
            make_team_pick_id(2026, 1, "A"): make_pick_record("A"),
        }
        result = get_team_picks(ow, "A")
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# build_inventory_table
# ---------------------------------------------------------------------------

class TestBuildInventoryTable:

    def test_owner_from_ownership_record(self):
        pid = make_team_pick_id(2026, 1, "A")
        picks = [{"pick_id": pid, "original_team": "A", "year": 2026, "round": 1,
                  "slot": None, "salary": None, "order_known": False, "is_compensatory": False}]
        ow = {pid: {"original_team": "A", "owner": "B", "slot": None}}
        row = build_inventory_table(picks, ow)[0]
        assert row["owner"] == "B"

    def test_owner_defaults_to_original_team_when_not_in_ownership(self):
        pid = make_team_pick_id(2027, 1, "Team X")
        picks = [{"pick_id": pid, "original_team": "Team X", "year": 2027, "round": 1,
                  "slot": None, "salary": None, "order_known": False, "is_compensatory": False}]
        row = build_inventory_table(picks, {})[0]
        assert row["owner"] == "Team X"

    def test_comp_pick_owner_none_by_default(self):
        pid = make_comp_pick_id(2026, 2, 1)
        picks = [{"pick_id": pid, "original_team": None, "year": 2026, "round": 2,
                  "slot": 11, "salary": 4, "order_known": False, "is_compensatory": True}]
        row = build_inventory_table(picks, {})[0]
        assert row["owner"] is None

    def test_preserves_pick_order(self):
        config = _minimal_config(rounds=2, future_years=0)
        ow = {}
        for rnd in (1, 2):
            for t in ("A", "B"):
                pid = make_team_pick_id(2026, rnd, t)
                ow[pid] = make_pick_record(t)
        picks = generate_picks(config, ow)
        table = build_inventory_table(picks, ow)
        assert [r["pick_id"] for r in table] == [p["pick_id"] for p in picks]


# ---------------------------------------------------------------------------
# all_teams_from_ownership
# ---------------------------------------------------------------------------

class TestAllTeamsFromOwnership:

    def test_returns_sorted_unique_owners(self):
        ow = {
            "a": {"owner": "Zebra", "original_team": "Zebra", "slot": None},
            "b": {"owner": "Alpha", "original_team": "Alpha", "slot": None},
            "c": {"owner": "Alpha", "original_team": "Alpha", "slot": None},
            "d": {"owner": None,    "original_team": None,    "slot": None},
        }
        assert all_teams_from_ownership(ow) == ["Alpha", "Zebra"]

    def test_uses_owner_not_original_team(self):
        ow = {"p": {"original_team": "From", "owner": "To", "slot": None}}
        result = all_teams_from_ownership(ow)
        assert "To" in result
        assert "From" not in result

    def test_empty_returns_empty(self):
        assert all_teams_from_ownership({}) == []
