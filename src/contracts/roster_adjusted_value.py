"""
Roster-Adjusted Value (RAV) — Phase 3 post-processing module.

A player's raw TV (tv_y0) reflects their individual projected performance, but it
overstates value for backup players who only start when a roster mate is on bye or
injured.  RAV applies a position- and depth-specific discount to convert raw TV into
the fraction of value a player actually delivers to their specific team's roster.

Discount formula (derived from bye math + historical availability rates):
  absence_rate[pos] = 1 - avg_availability_rate[pos]   (from rav_availability_rates.csv)
  bye_fraction      = 1 / regular_season_weeks

  Starters (any slot):        discount = 1.0
  Bench depth 0, QB:          discount = 2 * bye_fraction + absence_rate[QB]
                               (QB3 covers both starters' independent byes)
  Bench depth 0, RB/WR/TE:   discount = bye_fraction + absence_rate[pos]
  Bench depth 1, all:         discount = absence_rate[pos]^2
  Bench depth 2+, all:        discount = bench_depth_2plus_floor (config, default 0.01)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

_SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "SF"]
_FLEX_ELIGIBLE = {"RB", "WR", "TE"}
_SF_ELIGIBLE = {"QB", "RB", "WR", "TE"}


# ---------------------------------------------------------------------------
# Availability rates
# ---------------------------------------------------------------------------

def load_availability_rates(path: str | Path) -> dict[str, float]:
    """Read rav_availability_rates.csv and return {position: avg_availability_rate}."""
    df = pd.read_csv(path)
    return dict(zip(df["position"], df["avg_availability_rate"].astype(float)))


def compute_depth_discounts(
    availability_rates: dict[str, float],
    regular_season_weeks: int,
    bench_depth_2plus_floor: float = 0.01,
) -> dict[str, list[float]]:
    """
    Return a dict mapping each position to a list of depth-tier discounts:
      discounts[pos][0] = bench_depth 0 discount
      discounts[pos][1] = bench_depth 1 discount
      discounts[pos][2] = bench_depth 2+ discount (floor)

    QB uses 2x bye fraction at depth 0; all other positions use 1x.
    """
    W = regular_season_weeks
    bye = 1.0 / W
    discounts: dict[str, list[float]] = {}
    for pos, avail in availability_rates.items():
        absence = 1.0 - avail
        if pos == "QB":
            d0 = min(2 * bye + absence, 1.0)
        else:
            d0 = min(bye + absence, 1.0)
        d1 = absence ** 2
        d2 = bench_depth_2plus_floor
        discounts[pos] = [d0, d1, d2]
    return discounts


# ---------------------------------------------------------------------------
# Lineup assignment (per-team greedy)
# ---------------------------------------------------------------------------

def assign_team_lineup(
    team_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """
    Assign each player on a single team's roster to a starting slot or bench.

    Slots are filled in order: QB → RB → WR → TE → FLEX → SF.
    Sort key is tv_y0 descending within each eligible position group.

    Returns a copy of team_df with added columns:
      rav_slot   : str — "QB", "RB", "WR", "TE", "FLEX", "SF", or "bench"
      started    : bool
      bench_depth: int — 0-indexed rank among unstarted players of same position
                         (0 for starters, increases with depth)
    """
    lineup = config["lineup"]
    slots_needed = {
        "QB":   int(lineup.get("qb", 1)),
        "RB":   int(lineup.get("rb", 2)),
        "WR":   int(lineup.get("wr", 3)),
        "TE":   int(lineup.get("te", 1)),
        "FLEX": int(lineup.get("flex", 2)),
        "SF":   int(lineup.get("superflex", 1)),
    }

    df = team_df.copy().reset_index(drop=True)
    df["rav_slot"] = "bench"
    df["started"] = False

    remaining = set(df.index)

    def _fill_slot(slot: str, eligible_positions: set[str], count: int) -> None:
        candidates = (
            df.loc[list(remaining & set(df[df["position"].isin(eligible_positions)].index))]
            .sort_values("tv_y0", ascending=False)
        )
        for idx in candidates.index[:count]:
            df.at[idx, "rav_slot"] = slot
            df.at[idx, "started"] = True
            remaining.discard(idx)

    _fill_slot("QB",   {"QB"},          slots_needed["QB"])
    _fill_slot("RB",   {"RB"},          slots_needed["RB"])
    _fill_slot("WR",   {"WR"},          slots_needed["WR"])
    _fill_slot("TE",   {"TE"},          slots_needed["TE"])
    _fill_slot("FLEX", _FLEX_ELIGIBLE,  slots_needed["FLEX"])
    _fill_slot("SF",   _SF_ELIGIBLE,    slots_needed["SF"])

    # Assign bench_depth: 0-indexed within position among unstarted players
    df["bench_depth"] = 0
    for pos in df["position"].unique():
        bench_mask = (~df["started"]) & (df["position"] == pos)
        bench_idx = df.loc[bench_mask].sort_values("tv_y0", ascending=False).index
        for depth, idx in enumerate(bench_idx):
            df.at[idx, "bench_depth"] = depth

    return df


# ---------------------------------------------------------------------------
# RAV computation
# ---------------------------------------------------------------------------

def compute_rav(
    contract_surplus_df: pd.DataFrame,
    config: dict[str, Any],
    availability_rates: dict[str, float],
) -> pd.DataFrame:
    """
    Add RAV columns to contract_surplus_df.

    New columns: rav_slot, started, bench_depth, depth_discount, rav_y0, trade_gap_y0.

    Parameters
    ----------
    contract_surplus_df:
        Output of build_contract_surplus_table(). Must have: player, team, position, tv_y0.
    config:
        League config dict with 'lineup' and 'rav' blocks.
    availability_rates:
        {position: avg_availability_rate} from load_availability_rates().
    """
    rav_cfg = config.get("rav", {})
    regular_season_weeks = int(rav_cfg.get("regular_season_weeks", 17))
    floor = float(rav_cfg.get("bench_depth_2plus_floor", 0.01))

    discounts = compute_depth_discounts(availability_rates, regular_season_weeks, floor)

    pieces: list[pd.DataFrame] = []
    for team, team_df in contract_surplus_df.groupby("team"):
        assigned = assign_team_lineup(team_df, config)
        pieces.append(assigned)

    result = pd.concat(pieces, ignore_index=True)

    def _apply_discount(row: pd.Series) -> float:
        if row["started"]:
            return 1.0
        pos = row["position"]
        depth = int(row["bench_depth"])
        pos_discounts = discounts.get(pos, [floor, floor, floor])
        if depth == 0:
            return pos_discounts[0]
        if depth == 1:
            return pos_discounts[1]
        return pos_discounts[2]  # floor

    result["depth_discount"] = result.apply(_apply_discount, axis=1)
    result["rav_y0"] = result["tv_y0"] * result["depth_discount"]
    result["trade_gap_y0"] = result["tv_y0"] - result["rav_y0"]

    return result


# ---------------------------------------------------------------------------
# Summary tables
# ---------------------------------------------------------------------------

def build_team_rav_summary(rav_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a team-level RAV summary: one row per team.

    Columns: team, total_tv_y0, total_rav_y0, rav_utilization_rate,
             total_trade_gap_y0, and per-position tv/rav breakdowns.
    """
    base = rav_df.groupby("team", as_index=False).agg(
        total_tv_y0=("tv_y0", "sum"),
        total_rav_y0=("rav_y0", "sum"),
        total_trade_gap_y0=("trade_gap_y0", "sum"),
    )
    base["rav_utilization_rate"] = base["total_rav_y0"] / base["total_tv_y0"].replace(0, float("nan"))

    for pos in ["QB", "RB", "WR", "TE"]:
        pos_df = rav_df[rav_df["position"] == pos].groupby("team", as_index=False).agg(
            **{f"tv_{pos.lower()}": ("tv_y0", "sum"), f"rav_{pos.lower()}": ("rav_y0", "sum")}
        )
        base = base.merge(pos_df, on="team", how="left")
        base[f"tv_{pos.lower()}"] = base[f"tv_{pos.lower()}"].fillna(0.0)
        base[f"rav_{pos.lower()}"] = base[f"rav_{pos.lower()}"].fillna(0.0)

    return base.sort_values("total_rav_y0", ascending=False).reset_index(drop=True)


def build_trade_gap_screen(rav_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return bench players sorted by trade_gap_y0 descending.

    These are players whose TV is being heavily discounted on their current
    team because they are backups — prime trade candidates for teams that
    would start them.
    """
    bench = rav_df[~rav_df["started"]].copy()
    cols = [
        "player", "team", "position",
        "tv_y0", "rav_y0", "trade_gap_y0",
        "bench_depth", "rav_slot", "started",
        "cap_y0", "surplus_y0",
        "depth_discount",
    ]
    available_cols = [c for c in cols if c in bench.columns]
    return bench[available_cols].sort_values("trade_gap_y0", ascending=False).reset_index(drop=True)
