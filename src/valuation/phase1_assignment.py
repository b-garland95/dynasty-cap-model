from __future__ import annotations

from typing import Any

import pandas as pd

SLOTS: tuple[str, ...] = ("QB", "RB", "WR", "TE", "FLEX", "SF")


def assign_leaguewide_starting_set(week_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Assign players into the leaguewide optimal constrained starting set."""
    teams = int(config["league"]["teams"])
    lineup = config["lineup"]
    required_counts = {
        "QB": teams * int(lineup["qb"]),
        "RB": teams * int(lineup["rb"]),
        "WR": teams * int(lineup["wr"]),
        "TE": teams * int(lineup["te"]),
        "FLEX": teams * int(lineup["flex"]),
        "SF": teams * int(lineup["superflex"]),
    }

    remaining = week_df.copy()
    assigned_frames: list[pd.DataFrame] = []

    slot_rules = [
        ("QB", ["QB"]),
        ("RB", ["RB"]),
        ("WR", ["WR"]),
        ("TE", ["TE"]),
        ("FLEX", ["RB", "WR", "TE"]),
        ("SF", ["QB", "RB", "WR", "TE"]),
    ]

    for slot_name, eligible_positions in slot_rules:
        assigned_df, remaining = _assign_slot(
            remaining=remaining,
            eligible_positions=eligible_positions,
            required_count=required_counts[slot_name],
            slot_name=slot_name,
        )
        assigned_frames.append(assigned_df)

    return pd.concat(assigned_frames, ignore_index=True)


def compute_weekly_margins(started_df: pd.DataFrame, cutlines: dict[str, float]) -> pd.DataFrame:
    """Compute position-based weekly margins and positive/negative weekly value.

    ``cutlines`` must be keyed by position (QB, RB, WR, TE).  Every player's
    margin is measured against their own position's cutline, regardless of
    which slot they were assigned to.
    """
    result = started_df.copy()
    result["margin"] = result.apply(
        lambda row: float(row["points"]) - float(cutlines[row["position"]]),
        axis=1,
    )
    result["wmsv"] = result["margin"].clip(lower=0.0)
    result["wdrag"] = result["margin"].clip(upper=0.0)
    return result


def compute_sav_for_week(
    week_df: pd.DataFrame,
    position_cutlines: dict[str, float],
    config: dict[str, Any],
) -> pd.DataFrame:
    """Assign the weekwide starting set and compute weekly margins for SAV."""
    started_df = assign_leaguewide_starting_set(week_df, config)
    return compute_weekly_margins(started_df, position_cutlines)


# Fallback slot for players not in the leaguewide starting set.
_FALLBACK_SLOT: dict[str, str] = {
    "QB": "SF",
    "RB": "FLEX",
    "WR": "FLEX",
    "TE": "FLEX",
}


def compute_full_pool_margins(
    week_df: pd.DataFrame,
    position_cutlines: dict[str, float],
    config: dict[str, Any],
    min_points: float = 0.1,
) -> pd.DataFrame:
    """Compute margins for ALL players in the weekly pool, not just starters.

    Players in the optimal starting set get their assigned slot.
    Non-starters get a fallback slot (QB→SF, RB/WR/TE→FLEX) so the capture
    model can determine start probability.  Margins for all players are
    computed against their **position** cutline.

    Parameters
    ----------
    week_df:
        Full weekly player pool with columns: gsis_id, player, position, points.
    position_cutlines:
        Shrunk cutlines keyed by position (QB, RB, WR, TE).
    config:
        League config dict.
    min_points:
        Minimum actual points to include a player (filters out zeroes/inactives).

    Returns
    -------
    DataFrame with all players and their margin, wmsv, wdrag, assigned_slot.
    """
    # Filter to players meeting minimum threshold.
    pool = week_df[week_df["points"] >= min_points].copy()
    if pool.empty:
        return pd.DataFrame()

    # Get the optimal starting set with assigned slots.
    started_df = assign_leaguewide_starting_set(pool, config)

    # Build the non-starter pool: everyone not in the starting set.
    id_col = "gsis_id" if "gsis_id" in pool.columns else "player"
    started_ids = set(started_df[id_col].values)
    non_starters = pool[~pool[id_col].isin(started_ids)].copy()

    # Assign fallback slots to non-starters.
    non_starters["assigned_slot"] = non_starters["position"].map(_FALLBACK_SLOT)
    non_starters["rank_within_slot"] = 0

    id_cols = [id_col] if id_col != "player" else []
    keep_cols = id_cols + ["player", "position", "points", "assigned_slot", "rank_within_slot"]
    non_starters = non_starters[[c for c in keep_cols if c in non_starters.columns]]

    # Combine starters + non-starters, compute margins.
    full_pool = pd.concat([started_df, non_starters], ignore_index=True)
    return compute_weekly_margins(full_pool, position_cutlines)



def _assign_slot(
    remaining: pd.DataFrame,
    eligible_positions: list[str],
    required_count: int,
    slot_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = remaining[remaining["position"].isin(eligible_positions)].sort_values(
        "points",
        ascending=False,
    )
    if len(eligible) < required_count:
        raise ValueError(
            f"Insufficient eligible players for slot {slot_name}: need {required_count}, found {len(eligible)}"
        )

    chosen = eligible.head(required_count).copy()
    chosen["assigned_slot"] = slot_name
    chosen["rank_within_slot"] = range(1, len(chosen) + 1)
    updated_remaining = remaining.drop(index=chosen.index)
    id_cols = ["gsis_id"] if "gsis_id" in chosen.columns else []
    return chosen[id_cols + ["player", "position", "points", "assigned_slot", "rank_within_slot"]], updated_remaining
