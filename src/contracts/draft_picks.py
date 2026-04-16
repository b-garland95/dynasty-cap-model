"""Draft pick ownership management for dynasty cap leagues.

Provides utilities for:
- Generating pick IDs for current + future draft years
- Loading and saving pick ownership from/to a JSON file
- Querying pick inventory by team

Storage schema
--------------
A JSON object mapping pick_id → owner (team name string or null for unowned).

  {
    "2026_1_01": "Team A",
    "2026_1_02": null,
    ...
  }

Pick ID format: "{year}_{round}_{slot:02d}"
  e.g. "2026_1_01", "2026_2_03"

Slot is 1-indexed and zero-padded to 2 digits so lexicographic sort = natural
order within a round.

The rookie pay scale is read from league_config.yaml (rookie_scale section) so
salary information is never duplicated here — this module reads it from the
single source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OWNERSHIP_PATH = _REPO_ROOT / "data" / "processed" / "draft_pick_ownership.json"


# ---------------------------------------------------------------------------
# Pick-ID generation
# ---------------------------------------------------------------------------

def generate_picks(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate pick metadata for all tracked draft years.

    Draft years tracked: target_season through target_season + future_years_tracked.

    Parameters
    ----------
    config:
        Loaded league config dict (from load_league_config).

    Returns
    -------
    List of dicts, each with keys:
      - pick_id  : str  (e.g. "2026_1_01")
      - year     : int
      - round    : int
      - slot     : int  (1-indexed)
      - salary   : int | None  (from rookie_scale; None if not defined)
    """
    target_season = int(config["season"]["target_season"])
    dp_cfg = config.get("draft_picks", {})
    future_years = int(dp_cfg.get("future_years_tracked", 2))
    rounds = int(dp_cfg.get("rounds", 4))
    picks_per_round = int(dp_cfg.get("picks_per_round", config["league"]["teams"]))

    rookie_scale = config.get("rookie_scale", {})
    round1_salaries: dict[str, int] = rookie_scale.get("round1", {})
    round_flat_salaries: dict[int, Any] = {
        2: rookie_scale.get("round2_salary"),
        3: rookie_scale.get("round3_salary"),
        4: rookie_scale.get("round4_salary"),
    }

    picks: list[dict[str, Any]] = []
    for year_offset in range(future_years + 1):
        year = target_season + year_offset
        for rnd in range(1, rounds + 1):
            for slot in range(1, picks_per_round + 1):
                pick_id = f"{year}_{rnd}_{slot:02d}"
                if rnd == 1:
                    slot_key = f"1.{slot:02d}"
                    salary = round1_salaries.get(slot_key)
                else:
                    salary = round_flat_salaries.get(rnd)
                picks.append({
                    "pick_id": pick_id,
                    "year": year,
                    "round": rnd,
                    "slot": slot,
                    "salary": salary,
                })
    return picks


# ---------------------------------------------------------------------------
# Ownership persistence
# ---------------------------------------------------------------------------

def load_ownership(path: str | Path | None = None) -> dict[str, str | None]:
    """Load pick ownership from a JSON file.

    Returns a dict mapping pick_id → owner (str team name or None).
    Returns an empty dict if the file does not exist.

    Raises
    ------
    ValueError
        If the file exists but its top-level JSON value is not an object.
    """
    if path is None:
        path = DEFAULT_OWNERSHIP_PATH
    path_obj = Path(path)
    if not path_obj.exists():
        return {}
    with path_obj.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(
            f"draft_pick_ownership file must be a JSON object, got {type(data).__name__}"
        )
    return data


def save_ownership(
    ownership: dict[str, str | None],
    path: str | Path | None = None,
) -> None:
    """Persist pick ownership to a JSON file.

    Creates parent directories as needed.

    Parameters
    ----------
    ownership:
        Dict mapping pick_id → owner (str or None).
    path:
        Destination path. Defaults to DEFAULT_OWNERSHIP_PATH.
    """
    if path is None:
        path = DEFAULT_OWNERSHIP_PATH
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    with path_obj.open("w", encoding="utf-8") as fh:
        json.dump(ownership, fh, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Inventory queries
# ---------------------------------------------------------------------------

def get_team_picks(
    ownership: dict[str, str | None],
    team: str,
    picks: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return pick_ids owned by the given team, in natural (sorted) order.

    Parameters
    ----------
    ownership:
        Dict from load_ownership().
    team:
        Team name to filter by (exact string match).
    picks:
        If provided, only returns pick_ids present in this list (constrains to
        the valid pick universe for the current config). Pass None to return all
        matching keys in ownership without universe validation.

    Returns
    -------
    Sorted list of pick_ids owned by team.
    """
    if picks is not None:
        valid_ids = {p["pick_id"] for p in picks}
        return sorted(
            pick_id
            for pick_id, owner in ownership.items()
            if owner == team and pick_id in valid_ids
        )
    return sorted(
        pick_id for pick_id, owner in ownership.items() if owner == team
    )


def build_inventory_table(
    picks: list[dict[str, Any]],
    ownership: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Merge pick metadata with current ownership.

    Returns a list of dicts with all keys from each pick plus:
      - owner : str | None  (team name, or None if unowned)

    Picks are returned in the same order as the input `picks` list.
    """
    return [
        {**pick, "owner": ownership.get(pick["pick_id"])}
        for pick in picks
    ]


def all_teams_from_ownership(ownership: dict[str, str | None]) -> list[str]:
    """Return sorted list of unique team names present in ownership."""
    return sorted({v for v in ownership.values() if v is not None})
