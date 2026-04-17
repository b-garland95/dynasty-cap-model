"""Contract schedule validation workflow — queue management and status persistence."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

VALIDATION_STATUS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "processed" / "contract_schedule_validation_status.json"
)
DEFAULT_OVERRIDES_PATH = (
    Path(__file__).resolve().parents[2]
    / "data" / "raw" / "roster_exports" / "contract_salary_schedule_overrides.csv"
)

_OVERRIDE_COLUMNS = [
    "player", "team", "position", "year_index",
    "cap_hit_real", "cap_hit_current", "schedule_source", "needs_schedule_validation",
]


def _player_key(player: str, team: str) -> str:
    return f"{player}|{team}"


def load_validation_status(path: str | Path | None = None) -> dict[str, Any]:
    """Load validation status dict from JSON; returns empty dict if file missing."""
    p = Path(path) if path else VALIDATION_STATUS_PATH
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_validation_status(data: dict[str, Any], path: str | Path | None = None) -> None:
    """Persist validation status JSON."""
    p = Path(path) if path else VALIDATION_STATUS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def mark_player_validated(
    validation_status: dict[str, Any],
    player: str,
    team: str,
    validated_at: str | None = None,
) -> dict[str, Any]:
    """Return updated validation_status with the given player marked as validated."""
    key = _player_key(player, team)
    updated = dict(validation_status)
    updated[key] = {
        "status": "validated",
        "validated_at": validated_at or datetime.now(timezone.utc).isoformat(),
    }
    return updated


def get_validation_queue(
    schedule_df: pd.DataFrame,
    validation_status: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return players whose schedule has needs_schedule_validation=True and haven't been validated yet."""
    flagged = schedule_df[schedule_df["needs_schedule_validation"].astype(bool)]
    player_keys = flagged[["player", "team", "position"]].drop_duplicates()

    result: list[dict[str, Any]] = []
    for _, row in player_keys.iterrows():
        key = _player_key(row["player"], row["team"])
        if validation_status.get(key, {}).get("status") == "validated":
            continue
        player_rows = schedule_df[
            (schedule_df["player"] == row["player"]) &
            (schedule_df["team"] == row["team"])
        ].sort_values("year_index")
        result.append({
            "player": row["player"],
            "team": row["team"],
            "position": row["position"],
            "schedule": _to_schedule_records(player_rows),
        })
    return result


def get_validated_players(
    schedule_df: pd.DataFrame,
    validation_status: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return players marked as validated, with their current schedule rows."""
    result: list[dict[str, Any]] = []
    for key, info in validation_status.items():
        if info.get("status") != "validated":
            continue
        parts = key.split("|", 1)
        if len(parts) != 2:
            continue
        player, team = parts
        player_rows = schedule_df[
            (schedule_df["player"] == player) &
            (schedule_df["team"] == team)
        ].sort_values("year_index")
        result.append({
            "player": player,
            "team": team,
            "validated_at": info.get("validated_at"),
            "schedule": _to_schedule_records(player_rows),
        })
    return result


def _to_schedule_records(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert schedule DataFrame rows to JSON-safe dicts (NaN cap_hit_current → None)."""
    records: list[dict[str, Any]] = []
    for _, r in rows.iterrows():
        current = r["cap_hit_current"]
        records.append({
            "year_index": int(r["year_index"]),
            "cap_hit_real": float(r["cap_hit_real"]),
            "cap_hit_current": None if (isinstance(current, float) and math.isnan(current)) else float(current),
            "schedule_source": str(r["schedule_source"]),
            "needs_schedule_validation": bool(r["needs_schedule_validation"]),
        })
    return records


def update_schedule_overrides(
    overrides_path: str | Path,
    player: str,
    team: str,
    position: str,
    schedule_rows: list[dict[str, Any]],
) -> None:
    """Write (or replace) override rows for one player in the overrides CSV.

    Each dict in schedule_rows must have: year_index, cap_hit_real, and optionally
    cap_hit_current and schedule_source.  All written rows get needs_schedule_validation=False,
    since writing to the override dataset is the act of validation.
    """
    path = Path(overrides_path)
    if path.exists():
        existing = pd.read_csv(path)
        mask = (existing["player"] == player) & (existing["team"] == team)
        existing = existing[~mask].reset_index(drop=True)
        for col in _OVERRIDE_COLUMNS:
            if col not in existing.columns:
                existing[col] = None
        existing = existing[_OVERRIDE_COLUMNS]
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = pd.DataFrame(columns=_OVERRIDE_COLUMNS)

    new_rows = []
    for row in schedule_rows:
        current = row.get("cap_hit_current")
        new_rows.append({
            "player": player,
            "team": team,
            "position": position,
            "year_index": int(row["year_index"]),
            "cap_hit_real": float(row["cap_hit_real"]),
            "cap_hit_current": current,
            "schedule_source": row.get("schedule_source", "manual_override"),
            "needs_schedule_validation": False,
        })

    new_df = pd.DataFrame(new_rows, columns=_OVERRIDE_COLUMNS)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(path, index=False)
