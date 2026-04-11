"""Phase 1 season-level pipeline orchestrator.

Wires the individual Phase 1 modules (cutlines, assignment, SAV, RSV/LD,
CG, PAR) into a single ``run_phase1_season()`` call and provides a
multi-season wrapper that concatenates results.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.valuation.capture_model import PerfectCaptureModel, RationalStartCaptureModel
from src.valuation.phase1_assignment import (
    assign_leaguewide_starting_set,
    compute_full_pool_margins,
    compute_weekly_margins,
)
from src.valuation.phase1_cutlines import (
    POSITIONS,
    apply_shrinkage,
    compute_position_cutlines,
    compute_season_base_cutlines,
    compute_weekly_raw_cutlines,
)
from src.valuation.phase1_metrics import aggregate_sav
from src.valuation.phase1_par import compute_par_by_player, compute_position_replacement_level_par
from src.valuation.phase1_realized import compute_capture_gap, compute_rsv_ld_from_started_weekly, compute_rsv_ld_weekly


def run_phase1_season(
    season_points: pd.DataFrame,
    season_proj: pd.DataFrame | None,
    season_adp: pd.DataFrame | None,
    config: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    """Run the full Phase 1 pipeline for one season.

    Parameters
    ----------
    season_points:
        Historical weekly points for a single season.  Must contain:
        ``gsis_id, player, position, points, season, week``.
    season_proj:
        Weekly projections for the same season.  Must contain:
        ``gsis_id, player, position, projected_points, season, week``.
        Pass ``None`` if no projections are available (falls back to
        PerfectCaptureModel).
    season_adp:
        Preseason redraft rankings for the same season. Must contain at least
        ``season, rank`` plus ``gsis_id`` or ``player``. Pass ``None`` to
        fall back to the start-only rational model when projections exist.
    config:
        League config dict.

    Returns
    -------
    dict with keys:
        ``started_weekly``, ``sav``, ``rsv_ld``, ``cg``, ``par``, ``cutlines``.
    """
    season = int(season_points["season"].iloc[0])

    # --- Pass 1: raw cutlines (slot + position) ------------------------------
    raw_slot_cutlines_by_week: list[dict[str, float]] = []
    raw_pos_cutlines_by_week: list[dict[str, float]] = []
    weeks = sorted(season_points["week"].unique())
    for week in weeks:
        week_df = season_points[season_points["week"] == week]
        raw_slot_cutlines_by_week.append(compute_weekly_raw_cutlines(week_df, config))
        started_df = assign_leaguewide_starting_set(week_df, config)
        raw_pos_cutlines_by_week.append(compute_position_cutlines(started_df))

    base_slot_cutlines = compute_season_base_cutlines(raw_slot_cutlines_by_week)
    base_pos_cutlines = compute_season_base_cutlines(raw_pos_cutlines_by_week, keys=POSITIONS)

    # Build a cutlines record for export.
    cutline_rows: list[dict] = []
    for week, raw_slot_cl, raw_pos_cl in zip(weeks, raw_slot_cutlines_by_week, raw_pos_cutlines_by_week):
        shrunk_slot_cl = apply_shrinkage(raw_slot_cl, base_slot_cutlines, config)
        shrunk_pos_cl = apply_shrinkage(raw_pos_cl, base_pos_cutlines, config, keys=POSITIONS)
        for slot in raw_slot_cl:
            cutline_rows.append({
                "season": season,
                "week": week,
                "cutline_type": "slot",
                "key": slot,
                "raw_cutline": raw_slot_cl[slot],
                "shrunk_cutline": shrunk_slot_cl[slot],
                "base_cutline": base_slot_cutlines[slot],
            })
        for pos in raw_pos_cl:
            cutline_rows.append({
                "season": season,
                "week": week,
                "cutline_type": "position",
                "key": pos,
                "raw_cutline": raw_pos_cl[pos],
                "shrunk_cutline": shrunk_pos_cl[pos],
                "base_cutline": base_pos_cutlines[pos],
            })
    cutlines_df = pd.DataFrame(cutline_rows)

    # --- Pass 2: assignment + margins (using position cutlines) -------------
    started_frames: list[pd.DataFrame] = []
    full_pool_frames: list[pd.DataFrame] = []
    for week, raw_slot_cl, raw_pos_cl in zip(weeks, raw_slot_cutlines_by_week, raw_pos_cutlines_by_week):
        week_df = season_points[season_points["week"] == week]
        shrunk_pos_cl = apply_shrinkage(raw_pos_cl, base_pos_cutlines, config, keys=POSITIONS)
        # Top-100 starters for SAV calculation.
        started_df = assign_leaguewide_starting_set(week_df, config)
        started = compute_weekly_margins(started_df, shrunk_pos_cl)
        started["season"] = season
        started["week"] = week
        started_frames.append(started)
        # Full player pool (all players with points >= 0.1) for RSV.
        full_pool = compute_full_pool_margins(week_df, shrunk_pos_cl, config, min_points=0.1)
        full_pool["season"] = season
        full_pool["week"] = week
        full_pool_frames.append(full_pool)

    started_weekly = pd.concat(started_frames, ignore_index=True)
    full_pool_weekly = pd.concat(full_pool_frames, ignore_index=True)
    sav_df = aggregate_sav(started_weekly)

    # --- Capture model + RSV / LD ------------------------------------------
    if season_proj is not None and len(season_proj) > 0:
        proj_renamed = season_proj.rename(columns={"projected_points": "proj_points"})

        # TODO: Re-enable `RationalCaptureModel` once the roster-probability
        # heuristic is behaving sensibly in production Phase 1 runs.
        #
        # The rankings/ADP plumbing is intentionally left in place so we can
        # revisit rho without re-threading the pipeline, but for now RSV uses
        # sigma-only start capture.
        #
        # Interesting review cases from the current rho heuristic:
        # - Brock Purdy, 2025 Week 1: surprisingly low roster probability
        # - Joe Burrow, 2025 Week 2: surprisingly low roster probability
        _ = season_adp
        capture_model = RationalStartCaptureModel(proj_renamed, config)
    else:
        capture_model = PerfectCaptureModel()

    # Compute weekly RSV/LD over the full player pool (not just starters).
    realized_weekly = compute_rsv_ld_weekly(full_pool_weekly, capture_model)
    rsv_ld_df = compute_rsv_ld_from_started_weekly(full_pool_weekly, capture_model)

    # --- Capture gap --------------------------------------------------------
    cg_df = compute_capture_gap(sav_df, rsv_ld_df)

    # --- PAR ----------------------------------------------------------------
    r_par = compute_position_replacement_level_par(season_points, config)
    par_df = compute_par_by_player(season_points, r_par)

    return {
        "started_weekly": realized_weekly,
        "sav": sav_df,
        "rsv_ld": rsv_ld_df,
        "cg": cg_df,
        "par": par_df,
        "cutlines": cutlines_df,
    }


def run_phase1_all_seasons(
    historical_points: pd.DataFrame,
    projections: pd.DataFrame | None,
    adp_rankings: pd.DataFrame | None,
    config: dict[str, Any],
    seasons: list[int] | None = None,
) -> dict[str, pd.DataFrame]:
    """Run Phase 1 for multiple seasons and concatenate results.

    Parameters
    ----------
    historical_points:
        Multi-season historical weekly points.
    projections:
        Multi-season weekly projections (may be ``None``).
    adp_rankings:
        Multi-season preseason redraft rankings (may be ``None``).
    config:
        League config dict.
    seasons:
        Explicit list of seasons to process. Defaults to all seasons
        present in *historical_points*.

    Returns
    -------
    dict with the same keys as ``run_phase1_season``, each value being
    the concatenated DataFrame across all requested seasons.
    """
    if seasons is None:
        seasons = sorted(historical_points["season"].unique())

    all_results: dict[str, list[pd.DataFrame]] = {
        "started_weekly": [],
        "sav": [],
        "rsv_ld": [],
        "cg": [],
        "par": [],
        "cutlines": [],
    }

    for season in seasons:
        season_pts = historical_points[historical_points["season"] == season]
        if season_pts.empty:
            continue

        season_proj = None
        if projections is not None:
            sp = projections[projections["season"] == season]
            if not sp.empty:
                season_proj = sp

        season_adp = None
        if adp_rankings is not None:
            sa = adp_rankings[adp_rankings["season"] == season]
            if not sa.empty:
                season_adp = sa

        result = run_phase1_season(season_pts, season_proj, season_adp, config)
        for key in all_results:
            all_results[key].append(result[key])

    return {
        key: pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        for key, frames in all_results.items()
    }
