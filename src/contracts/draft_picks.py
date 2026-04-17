"""Draft pick ownership management for dynasty cap leagues.

Data model
----------
Each pick is a dict with:
  pick_id        : str   "{year}_{round}_{slot:02d}", e.g. "2026_1_03"
  year           : int
  round          : int
  slot           : int   1-indexed.  For years where order_known=False, the
                         slot is a placeholder sequence number, not a real
                         draft position.
  salary         : int | None  from rookie_scale
  order_known    : bool  True only for years listed in years_with_known_order.
                         When False, slot has no positional meaning yet.
  is_compensatory: bool  True for extra picks configured in compensatory_picks.

Ownership storage
-----------------
A JSON object mapping pick_id → ownership record:

  {
    "2026_1_01": {"original_team": "Team A", "owner": "Team A"},
    "2026_1_02": {"original_team": "Team B", "owner": "Team C"},
    "2026_2_11": {"original_team": null, "owner": null}
  }

Fields:
  original_team : str | None  team to which the pick was originally assigned.
  owner         : str | None  current owner; may differ after a trade.
                              Defaults to original_team when a pick is created.

Backward compatibility: the old format (pick_id → team_name_string | null) is
auto-migrated to the new format by load_ownership().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OWNERSHIP_PATH = _REPO_ROOT / "data" / "processed" / "draft_pick_ownership.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pick_salary(
    rnd: int,
    slot: int,
    round1_salaries: dict[str, Any],
    round_flat_salaries: dict[int, Any],
) -> int | None:
    if rnd == 1:
        return round1_salaries.get(f"1.{slot:02d}")
    return round_flat_salaries.get(rnd)


def _migrate_record(value: Any) -> dict[str, str | None]:
    """Convert an old-format ownership value (str | None) to new-format dict."""
    if isinstance(value, dict):
        return value
    # Old format: string team name or null → both fields set to that value.
    return {"original_team": value, "owner": value}


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
      pick_id        : str   "{year}_{round}_{slot:02d}"
      year           : int
      round          : int
      slot           : int   1-indexed; placeholder only when order_known=False
      salary         : int | None
      order_known    : bool
      is_compensatory: bool
    """
    target_season = int(config["season"]["target_season"])
    dp_cfg = config.get("draft_picks", {})
    future_years = int(dp_cfg.get("future_years_tracked", 2))
    rounds = int(dp_cfg.get("rounds", 4))
    picks_per_round = int(dp_cfg.get("picks_per_round", config["league"]["teams"]))
    years_with_known_order: set[int] = {
        int(y) for y in dp_cfg.get("years_with_known_order", [])
    }
    comp_picks_cfg: list[dict[str, int]] = dp_cfg.get("compensatory_picks", [])

    rookie_scale = config.get("rookie_scale", {})
    round1_salaries: dict[str, Any] = rookie_scale.get("round1", {})
    round_flat_salaries: dict[int, Any] = {
        2: rookie_scale.get("round2_salary"),
        3: rookie_scale.get("round3_salary"),
        4: rookie_scale.get("round4_salary"),
    }

    picks: list[dict[str, Any]] = []
    for year_offset in range(future_years + 1):
        year = target_season + year_offset
        order_known = year in years_with_known_order
        for rnd in range(1, rounds + 1):
            for slot in range(1, picks_per_round + 1):
                picks.append({
                    "pick_id": f"{year}_{rnd}_{slot:02d}",
                    "year": year,
                    "round": rnd,
                    "slot": slot,
                    "salary": _pick_salary(rnd, slot, round1_salaries, round_flat_salaries),
                    "order_known": order_known,
                    "is_compensatory": False,
                })
            for comp in comp_picks_cfg:
                if int(comp["round"]) == rnd:
                    slot = int(comp["slot"])
                    picks.append({
                        "pick_id": f"{year}_{rnd}_{slot:02d}",
                        "year": year,
                        "round": rnd,
                        "slot": slot,
                        "salary": _pick_salary(rnd, slot, round1_salaries, round_flat_salaries),
                        "order_known": order_known,
                        "is_compensatory": True,
                    })
    return picks


# ---------------------------------------------------------------------------
# Ownership persistence
# ---------------------------------------------------------------------------

def load_ownership(path: str | Path | None = None) -> dict[str, dict[str, str | None]]:
    """Load pick ownership from a JSON file.

    Returns a dict mapping pick_id → {"original_team": ..., "owner": ...}.
    Returns an empty dict if the file does not exist.

    Old-format files (pick_id → string | null) are auto-migrated to the new
    format on load; the file on disk is NOT rewritten automatically.

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
    return {pick_id: _migrate_record(val) for pick_id, val in data.items()}


def save_ownership(
    ownership: dict[str, dict[str, str | None]],
    path: str | Path | None = None,
) -> None:
    """Persist pick ownership to a JSON file.

    Creates parent directories as needed.

    Parameters
    ----------
    ownership:
        Dict mapping pick_id → {"original_team": str|None, "owner": str|None}.
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
# Ownership helpers
# ---------------------------------------------------------------------------

def make_pick_record(
    original_team: str | None,
    owner: str | None = None,
) -> dict[str, str | None]:
    """Create an ownership record, defaulting owner to original_team."""
    return {
        "original_team": original_team,
        "owner": original_team if owner is None else owner,
    }


def set_owner(
    ownership: dict[str, dict[str, str | None]],
    pick_id: str,
    new_owner: str | None,
) -> None:
    """Update the current owner of a pick without changing original_team.

    If the pick_id is not yet in ownership, it is created with
    original_team=None and the given owner.
    """
    if pick_id in ownership:
        ownership[pick_id] = {
            "original_team": ownership[pick_id].get("original_team"),
            "owner": new_owner,
        }
    else:
        ownership[pick_id] = {"original_team": None, "owner": new_owner}


# ---------------------------------------------------------------------------
# Inventory queries
# ---------------------------------------------------------------------------

def get_team_picks(
    ownership: dict[str, dict[str, str | None]],
    team: str,
    picks: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return pick_ids currently owned by the given team, in natural order.

    Parameters
    ----------
    ownership:
        Dict from load_ownership().
    team:
        Team name to filter by (exact string match on the 'owner' field).
    picks:
        If provided, constrains results to pick_ids present in this list.

    Returns
    -------
    Sorted list of pick_ids owned by team.
    """
    if picks is not None:
        valid_ids = {p["pick_id"] for p in picks}
        return sorted(
            pick_id
            for pick_id, rec in ownership.items()
            if rec.get("owner") == team and pick_id in valid_ids
        )
    return sorted(
        pick_id for pick_id, rec in ownership.items() if rec.get("owner") == team
    )


def build_inventory_table(
    picks: list[dict[str, Any]],
    ownership: dict[str, dict[str, str | None]],
) -> list[dict[str, Any]]:
    """Merge pick metadata with current ownership.

    Returns a list of dicts with all pick keys plus:
      original_team : str | None
      owner         : str | None

    Picks are returned in the same order as the input list.
    """
    result = []
    for pick in picks:
        rec = ownership.get(pick["pick_id"], {})
        result.append({
            **pick,
            "original_team": rec.get("original_team"),
            "owner": rec.get("owner"),
        })
    return result


def all_teams_from_ownership(
    ownership: dict[str, dict[str, str | None]],
) -> list[str]:
    """Return sorted list of unique team names present as current owners."""
    return sorted({
        rec.get("owner")
        for rec in ownership.values()
        if rec.get("owner") is not None
    })
