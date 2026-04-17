"""Free agent market valuation framework.

Produces two outputs:
  1. A player-level table with projected_value (tv_y0) and market_adjusted_value.
  2. A league-level cap environment dict that explains the inflation/deflation signal.

Market mechanism (v1):
  cap_to_value_ratio (CVR) = available_cap / total_fa_projected_value
  market_multiplier         = CVR ^ alpha   (dampened power law)
  market_adjusted_value     = projected_value * market_multiplier

Available cap uses the precise per-team formula that matches the League Config screen:
  cap_remaining_per_team = base_cap - current_cap_usage - dead_money
                           - cap_transactions + rollover
  available_cap          = sum(max(cap_remaining_per_team, 0) for all teams)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

_FA_TV_COLUMN = "tv_y0"
_FA_TV_FALLBACK = "esv_hat"
_DEFAULT_ALPHA = 0.5
_MULTIPLIER_FLOOR = 1e-4


def _per_team_cap_remaining(
    current_cap_usage: float,
    base_cap: float,
    team_adj: dict[str, float],
) -> float:
    dead_money = float(team_adj.get("dead_money", 0.0))
    cap_transactions = float(team_adj.get("cap_transactions", 0.0))
    rollover = float(team_adj.get("rollover", 0.0))
    return base_cap - current_cap_usage - dead_money - cap_transactions + rollover


def compute_cap_environment(
    tv_df: pd.DataFrame,
    cap_health_df: pd.DataFrame | None,
    config: dict[str, Any],
    team_adjustments: dict[str, dict[str, float]] | None = None,
) -> dict[str, float]:
    """Compute league-wide cap pressure metrics for the free agent market.

    Parameters
    ----------
    tv_df:
        TV inputs DataFrame; must contain an ``is_rostered`` column and either
        ``tv_y0`` or ``esv_hat`` as the projected-value source.
    cap_health_df:
        Team cap health DataFrame with ``team`` and ``current_cap_usage`` columns.
        When None, total available cap falls back to ``N_teams * base_cap``.
    config:
        League config dict (from ``load_league_config()``).
    team_adjustments:
        Per-team adjustment dict ``{team: {dead_money, cap_transactions, rollover}}``.
        Matches the schema managed by ``src/contracts/team_adjustments.py``.
        When None, adjustments default to zero for all teams.

    Returns
    -------
    dict with keys:
        total_cap_available, total_fa_value, cap_to_value_ratio,
        market_multiplier, inflation_pct, alpha
    """
    n_teams = int(config["league"]["teams"])
    base_cap = float(config["cap"]["base_cap"])
    alpha = float(
        config.get("free_agent_market", {}).get("cap_pressure_alpha", _DEFAULT_ALPHA)
    )
    adj = team_adjustments or {}

    if cap_health_df is not None and not cap_health_df.empty:
        total_cap_available = 0.0
        for _, row in cap_health_df.iterrows():
            team = str(row.get("team", ""))
            remaining = _per_team_cap_remaining(
                current_cap_usage=float(row.get("current_cap_usage", 0.0)),
                base_cap=base_cap,
                team_adj=adj.get(team, {}),
            )
            total_cap_available += max(remaining, 0.0)
    else:
        total_cap_available = float(n_teams * base_cap)

    is_rostered = (
        tv_df["is_rostered"].fillna(False).astype(bool)
        if "is_rostered" in tv_df.columns
        else pd.Series(False, index=tv_df.index)
    )
    tv_col = _FA_TV_COLUMN if _FA_TV_COLUMN in tv_df.columns else _FA_TV_FALLBACK
    fa_values = pd.to_numeric(
        tv_df.loc[~is_rostered, tv_col], errors="coerce"
    ).fillna(0.0)
    total_fa_value = float(fa_values.sum())

    cpr = total_cap_available / total_fa_value if total_fa_value > 0.0 else 1.0
    market_multiplier = float(max(cpr, _MULTIPLIER_FLOOR) ** alpha)
    inflation_pct = (market_multiplier - 1.0) * 100.0

    return {
        "total_cap_available": total_cap_available,
        "total_fa_value": total_fa_value,
        "cap_to_value_ratio": cpr,
        "market_multiplier": market_multiplier,
        "inflation_pct": inflation_pct,
        "alpha": alpha,
    }


def build_free_agent_market_table(
    tv_df: pd.DataFrame,
    cap_health_df: pd.DataFrame | None,
    config: dict[str, Any],
    team_adjustments: dict[str, dict[str, float]] | None = None,
    include_rostered: bool = False,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build the free agent market valuation table.

    Parameters
    ----------
    tv_df:
        TV inputs DataFrame (from ``tv_inputs.csv``).  Required columns:
        ``player``, ``position``, ``team``.  Optional but used when present:
        ``tv_y0``, ``esv_hat``, ``adp``, ``esv_p25``, ``esv_p50``, ``esv_p75``,
        ``is_rostered``.
    cap_health_df:
        Team cap health DataFrame; see ``compute_cap_environment``.
    config:
        League config dict.
    team_adjustments:
        Per-team cap adjustment dict; see ``compute_cap_environment``.
    include_rostered:
        When False (default) the output contains only players with
        ``is_rostered = False``.  When True, all players are included.

    Returns
    -------
    (player_df, cap_env_dict)
        player_df columns: player, position, team, adp, is_rostered,
                           esv_p25, esv_p50, esv_p75,
                           projected_value, market_adjusted_value,
                           market_premium_pct
        cap_env_dict: output of ``compute_cap_environment``
    """
    cap_env = compute_cap_environment(tv_df, cap_health_df, config, team_adjustments)
    multiplier = cap_env["market_multiplier"]

    working = tv_df.copy()

    if "is_rostered" not in working.columns:
        working["is_rostered"] = False
    working["is_rostered"] = working["is_rostered"].fillna(False).astype(bool)

    if not include_rostered:
        working = working[~working["is_rostered"]].copy()

    tv_col = _FA_TV_COLUMN if _FA_TV_COLUMN in working.columns else _FA_TV_FALLBACK
    working["projected_value"] = pd.to_numeric(
        working[tv_col], errors="coerce"
    ).fillna(0.0)
    working["market_adjusted_value"] = working["projected_value"] * multiplier
    working["market_premium_pct"] = cap_env["inflation_pct"]

    base_cols = [c for c in ["player", "position", "team"] if c in working.columns]
    optional_cols = [
        c
        for c in ["adp", "is_rostered", "esv_p25", "esv_p50", "esv_p75"]
        if c in working.columns
    ]
    value_cols = ["projected_value", "market_adjusted_value", "market_premium_pct"]

    result = (
        working[base_cols + optional_cols + value_cols]
        .drop_duplicates(subset=["player", "position"] if "player" in working.columns else None)
        .sort_values("projected_value", ascending=False)
        .reset_index(drop=True)
    )

    return result, cap_env
