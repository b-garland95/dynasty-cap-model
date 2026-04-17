"""Tests for contract schedule validation workflow."""

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from src.contracts.contract_validation import (
    get_validated_players,
    get_validation_queue,
    load_validation_status,
    mark_player_validated,
    save_validation_status,
    update_schedule_overrides,
)
from src.contracts.phase3_tables import (
    apply_schedule_overrides,
    build_contract_ledger,
    build_salary_schedule,
    load_schedule_overrides,
)
from src.utils.config import load_league_config

_CONFIG = load_league_config()


def _fixture_path() -> str:
    return str(Path(__file__).parent / "fixtures" / "tiny_roster.csv")


def _build_schedule() -> pd.DataFrame:
    ledger = build_contract_ledger(_fixture_path())
    return build_salary_schedule(ledger, _CONFIG)


# ── Queue loading ─────────────────────────────────────────────────────────────

def test_queue_contains_instrument_adjusted_players():
    schedule = _build_schedule()
    queue = get_validation_queue(schedule, {})

    player_names = [p["player"] for p in queue]
    # Player Four and Player Five are instrument-adjusted (has_been_extended=True)
    assert "Player Four" in player_names
    assert "Player Five" in player_names


def test_queue_excludes_standard_players():
    schedule = _build_schedule()
    queue = get_validation_queue(schedule, {})

    player_names = [p["player"] for p in queue]
    assert "Player One" not in player_names
    assert "Player Two" not in player_names
    assert "Player Three" not in player_names


def test_queue_entries_have_required_fields():
    schedule = _build_schedule()
    queue = get_validation_queue(schedule, {})
    assert len(queue) > 0

    for entry in queue:
        assert "player" in entry
        assert "team" in entry
        assert "position" in entry
        assert "schedule" in entry
        assert isinstance(entry["schedule"], list)
        for row in entry["schedule"]:
            assert "year_index" in row
            assert "cap_hit_real" in row
            assert "schedule_source" in row
            assert "needs_schedule_validation" in row


def test_queue_excludes_already_validated_player():
    schedule = _build_schedule()
    status = {"Player Four|B": {"status": "validated", "validated_at": "2026-01-01T00:00:00+00:00"}}
    queue = get_validation_queue(schedule, status)

    player_names = [p["player"] for p in queue]
    assert "Player Four" not in player_names
    assert "Player Five" in player_names


def test_queue_is_empty_when_all_validated():
    schedule = _build_schedule()
    status = {
        "Player Four|B": {"status": "validated", "validated_at": "2026-01-01T00:00:00+00:00"},
        "Player Five|B": {"status": "validated", "validated_at": "2026-01-01T00:00:00+00:00"},
    }
    queue = get_validation_queue(schedule, status)
    assert queue == []


# ── Schedule cap_hit_current NaN serialization ────────────────────────────────

def test_queue_schedule_cap_hit_current_none_for_future_years():
    schedule = _build_schedule()
    queue = get_validation_queue(schedule, {})

    four = next(e for e in queue if e["player"] == "Player Four")
    year0 = next(r for r in four["schedule"] if r["year_index"] == 0)
    year1 = next(r for r in four["schedule"] if r["year_index"] == 1)

    assert year0["cap_hit_current"] is not None
    assert year1["cap_hit_current"] is None


# ── Override persistence ──────────────────────────────────────────────────────

def test_update_schedule_overrides_creates_file(tmp_path: Path):
    overrides_path = tmp_path / "overrides.csv"
    rows = [
        {"year_index": 0, "cap_hit_real": 10.0, "cap_hit_current": 10.0},
        {"year_index": 1, "cap_hit_real": 25.0},
    ]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", rows)

    assert overrides_path.exists()
    df = pd.read_csv(overrides_path)
    assert len(df) == 2
    p4_rows = df[df["player"] == "Player Four"]
    assert len(p4_rows) == 2
    assert list(p4_rows["cap_hit_real"]) == [10.0, 25.0]
    assert p4_rows["needs_schedule_validation"].tolist() == [False, False]


def test_update_schedule_overrides_replaces_existing_player(tmp_path: Path):
    overrides_path = tmp_path / "overrides.csv"
    # Write initial rows for two players
    initial_rows = [
        {"year_index": 0, "cap_hit_real": 8.0, "cap_hit_current": 8.0},
    ]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", initial_rows)
    update_schedule_overrides(overrides_path, "Player Five", "B", "TE", [
        {"year_index": 0, "cap_hit_real": 3.0, "cap_hit_current": 3.0},
    ])

    # Overwrite Player Four with new values
    new_rows = [
        {"year_index": 0, "cap_hit_real": 99.0, "cap_hit_current": 99.0},
        {"year_index": 1, "cap_hit_real": 110.0},
    ]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", new_rows)

    df = pd.read_csv(overrides_path)
    p4_rows = df[df["player"] == "Player Four"].sort_values("year_index")
    p5_rows = df[df["player"] == "Player Five"]

    assert len(p4_rows) == 2
    assert p4_rows.iloc[0]["cap_hit_real"] == 99.0
    assert p4_rows.iloc[1]["cap_hit_real"] == 110.0
    # Player Five must be untouched
    assert len(p5_rows) == 1
    assert p5_rows.iloc[0]["cap_hit_real"] == 3.0


