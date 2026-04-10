from __future__ import annotations

import math
from typing import Any, Protocol

import pandas as pd

from src.valuation.phase1_projected import (
    assign_projected_leaguewide_starting_set,
    compute_projected_raw_cutlines,
)


class CaptureModel(Protocol):
    """Protocol for roster/start capture probabilities."""

    def roster_prob(self, df: pd.DataFrame) -> pd.Series: ...

    def start_prob(self, df: pd.DataFrame) -> pd.Series: ...


class PerfectCaptureModel:
    """Capture model scaffold that assumes perfect roster and start capture."""

    def roster_prob(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype=float)

    def start_prob(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype=float)


class RationalStartCaptureModel:
    """Capture model that derives start probability σ from weekly projections.

    Roster probability ρ is fixed at 1.0 in milestone 4b.1.

    σ is computed as a sigmoid over the player's projected margin vs the
    projected slot cutline, using slot-specific decision noise τ from config:

        σ = 1 / (1 + exp(-m_hat / τ))

    Players not in the projected starting set use a conservative fallback slot
    (FLEX for RB/WR/TE, SF for QB) to compute their margin.

    The input df passed to start_prob must contain columns:
        season, week, gsis_id, position
    (i.e. the started_weekly_df must carry season, week, and gsis_id).
    """

    _FALLBACK_SLOT: dict[str, str] = {
        "QB": "SF",
        "RB": "FLEX",
        "WR": "FLEX",
        "TE": "FLEX",
    }

    def __init__(self, proj_df: pd.DataFrame, config: dict[str, Any]) -> None:
        """
        Args:
            proj_df: Weekly projections for a season with columns:
                season, week, player, position, proj_points.
            config: League config dict (must include capture_model.tau_by_slot).
        """
        self._config = config
        self._proj_cutlines: dict[tuple[int, int], dict[str, float]] = {}
        assignment_frames: list[pd.DataFrame] = []

        for (season, week), week_df in proj_df.groupby(["season", "week"]):
            key = (int(season), int(week))
            self._proj_cutlines[key] = compute_projected_raw_cutlines(week_df, config)
            assignment_frames.append(assign_projected_leaguewide_starting_set(week_df, config))

        self._proj_assignments: pd.DataFrame = (
            pd.concat(assignment_frames, ignore_index=True)
            if assignment_frames
            else pd.DataFrame(
                columns=["season", "week", "gsis_id", "proj_points", "proj_assigned_slot"]
            )
        )

        # Detect whether input uses gsis_id or player as the identity key.
        self._id_col: str = "gsis_id" if "gsis_id" in proj_df.columns else "player"

        # Full proj_points lookup for every player (including non-projected starters).
        self._proj_points_all: dict[tuple[int, int, str], float] = {
            (int(r[0]), int(r[1]), str(r[2])): float(r[3])
            for r in proj_df[["season", "week", self._id_col, "proj_points"]].itertuples(index=False)
        }

    def roster_prob(self, df: pd.DataFrame) -> pd.Series:
        """Return ρ = 1.0 for all rows (roster probability not yet modelled)."""
        return pd.Series(1.0, index=df.index, dtype=float)

    def start_prob(self, df: pd.DataFrame) -> pd.Series:
        """Compute start probability σ for each actual-started row in df.

        Steps:
        1. Look up player's projected slot and proj_points from the projected
           leaguewide starting set for that (season, week).
        2. Players absent from the projected set fall back to FLEX (RB/WR/TE)
           or SF (QB) and use their raw proj_points as the margin baseline.
        3. σ = sigmoid(m_hat / τ) where m_hat = proj_points − projected_cutline
           and τ is the slot-specific decision noise from config.
        """
        tau_by_slot: dict[str, float] = self._config["capture_model"]["tau_by_slot"]

        id_col = self._id_col

        # Reset to positional index so the merge never scrambles row order.
        working = df[["season", "week", id_col, "position"]].copy().reset_index(drop=True)

        # Bring in projected slot and proj_points for players in the projected starting set.
        working = working.merge(
            self._proj_assignments[["season", "week", id_col, "proj_assigned_slot", "proj_points"]],
            on=["season", "week", id_col],
            how="left",
        )

        # Effective slot: projected slot for projected starters, fallback otherwise.
        in_proj_set = working["proj_assigned_slot"].notna()
        working["slot_hat"] = working["proj_assigned_slot"].where(
            in_proj_set,
            working["position"].map(self._FALLBACK_SLOT),
        )

        # Fill proj_points for players not in the projected starting set.
        missing_pts = working["proj_points"].isna()
        if missing_pts.any():
            working.loc[missing_pts, "proj_points"] = working.loc[missing_pts].apply(
                lambda r: self._proj_points_all.get(
                    (int(r["season"]), int(r["week"]), str(r[id_col]))
                ),
                axis=1,
            )

        # Projected cutline for each row's (season, week) and slot_hat.
        def _cutline(row: pd.Series) -> float:
            cutlines = self._proj_cutlines.get((int(row["season"]), int(row["week"])), {})
            return float(cutlines.get(row["slot_hat"], 0.0))

        working["cutline"] = working.apply(_cutline, axis=1)
        working["m_hat"] = working["proj_points"].fillna(0.0) - working["cutline"]
        working["tau"] = working["slot_hat"].map(tau_by_slot).fillna(2.5)

        # Variable τ: shrink τ as |margin| grows so obvious decisions → σ ≈ 0 or 1.
        alpha = self._config["capture_model"].get("tau_margin_scaling", 0.0)
        tau_effective = working["tau"] / (1.0 + alpha * working["m_hat"].abs())

        # σ = 1 / (1 + exp(-m/τ_eff)); clip exponent to avoid float overflow.
        exponent = -(working["m_hat"] / tau_effective).clip(-500.0, 500.0)
        sigma = 1.0 / (1.0 + exponent.apply(math.exp))

        return sigma.clip(0.0, 1.0).set_axis(df.index)
