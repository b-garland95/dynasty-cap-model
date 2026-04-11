from __future__ import annotations

import math
from typing import Any, Protocol

import pandas as pd

from src.valuation.market_salary import compute_market_salary
from src.valuation.phase1_projected import (
    assign_projected_leaguewide_starting_set,
    compute_projected_raw_cutlines,
)
from src.valuation.roster_probability import compute_roster_probabilities


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


class _ProjectedStartModelMixin:
    _FALLBACK_SLOT: dict[str, str] = {
        "QB": "SF",
        "RB": "FLEX",
        "WR": "FLEX",
        "TE": "FLEX",
    }

    def _init_start_model(self, proj_df: pd.DataFrame, config: dict[str, Any]) -> None:
        self._config = config
        self._proj_cutlines: dict[tuple[int, int], dict[str, float]] = {}
        assignment_frames: list[pd.DataFrame] = []

        for (season, week), week_df in proj_df.groupby(["season", "week"]):
            key = (int(season), int(week))
            self._proj_cutlines[key] = compute_projected_raw_cutlines(week_df, config)
            assignment_frames.append(assign_projected_leaguewide_starting_set(week_df, config))

        self._id_col = "gsis_id" if "gsis_id" in proj_df.columns else "player"
        self._proj_assignments = (
            pd.concat(assignment_frames, ignore_index=True)
            if assignment_frames
            else pd.DataFrame(
                columns=["season", "week", self._id_col, "proj_points", "proj_assigned_slot"]
            )
        )
        self._proj_points_all: dict[tuple[int, int, str], float] = {
            (int(r[0]), int(r[1]), str(r[2])): float(r[3])
            for r in proj_df[["season", "week", self._id_col, "proj_points"]].itertuples(index=False)
        }

    def start_prob(self, df: pd.DataFrame) -> pd.Series:
        """Compute start probability σ from projected slot margin vs cutline."""
        tau_by_slot: dict[str, float] = self._config["capture_model"]["tau_by_slot"]
        id_col = self._id_col

        working = df[["season", "week", id_col, "position"]].copy().reset_index(drop=True)
        working = working.merge(
            self._proj_assignments[["season", "week", id_col, "proj_assigned_slot", "proj_points"]],
            on=["season", "week", id_col],
            how="left",
        )

        in_proj_set = working["proj_assigned_slot"].notna()
        working["slot_hat"] = working["proj_assigned_slot"].where(
            in_proj_set,
            working["position"].map(self._FALLBACK_SLOT),
        )

        missing_pts = working["proj_points"].isna()
        if missing_pts.any():
            working.loc[missing_pts, "proj_points"] = working.loc[missing_pts].apply(
                lambda row: self._proj_points_all.get(
                    (int(row["season"]), int(row["week"]), str(row[id_col]))
                ),
                axis=1,
            )

        working["cutline"] = working.apply(
            lambda row: float(
                self._proj_cutlines.get((int(row["season"]), int(row["week"])), {}).get(
                    row["slot_hat"],
                    0.0,
                )
            ),
            axis=1,
        )
        working["m_hat"] = working["proj_points"].fillna(0.0) - working["cutline"]
        working["tau"] = working["slot_hat"].map(tau_by_slot).fillna(2.5)

        alpha = self._config["capture_model"].get("tau_margin_scaling", 0.0)
        tau_effective = working["tau"] / (1.0 + alpha * working["m_hat"].abs())
        exponent = -(working["m_hat"] / tau_effective).clip(-500.0, 500.0)
        sigma = 1.0 / (1.0 + exponent.apply(math.exp))
        return sigma.clip(0.0, 1.0).set_axis(df.index)


class RationalStartCaptureModel(_ProjectedStartModelMixin):
    """Milestone 4b.1 model: projected start probability with perfect rostering."""

    def __init__(self, proj_df: pd.DataFrame, config: dict[str, Any]) -> None:
        self._init_start_model(proj_df=proj_df, config=config)

    def roster_prob(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype=float)


class RationalCaptureModel(_ProjectedStartModelMixin):
    """Milestone 4b.2 model: roster probability ρ and start probability σ."""

    def __init__(self, proj_df: pd.DataFrame, adp_df: pd.DataFrame, config: dict[str, Any]) -> None:
        self._init_start_model(proj_df=proj_df, config=config)
        adp_salary_df = compute_market_salary(adp_df, config)
        self._rho_table = compute_roster_probabilities(proj_df, adp_salary_df, config)

    def roster_prob(self, df: pd.DataFrame) -> pd.Series:
        id_col = self._id_col
        if self._rho_table.empty:
            return pd.Series(0.0, index=df.index, dtype=float)

        lookup_cols = ["season", "week", id_col, "rho"]
        merged = df[["season", "week", id_col]].copy().reset_index(drop=True).merge(
            self._rho_table[lookup_cols],
            on=["season", "week", id_col],
            how="left",
        )
        return merged["rho"].fillna(0.0).clip(0.0, 1.0).set_axis(df.index)
