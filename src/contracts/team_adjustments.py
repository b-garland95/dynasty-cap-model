"""Team-level cap adjustment management for dynasty cap leagues.

Stores per-team manual inputs that feed into the Cap Remaining calculation:
  Cap Remaining = Starting Cap - Current Contract Value - Dead Money - Cap Transactions + Rollover

Storage schema
--------------
A JSON object mapping team name → adjustment values.

  {
    "Team A": {"dead_money": 5.0, "cap_transactions": -3.0, "rollover": 12.5},
    "Team B": {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 0.0}
  }

- dead_money: actual dead money charges incurred (float >= 0)
- cap_transactions: net cap impact from trades/moves (positive = credits, negative = charges)
- rollover: unused cap carried forward from prior season (float >= 0)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADJUSTMENTS_PATH = _REPO_ROOT / "data" / "processed" / "team_cap_adjustments.json"

ADJUSTMENT_FIELDS = ("dead_money", "cap_transactions", "rollover")


def load_team_adjustments(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """Load team cap adjustments from a JSON file.

    Returns an empty dict if the file does not exist.
    """
    if path is None:
        path = DEFAULT_ADJUSTMENTS_PATH
    path_obj = Path(path)
    if not path_obj.exists():
        return {}
    with path_obj.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(
            f"team_cap_adjustments file must be a JSON object, got {type(data).__name__}"
        )
    return data


def save_team_adjustments(
    data: dict[str, dict[str, float]],
    path: str | Path | None = None,
) -> None:
    """Validate and persist team cap adjustments to a JSON file."""
    validate_team_adjustments(data)
    if path is None:
        path = DEFAULT_ADJUSTMENTS_PATH
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def validate_team_adjustments(data: dict[str, Any]) -> None:
    """Validate team cap adjustments structure and values.

    Raises ValueError on invalid data.
    """
    if not isinstance(data, dict):
        raise ValueError("Team adjustments must be a JSON object")

    for team, entry in data.items():
        if not isinstance(team, str):
            raise ValueError(f"Team name must be a string, got {type(team).__name__}")
        if not isinstance(entry, dict):
            raise ValueError(f"Adjustment for {team!r} must be an object, got {type(entry).__name__}")

        for field in ADJUSTMENT_FIELDS:
            if field not in entry:
                raise ValueError(f"Adjustment for {team!r} missing required field {field!r}")
            value = entry[field]
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Adjustment for {team!r}.{field} must be a number, got {type(value).__name__}"
                )

        if entry["dead_money"] < 0:
            raise ValueError(f"Adjustment for {team!r}.dead_money must be >= 0, got {entry['dead_money']}")
        if entry["rollover"] < 0:
            raise ValueError(f"Adjustment for {team!r}.rollover must be >= 0, got {entry['rollover']}")


def get_team_adjustment(
    adjustments: dict[str, dict[str, float]],
    team: str,
) -> dict[str, float]:
    """Return adjustment values for a team, defaulting to zeros if not present."""
    return adjustments.get(team, {"dead_money": 0.0, "cap_transactions": 0.0, "rollover": 0.0})