def test_update_schedule_overrides_sets_needs_validation_false(tmp_path: Path):
    overrides_path = tmp_path / "overrides.csv"
    rows = [{"year_index": 0, "cap_hit_real": 8.0}]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", rows)

    df = pd.read_csv(overrides_path)
    assert df.iloc[0]["needs_schedule_validation"] == False


def test_overrides_applied_clear_validation_flag(tmp_path: Path):
    """After saving overrides, schedule shows needs_schedule_validation=False for that player."""
    overrides_path = tmp_path / "overrides.csv"
    rows = [
        {"year_index": 0, "cap_hit_real": 8.0, "cap_hit_current": 8.0, "schedule_source": "manual_override"},
        {"year_index": 1, "cap_hit_real": 35.0, "schedule_source": "manual_override"},
    ]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", rows)

    ledger = build_contract_ledger(_fixture_path())
    schedule = build_salary_schedule(ledger, _CONFIG)
    overrides_df = load_schedule_overrides(overrides_path)
    final_schedule = apply_schedule_overrides(schedule, overrides_df)

    p4 = final_schedule[final_schedule["player"] == "Player Four"]
    assert not p4["needs_schedule_validation"].any()
    assert (p4["cap_hit_real"] == [8.0, 35.0]).all()


# ── Validation status transitions ─────────────────────────────────────────────

def test_mark_player_validated_sets_status():
    status = {}
    updated = mark_player_validated(status, "Player Four", "B")
    assert updated["Player Four|B"]["status"] == "validated"
    assert "validated_at" in updated["Player Four|B"]


def test_mark_player_validated_preserves_other_entries():
    status = {"Player Five|B": {"status": "validated", "validated_at": "2026-01-01T00:00:00+00:00"}}
    updated = mark_player_validated(status, "Player Four", "B")
    assert "Player Five|B" in updated
    assert updated["Player Four|B"]["status"] == "validated"


def test_mark_player_validated_accepts_custom_timestamp():
    status = {}
    ts = "2026-04-17T12:00:00+00:00"
    updated = mark_player_validated(status, "Player Four", "B", validated_at=ts)
    assert updated["Player Four|B"]["validated_at"] == ts


# ── Validation status persistence ─────────────────────────────────────────────

def test_save_and_load_validation_status(tmp_path: Path):
    path = tmp_path / "validation_status.json"
    data = {"Player Four|B": {"status": "validated", "validated_at": "2026-01-01T00:00:00+00:00"}}

    save_validation_status(data, path)
    assert path.exists()

    loaded = load_validation_status(path)
    assert loaded == data


def test_load_validation_status_missing_file(tmp_path: Path):
    path = tmp_path / "nonexistent.json"
    result = load_validation_status(path)
    assert result == {}


# ── Validated player listing ───────────────────────────────────────────────────

def test_get_validated_players_returns_correct_entries():
    schedule = _build_schedule()
    status = {
        "Player Four|B": {"status": "validated", "validated_at": "2026-04-17T10:00:00+00:00"},
    }
    validated = get_validated_players(schedule, status)

    assert len(validated) == 1
    assert validated[0]["player"] == "Player Four"
    assert validated[0]["team"] == "B"
    assert validated[0]["validated_at"] == "2026-04-17T10:00:00+00:00"
    assert isinstance(validated[0]["schedule"], list)
    assert len(validated[0]["schedule"]) == 2


def test_get_validated_players_empty_when_no_status():
    schedule = _build_schedule()
    validated = get_validated_players(schedule, {})
    assert validated == []


def test_queue_reflects_status_after_full_validation_cycle(tmp_path: Path):
    """End-to-end: validate a player, confirm it leaves the queue and appears in validated list."""
    overrides_path = tmp_path / "overrides.csv"
    status_path = tmp_path / "status.json"

    schedule = _build_schedule()
    status = load_validation_status(status_path)

    # Initially both instrument players are in the queue
    queue_before = get_validation_queue(schedule, status)
    queue_names_before = [p["player"] for p in queue_before]
    assert "Player Four" in queue_names_before

    # Validate Player Four
    rows = [
        {"year_index": 0, "cap_hit_real": 8.0, "cap_hit_current": 8.0, "schedule_source": "confirmed"},
        {"year_index": 1, "cap_hit_real": 32.0, "schedule_source": "confirmed"},
    ]
    update_schedule_overrides(overrides_path, "Player Four", "B", "RB", rows)
    status = mark_player_validated(status, "Player Four", "B")
    save_validation_status(status, status_path)

    # Rebuild schedule with overrides
    ledger = build_contract_ledger(_fixture_path())
    new_schedule = build_salary_schedule(ledger, _CONFIG)
    overrides_df = load_schedule_overrides(overrides_path)
    new_schedule = apply_schedule_overrides(new_schedule, overrides_df)

    reloaded_status = load_validation_status(status_path)
    queue_after = get_validation_queue(new_schedule, reloaded_status)
    validated_after = get_validated_players(new_schedule, reloaded_status)

    queue_names_after = [p["player"] for p in queue_after]
    validated_names = [p["player"] for p in validated_after]

    assert "Player Four" not in queue_names_after
    assert "Player Five" in queue_names_after
    assert "Player Four" in validated_names
