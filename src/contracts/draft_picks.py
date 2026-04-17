"""Draft pick ownership management for dynasty cap leagues.

Pick ID format
--------------
Regular pick   : "{year}_{round}_t_{team_key}"
                 team_key = normalize_team_key(original_team)
                 e.g. "2026_1_t_big_boom_machine"

Compensatory   : "{year}_{round}_comp_{n:02d}"
                 n = 1-based index among comp picks for that round (config order)
                 e.g. "2026_2_comp_01"

The slot (draft position within the round) is NOT part of the pick ID.
It is a separately stored attribute, set when the draft order for a year is
finalized.  This means pick IDs never change across the pick lifecycle.

Ownership storage
-----------------
A JSON object mapping pick_id → ownership record:

  {
    "2026_1_t_big_boom_machine": {
      "original_team": "Big Boom Machine",
      "owner":         "Big Boom Machine",
      "slot":          4
    },
    "2027_1_t_big_boom_machine": {
      "original_team": "Big Boom Machine",
      "owner":         "Turner | Banana Breath",
      "slot":          null
    },
    "2026_2_comp_01": {
      "original_team": null,
      "owner":         null,
      "slot":          11
    }
  }

Fields:
  original_team : str | None  team the pick was originally assigned to.
  owner         : str | None  current owner; may differ from original after a trade.
  slot          : int | None  draft position within the round; null until order is set.

generate_picks() derives one pick per team per round per year from the ownership
file, plus comp picks from the league config.  If ownership is empty, only comp
picks are returned (team picks are not fabricated without data).

Backward compatibility
----------------------
load_ownership() auto-migrates two legacy formats on read:
  - Old string format  : pick_id → "Team Name"  becomes {original_team, owner, slot=null}
  - Old slot-based IDs : "2026_1_03" → "Team Name"  re-keyed to "2026_1_t_{key}", slot=3
    Entries with no original_team (old placeholder nulls) are silently dropped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OWNERSHIP_PATH = _REPO_ROOT / "data" / "processed" / "draft_pick_ownership.json"

# Matches the OLD slot-based pick_id format: "{year}_{round}_{slot:02d}"
_LEGACY_SLOT_RE = re.compile(r'^(\d{4})_(\d+)_(\d{2})$')


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def normalize_team_key(team: str) -> str:
    """Convert a team name to a stable lowercase slug for use in pick IDs."""
    return re.sub(r'[^a-z0-9]+', '_', team.lower()).strip('_')


def make_comp_pick_id(year: int, rnd: int, comp_index: int) -> str:
    """Return the pick_id for a compensatory pick."""
    return f"{year}_{rnd}_comp_{comp_index:02d}"


def make_team_pick_id(year: int, rnd: int, original_team: str) -> str:
    """Return the pick_id for a regular (team-based) pick."""
    return f"{year}_{rnd}_t_{normalize_team_key(original_team)}"


# ---------------------------------------------------------------------------
# Salary lookup
# ---------------------------------------------------------------------------

def _pick_salary(
    rnd: int,
    slot: int | None,
    round1_salaries: dict[str, Any],
    round_flat_salaries: dict[int, Any],
) -> int | None:
    if slot is None:
        return None
    if rnd == 1:
        return round1_salaries.get(f"1.{slot:02d}")
    return round_flat_salaries.get(rnd)


# ---------------------------------------------------------------------------
# Pick generation
# ---------------------------------------------------------------------------

def generate_picks(
    config: dict[str, Any],
    ownership: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Generate pick metadata for all tracked draft years.

    Regular picks are derived from the teams present in ownership as
    original_team values.  One pick per team per round per year is generated.
    Teams are shared across all tracked years (same 10 teams each year).

    Compensatory picks are always generated from the config's compensatory_picks
    list, regardless of ownership.

    Parameters
    ----------
    config:
        Loaded league config dict (from load_league_config).
    ownership:
        Ownership dict from load_ownership().  Required to produce team-based
        picks.  If None or empty, only comp picks are returned.

    Returns
    -------
    List of dicts, each with:
      pick_id        : str
      year           : int
      round          : int
      slot           : int | None   None until draft order is set for that year
      salary         : int | None   None when slot is None
      order_known    : bool
      is_compensatory: bool
      original_team  : str | None
    """
    target_season = int(config["season"]["target_season"])
    dp_cfg = config.get("draft_picks", {})
    future_years = int(dp_cfg.get("future_years_tracked", 2))
    rounds = int(dp_cfg.get("rounds", 4))
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

    # Unique original teams from ownership (sorted for stable output).
    all_teams: list[str] = sorted({
        rec.get("original_team")
        for rec in (ownership or {}).values()
        if isinstance(rec, dict) and rec.get("original_team")
    })

    # Comp picks by round: {round: [slot, ...]} sorted ascending.
    comp_by_round: dict[int, list[int]] = {}
    for c in comp_picks_cfg:
        comp_by_round.setdefault(int(c["round"]), []).append(int(c["slot"]))
    for rnd_slots in comp_by_round.values():
        rnd_slots.sort()

    picks: list[dict[str, Any]] = []
    for year_offset in range(future_years + 1):
        year = target_season + year_offset
        order_known = year in years_with_known_order

        for rnd in range(1, rounds + 1):
            # Regular picks — one per team.
            for team in all_teams:
                pid = make_team_pick_id(year, rnd, team)
                rec = (ownership or {}).get(pid) or {}
                slot: int | None = rec.get("slot")
                # original_team from ownership record (canonical name) or the team
                # variable (if record doesn't exist yet for this year/round combo).
                original_team: str = rec.get("original_team") or team
                picks.append({
                    "pick_id": pid,
                    "year": year,
                    "round": rnd,
                    "slot": slot,
                    "salary": _pick_salary(rnd, slot, round1_salaries, round_flat_salaries),
                    "order_known": order_known,
                    "is_compensatory": False,
                    "original_team": original_team,
                })

            # Compensatory picks.
            for comp_idx, slot in enumerate(comp_by_round.get(rnd, []), start=1):
                pid = make_comp_pick_id(year, rnd, comp_idx)
                picks.append({
                    "pick_id": pid,
                    "year": year,
                    "round": rnd,
                    "slot": slot,
                    "salary": _pick_salary(rnd, slot, round1_salaries, round_flat_salaries),
                    "order_known": order_known,
                    "is_compensatory": True,
                    "original_team": None,
                })

    return picks


