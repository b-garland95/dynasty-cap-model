from __future__ import annotations

import math
from typing import Any

import pandas as pd


def compute_ros_projection(proj_df: pd.DataFrame) -> pd.DataFrame:
    """Compute a short rest-of-season proxy using the current and next two weeks."""
    if proj_df.empty:
        return proj_df.copy()

    id_col = _resolve_id_col(proj_df)
    sort_cols = ["season", id_col, "week"]
    ros_df = proj_df.copy().sort_values(sort_cols).reset_index(drop=True)

    grouped = ros_df.groupby(["season", id_col], sort=False)["proj_points"]
    window_cols = [
        grouped.shift(shift_n)
        for shift_n in (0, -1, -2)
    ]
    ros_df["ros_proj"] = pd.concat(window_cols, axis=1).median(axis=1, skipna=True)

    keep_cols = [col for col in ("season", "week", id_col, "player", "position", "ros_proj") if col in ros_df.columns]
    return ros_df[keep_cols].reset_index(drop=True)


def compute_roster_probabilities(
    proj_df: pd.DataFrame,
    adp_salary_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Estimate weekly roster probability from projections and market salary.

    This function is intentionally league-agnostic: it uses public projections,
    ADP-derived market salary, roster capacity, and a simple stickiness rule.
    It does not use actual fantasy points or League Tycoon roster exports.
    """
    if proj_df.empty:
        return pd.DataFrame(columns=["season", "week", "player", "position", "rho_active", "rho"])

    roster_model = config["capture_model"]["roster_model"]
    ps_model = config["capture_model"].get("practice_squad_model", {})
    teams = int(config["league"]["teams"])
    active_capacity = teams * int(roster_model["active_roster_spots_per_team"])
    kappa = float(roster_model["kappa"])
    gamma = float(roster_model["gamma"])
    stickiness_bonus = float(roster_model.get("stickiness_bonus", 0.0))

    id_col = _resolve_shared_id_col(proj_df, adp_salary_df)
    ros_df = compute_ros_projection(proj_df)

    adp_cols = [
        col for col in ("season", id_col, "market_salary", "rookie_flag", "years_exp")
        if col in adp_salary_df.columns
    ]
    merged = ros_df.merge(adp_salary_df[adp_cols].drop_duplicates(), on=["season", id_col], how="left")

    if merged["market_salary"].notna().any():
        season_default_salary = merged.groupby("season")["market_salary"].transform("max")
        merged["market_salary"] = merged["market_salary"].fillna(season_default_salary).fillna(0.0)
    else:
        merged["market_salary"] = 0.0

    merged["desirability"] = merged["ros_proj"].fillna(0.0) - gamma * merged["market_salary"]

    frames: list[pd.DataFrame] = []
    for (season, week), week_df in merged.groupby(["season", "week"], sort=True):
        cutoff = _solve_cutoff_for_capacity(week_df["desirability"], active_capacity, kappa)
        season_week_df = week_df.copy()
        season_week_df["rho_active"] = _sigmoid((season_week_df["desirability"] - cutoff) / kappa)
        frames.append(season_week_df)

    rho_df = pd.concat(frames, ignore_index=True) if frames else merged.copy()
    rho_df["rho_active"] = _apply_stickiness(rho_df, id_col, stickiness_bonus)

    rho_df["rho_ps"] = 0.0
    if bool(ps_model.get("enabled", False)):
        rho_df["rho_ps"] = _compute_practice_squad_probabilities(rho_df, config)

    rho_df["rho"] = 1.0 - (1.0 - rho_df["rho_active"]) * (1.0 - rho_df["rho_ps"])

    agg_map = {"rho_active": "max", "rho_ps": "max", "rho": "max"}
    if "player" in rho_df.columns:
        agg_map["player"] = "first"
    if "position" in rho_df.columns:
        agg_map["position"] = "first"
    rho_df = rho_df.groupby(["season", "week", id_col], as_index=False).agg(agg_map)

    keep_cols = [
        col
        for col in ("season", "week", id_col, "player", "position", "rho_active", "rho_ps", "rho")
        if col in rho_df.columns
    ]
    return rho_df[keep_cols].reset_index(drop=True)


def _apply_stickiness(rho_df: pd.DataFrame, id_col: str, bonus: float) -> pd.Series:
    if bonus <= 0.0 or rho_df.empty:
        return rho_df["rho_active"].clip(0.0, 1.0)

    ordered = rho_df.sort_values(["season", id_col, "week"]).copy()
    prev_lookup: dict[tuple[int, str], float] = {}
    adjusted: list[float] = []

    for row in ordered.itertuples(index=False):
        season = int(getattr(row, "season"))
        player_id = str(getattr(row, id_col))
        key = (season, player_id)
        value = float(getattr(row, "rho_active"))
        if prev_lookup.get(key, 0.0) >= 0.5:
            value = min(1.0, value + bonus)
        prev_lookup[key] = value
        adjusted.append(value)

    ordered["rho_active"] = adjusted
    return ordered.sort_index()["rho_active"].clip(0.0, 1.0)


def _compute_practice_squad_probabilities(rho_df: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Estimate rookie PS stash probability.

    v1 intentionally stays conservative: if no explicit rookie indicator is
    available (`rookie_flag` or `years_exp`), the PS path is disabled rather
    than guessing from public data.
    """
    ps_model = config["capture_model"]["practice_squad_model"]
    teams = int(config["league"]["teams"])
    ps_capacity = teams * int(config["roster"]["practice_squad_slots"])
    if ps_capacity <= 0 or rho_df.empty:
        return pd.Series(0.0, index=rho_df.index, dtype=float)

    rookies = _detect_rookies(rho_df)
    if not rookies.any():
        return pd.Series(0.0, index=rho_df.index, dtype=float)

    roster_model = config["capture_model"]["roster_model"]
    gamma = float(roster_model["gamma"])
    cap_percent = float(ps_model["cap_percent"])
    delta = float(ps_model.get("delta", 0.0))
    kappa_ps = float(ps_model["kappa_ps"])

    ps_series = pd.Series(0.0, index=rho_df.index, dtype=float)
    for (_, _), week_df in rho_df.groupby(["season", "week"], sort=True):
        eligible_idx = week_df.index[rookies.loc[week_df.index]]
        if len(eligible_idx) == 0:
            continue

        desirability = (
            rho_df.loc[eligible_idx, "ros_proj"].fillna(0.0)
            - gamma * (cap_percent * rho_df.loc[eligible_idx, "market_salary"].fillna(0.0))
            + delta
        )
        cutoff = _solve_cutoff_for_capacity(desirability, ps_capacity, kappa_ps)
        ps_series.loc[eligible_idx] = _sigmoid((desirability - cutoff) / kappa_ps)

    return ps_series.clip(0.0, 1.0)


def _detect_rookies(df: pd.DataFrame) -> pd.Series:
    if "rookie_flag" in df.columns:
        return df["rookie_flag"].fillna(False).astype(bool)
    if "years_exp" in df.columns:
        years_exp = pd.to_numeric(df["years_exp"], errors="coerce")
        return years_exp.fillna(99).eq(0)
    return pd.Series(False, index=df.index, dtype=bool)


def _solve_cutoff_for_capacity(desirability: pd.Series, capacity: int, kappa: float) -> float:
    values = desirability.fillna(0.0).astype(float)
    n_players = len(values)
    if n_players == 0:
        return 0.0
    if capacity <= 0:
        return float(values.max() + 1000.0)
    if capacity >= n_players:
        return float(values.min() - 1000.0)

    lower = float(values.min() - 20.0 * kappa - 1.0)
    upper = float(values.max() + 20.0 * kappa + 1.0)
    for _ in range(80):
        midpoint = (lower + upper) / 2.0
        expected = float(_sigmoid((values - midpoint) / kappa).sum())
        if expected > capacity:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _sigmoid(values: pd.Series) -> pd.Series:
    clipped = values.clip(-500.0, 500.0)
    return 1.0 / (1.0 + clipped.map(lambda x: math.exp(-float(x))))


def _resolve_id_col(df: pd.DataFrame) -> str:
    if "gsis_id" in df.columns:
        return "gsis_id"
    return "player"


def _resolve_shared_id_col(proj_df: pd.DataFrame, adp_df: pd.DataFrame) -> str:
    if "gsis_id" in proj_df.columns and "gsis_id" in adp_df.columns:
        return "gsis_id"
    return "player"
