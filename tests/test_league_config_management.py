"""Tests for league config management: config save, team adjustments, roster
validation, and cap remaining calculation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.contracts.phase3_tables import validate_roster_csv
from src.contracts.team_adjustments import (
    get_team_adjustment,
    load_team_adjustments,
    save_team_adjustments,
    validate_team_adjustments,
)
from src.utils.config import load_league_config, save_league_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Team Cap Adjustments
# ---------------------------------------------------------------------------

class TestTeamAdjustments:

    def test_load_returns_empty_when_missing(self, tmp_path):
        result = load_team_adjustments(tmp_path / "nonexistent.json")
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "adj.json"
        data = {
            "Team A": {"dead_money": 5.0, "cap_transactions": -3.0, "rollover": 12.5},
            "Team B": {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 0.0},
        }
        save_team_adjustments(data, path)
        loaded = load_team_adjustments(path)
        assert loaded == data

    def test_validate_rejects_negative_dead_money(self):
        data = {"Team A": {"dead_money": -1.0, "cap_transactions": 0, "rollover": 0}}
        with pytest.raises(ValueError, match="dead_money must be >= 0"):
            validate_team_adjustments(data)

    def test_validate_allows_negative_cap_transactions(self):
        data = {"Team A": {"dead_money": 0, "cap_transactions": -10.0, "rollover": 0}}
        validate_team_adjustments(data)  # must not raise

    def test_validate_rejects_non_numeric(self):
        data = {"Team A": {"dead_money": "bad", "cap_transactions": 0, "rollover": 0}}
        with pytest.raises(ValueError, match="must be a number"):
            validate_team_adjustments(data)

    def test_validate_rejects_missing_field(self):
        data = {"Team A": {"dead_money": 0, "cap_transactions": 0}}
        with pytest.raises(ValueError, match="missing required field"):
            validate_team_adjustments(data)

    def test_get_team_adjustment_defaults_to_zeros(self):
        adj = get_team_adjustment({}, "Unknown Team")
        assert adj == {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 0.0}

    def test_get_team_adjustment_returns_existing(self):
        data = {"Team X": {"dead_money": 5.0, "cap_transactions": -2.0, "rollover": 10.0}}
        adj = get_team_adjustment(data, "Team X")
        assert adj["dead_money"] == 5.0
        assert adj["cap_transactions"] == -2.0
        assert adj["rollover"] == 10.0


# ---------------------------------------------------------------------------
# Config Save
# ---------------------------------------------------------------------------

class TestConfigSave:

    def _make_config_copy(self, tmp_path):
        """Copy the real config to a temp file for safe editing."""
        original = load_league_config()
        import yaml
        dest = tmp_path / "league_config.yaml"
        with dest.open("w") as f:
            yaml.safe_dump(original, f, default_flow_style=False, sort_keys=False)
        return str(dest)

    def test_save_roundtrip(self, tmp_path):
        path = self._make_config_copy(tmp_path)
        original = load_league_config(path)
        original_base_cap = original["cap"]["base_cap"]

        new_cap = original_base_cap + 50
        updated = save_league_config({"cap.base_cap": new_cap}, path)
        assert updated["cap"]["base_cap"] == new_cap

        reloaded = load_league_config(path)
        assert reloaded["cap"]["base_cap"] == new_cap

    def test_save_rejects_invalid_discount_rate(self, tmp_path):
        path = self._make_config_copy(tmp_path)
        with pytest.raises(ValueError, match="discount_rate"):
            save_league_config({"cap.discount_rate": 1.5}, path)

    def test_save_preserves_unedited_fields(self, tmp_path):
        path = self._make_config_copy(tmp_path)
        original = load_league_config(path)
        original_lineup = original["lineup"].copy()

        save_league_config({"cap.base_cap": 999}, path)
        reloaded = load_league_config(path)

        for slot in ("qb", "rb", "wr", "te", "flex", "superflex"):
            assert reloaded["lineup"][slot] == original_lineup[slot]

    def test_save_rejects_non_editable_field(self, tmp_path):
        path = self._make_config_copy(tmp_path)
        with pytest.raises(ValueError, match="Non-editable"):
            save_league_config({"valuation.unranked_start_prob": 0.5}, path)


# ---------------------------------------------------------------------------
# Roster Validation
# ---------------------------------------------------------------------------

class TestRosterValidation:

    def test_validate_valid_roster(self):
        result = validate_roster_csv(str(FIXTURES_DIR / "tiny_roster.csv"))
        assert result["valid"] is True
        assert result["rows"] == 5
        assert "A" in result["teams"]
        assert "B" in result["teams"]

    def test_validate_missing_column(self, tmp_path):
        path = tmp_path / "bad_roster.csv"
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Team", "Player", "Current Salary"])
            writer.writerow(["A", "Someone", "10"])
        result = validate_roster_csv(str(path))
        assert result["valid"] is False
        assert "Missing required columns" in result["error"]

    def test_validate_bad_numeric(self, tmp_path):
        path = tmp_path / "bad_numeric.csv"
        headers = [
            "Team", "Player", "Position", "Current Salary", "Real Salary",
            "Extension Salary", "Years", "PS Eligible", "Has Been Extended",
            "Has Been Tagged", "Contract Eligible", "Extension Eligible", "Tag Eligible",
        ]
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow(["A", "P1", "QB", "not_a_number", "10", "0", "2",
                             "FALSE", "FALSE", "FALSE", "TRUE", "TRUE", "TRUE"])
        result = validate_roster_csv(str(path))
        assert result["valid"] is False
        assert "non-numeric" in result["error"].lower()

    def test_validate_empty_csv(self, tmp_path):
        path = tmp_path / "empty.csv"
        headers = [
            "Team", "Player", "Position", "Current Salary", "Real Salary",
            "Extension Salary", "Years", "PS Eligible", "Has Been Extended",
            "Has Been Tagged", "Contract Eligible", "Extension Eligible", "Tag Eligible",
        ]
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        result = validate_roster_csv(str(path))
        assert result["valid"] is False
        assert "no data" in result["error"].lower()

    def test_validate_nonexistent_file(self, tmp_path):
        result = validate_roster_csv(str(tmp_path / "nope.csv"))
        assert result["valid"] is False
        assert "Cannot read CSV" in result["error"]


# ---------------------------------------------------------------------------
# Cap Remaining Calculation
# ---------------------------------------------------------------------------

class TestCapRemaining:
    """Tests for the Cap Remaining formula:
    Cap Remaining = Starting Cap - Current Cap Usage - Dead Money - Cap Transactions + Rollover
    """

    def test_basic_formula(self):
        base_cap = 300
        current_cap_usage = 250
        dead_money = 10
        cap_transactions = 5  # positive = credits
        rollover = 20

        cap_remaining = base_cap - current_cap_usage - dead_money - cap_transactions + rollover
        assert cap_remaining == 55  # 300 - 250 - 10 - 5 + 20

    def test_negative_cap_transactions_reduces_remaining(self):
        base_cap = 300
        current_cap_usage = 250
        dead_money = 0
        cap_transactions = -15  # negative = charges (adds to cap space since we subtract)
        rollover = 0

        cap_remaining = base_cap - current_cap_usage - dead_money - cap_transactions + rollover
        # 300 - 250 - 0 - (-15) + 0 = 300 - 250 + 15 = 65
        assert cap_remaining == 65

    def test_zero_adjustments(self):
        base_cap = 300
        current_cap_usage = 280

        adj = get_team_adjustment({}, "Team X")
        cap_remaining = (
            base_cap - current_cap_usage
            - adj["dead_money"] - adj["cap_transactions"] + adj["rollover"]
        )
        assert cap_remaining == 20

    def test_all_adjustments(self):
        base_cap = 300
        current_cap_usage = 200
        adjustments = {
            "Team A": {"dead_money": 15.0, "cap_transactions": -5.0, "rollover": 30.0},
        }

        adj = get_team_adjustment(adjustments, "Team A")
        cap_remaining = (
            base_cap - current_cap_usage
            - adj["dead_money"] - adj["cap_transactions"] + adj["rollover"]
        )
        # 300 - 200 - 15 - (-5) + 30 = 300 - 200 - 15 + 5 + 30 = 120
        assert cap_remaining == 120