# ---------------------------------------------------------------------------
# Ownership persistence
# ---------------------------------------------------------------------------

def _normalize_record(value: Any) -> dict[str, Any]:
    """Coerce any ownership value to the canonical {original_team, owner, slot} form."""
    if isinstance(value, dict):
        return {
            "original_team": value.get("original_team"),
            "owner": value.get("owner"),
            "slot": value.get("slot"),
        }
    # Old string or null format.
    return {"original_team": value, "owner": value, "slot": None}


def load_ownership(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load pick ownership from a JSON file.

    Performs two automatic migrations on read:
    1. Old string values (pick_id → "Team") become full records.
    2. Old slot-based pick IDs ("2026_1_03") are re-keyed to team-based IDs
       ("2026_1_t_team_key") when the record has an original_team.  Entries
       with no original_team (old unowned placeholders) are dropped.

    Returns a dict mapping pick_id → {original_team, owner, slot}.
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

    result: dict[str, dict[str, Any]] = {}
    for pick_id, raw_value in data.items():
        rec = _normalize_record(raw_value)

        # Migrate legacy slot-based pick IDs.
        m = _LEGACY_SLOT_RE.match(pick_id)
        if m:
            year, rnd, slot_str = m.group(1), m.group(2), m.group(3)
            original_team = rec.get("original_team")
            if not original_team:
                # Unowned placeholder — drop.
                continue
            new_id = make_team_pick_id(int(year), int(rnd), original_team)
            rec["slot"] = int(slot_str)
            result[new_id] = rec
        else:
            result[pick_id] = rec

    return result


def save_ownership(
    ownership: dict[str, dict[str, Any]],
    path: str | Path | None = None,
) -> None:
    """Persist pick ownership to a JSON file.

    Creates parent directories as needed.
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
    slot: int | None = None,
) -> dict[str, Any]:
    """Create an ownership record.  owner defaults to original_team if not given."""
    return {
        "original_team": original_team,
        "owner": original_team if owner is None else owner,
        "slot": slot,
    }


def set_owner(
    ownership: dict[str, dict[str, Any]],
    pick_id: str,
    new_owner: str | None,
) -> None:
    """Update current owner without changing original_team or slot."""
    if pick_id in ownership:
        ownership[pick_id] = {**ownership[pick_id], "owner": new_owner}
    else:
        ownership[pick_id] = {"original_team": None, "owner": new_owner, "slot": None}


def set_draft_order(
    ownership: dict[str, dict[str, Any]],
    year: int,
    rnd: int,
    teams_in_slot_order: list[str],
) -> None:
    """Assign slots to a full round for a given year.

    Parameters
    ----------
    ownership:
        Ownership dict (mutated in place).
    year:
        Draft year.
    rnd:
        Round number.
    teams_in_slot_order:
        Team names in draft order, index 0 = slot 1.
    """
    for slot, team in enumerate(teams_in_slot_order, start=1):
        pid = make_team_pick_id(year, rnd, team)
        if pid in ownership:
            ownership[pid] = {**ownership[pid], "slot": slot}
        else:
            ownership[pid] = make_pick_record(team, slot=slot)


def register_teams(
    ownership: dict[str, dict[str, Any]],
    teams: list[str],
    years: list[int],
    rounds: int,
) -> None:
    """Ensure every team has ownership records for every year/round combination.

    Only adds records that do not already exist.  Does not overwrite.
    """
    for year in years:
        for rnd in range(1, rounds + 1):
            for team in teams:
                pid = make_team_pick_id(year, rnd, team)
                if pid not in ownership:
                    ownership[pid] = make_pick_record(team)


# ---------------------------------------------------------------------------
# Inventory queries
# ---------------------------------------------------------------------------

def get_team_picks(
    ownership: dict[str, dict[str, Any]],
    team: str,
    picks: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return pick_ids currently owned by the given team, sorted.

    Filters by the 'owner' field in ownership records.
    """
    if picks is not None:
        valid_ids = {p["pick_id"] for p in picks}
        return sorted(
            pid
            for pid, rec in ownership.items()
            if isinstance(rec, dict) and rec.get("owner") == team and pid in valid_ids
        )
    return sorted(
        pid
        for pid, rec in ownership.items()
        if isinstance(rec, dict) and rec.get("owner") == team
    )


def build_inventory_table(
    picks: list[dict[str, Any]],
    ownership: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge pick metadata with current ownership.

    Returns picks in input order, each augmented with:
      owner : str | None  current owner from ownership (or original_team if unset)
    """
    result = []
    for pick in picks:
        rec = ownership.get(pick["pick_id"]) or {}
        owner = rec.get("owner")
        # Default: owner is the original_team encoded in the pick.
        if owner is None:
            owner = pick.get("original_team")
        result.append({**pick, "owner": owner})
    return result


def all_teams_from_ownership(
    ownership: dict[str, dict[str, Any]],
) -> list[str]:
    """Return sorted list of unique current owners in the ownership dict."""
    return sorted({
        rec.get("owner")
        for rec in ownership.values()
        if isinstance(rec, dict) and rec.get("owner") is not None
    })
