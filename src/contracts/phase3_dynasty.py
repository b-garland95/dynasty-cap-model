"""Phase 3 dynasty trajectory: replace flat tv_y1–tv_y3 with age-curve + delta paths.

This module consumes the flat TV path produced by ``src.modeling.phase2_tv_scorer``
and enriches years 1–3 using dynasty positional rank calibration, position-specific
age curves, and a redraft-vs-dynasty delta correction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.ingest.player_ids import normalize_name
from src.modeling.age_curve import get_age_multiplier, load_age_curves
from src.modeling.dynasty_calibration import (
    build_dynasty_training_data,
    compute_positional_rank,
    fit_dynasty_calibration,
    predict_dynasty_ceiling,
)
from src.utils.config import load_league_config


def apply_dynasty_tv_path(
    tv_df: pd.DataFrame,
    dynasty_rankings_df: pd.DataFrame,
    training_df: pd.DataFrame,
    *,
    target_season: int,
    config: dict | None = None,
) -> pd.DataFrame:
    """Replace flat tv_y1–tv_y3 values with a dynasty-calibrated trajectory.

    Trajectory formula for year offset k (1–3)::

        tv_yk = esv_dynasty_ceiling
                * age_curve_multiplier(position, current_age, k)
                * delta_correction(delta, k)

    where:

    - ``esv_dynasty_ceiling`` is scored from the player's dynasty positional
      rank (rank within position/season); safe for non-SF dynasty ADP.
    - ``age_curve_multiplier`` rises toward 1.0 at the position's peak age then
      declines, giving developing players an upward slope and aging players a
      downward slope.
    - ``delta_correction`` nudges the trajectory based on
      ``delta = redraft_pos_rank − dynasty_pos_rank``:
      a positive delta (developing player ranked lower in redraft than dynasty
      expects) boosts future years; a negative delta (ageing star) pulls them down.

    Per-year uncertainty bands (``esv_p25_y1``, ``esv_p75_y1``, …) are derived
    from the dynasty calibration's residual quantiles, expanded with each year
    offset and made asymmetric by the delta signal (developing players get extra
    upside width; declining players get extra downside width).

    .. note::
        The delta signal (redraft_pos_rank − dynasty_pos_rank) is a ranking
        signal only — it has not been backtested against actual multi-year ESV
        outcomes.  Players with a large positive delta may have one simply
        because of dynasty ranking noise rather than genuine breakout potential.
        See TODO: add delta-predictiveness backtest in run_dynasty_backtest.py.

    Players without a dynasty ADP match keep their existing flat tv_y1–tv_y3 and
    receive ``dynasty_tv_applied = False``.  If *tv_df* lacks an ``age`` column,
    age-curve multipliers default to 1.0.

    Parameters
    ----------
    tv_df:
        Output of ``build_phase2_tv_inputs_from_frames()``; must have at least
        ``player``, ``position``, ``tv_y0``, ``adp`` columns.
    dynasty_rankings_df:
        Multi-season dynasty rankings with columns ``season``, ``rank``,
        ``player``, ``position``, ``gsis_id``.  Used for calibration (all
        historical seasons) and target-season scoring.
    training_df:
        Phase 2 training dataset (``season``, ``gsis_id``, ``player``,
        ``position``, ``esv``, …) providing historical ESV for calibration.
    target_season:
        The contract base year (e.g. 2026).
    config:
        Loaded ``league_config.yaml`` dict.  If ``None``, loaded from the
        default path.

    Returns
    -------
    Copy of *tv_df* with:
    - ``tv_y1``, ``tv_y2``, ``tv_y3`` replaced by dynasty trajectory values
      (where a dynasty match exists).
    - New columns ``esv_p25_y1``, ``esv_p75_y1``, ``esv_p25_y2``,
      ``esv_p75_y2``, ``esv_p25_y3``, ``esv_p75_y3``.
    - New columns ``esv_dynasty_ceiling``, ``dynasty_pos_rank``,
      ``redraft_pos_rank``, ``dynasty_delta``.
    - Boolean column ``dynasty_tv_applied``.
    """
    if config is None:
        config = load_league_config()

    age_curves = load_age_curves(config)
    delta_alpha = float(config.get("dynasty_delta_alpha", 0.05))
    band_expansion = float(config.get("dynasty_band_expansion", 0.40))

    # ------------------------------------------------------------------
    # 1. Fit dynasty calibration from historical data
    # ------------------------------------------------------------------
    dynasty_train = build_dynasty_training_data(training_df, dynasty_rankings_df)
    if dynasty_train.empty:
        raise ValueError(
            "No dynasty training data built — check that dynasty_rankings_df "
            "has 'gsis_id' values that match training_df."
        )
    dynasty_cals = fit_dynasty_calibration(dynasty_train)

    # ------------------------------------------------------------------
    # 2. Score target-season dynasty positional ranks
    # ------------------------------------------------------------------
    target_dynasty = dynasty_rankings_df.loc[
        dynasty_rankings_df["season"] == target_season
    ].copy()
    if target_dynasty.empty:
        raise ValueError(
            f"No dynasty rankings found for target season {target_season}."
        )

    target_dynasty = compute_positional_rank(target_dynasty)
    target_dynasty["log_adp"] = np.log(target_dynasty["dynasty_pos_rank"])
    target_dynasty["merge_name"] = target_dynasty["player"].map(normalize_name)
    target_dynasty["position"] = target_dynasty["position"].str.upper()

    scored_dynasty = predict_dynasty_ceiling(
        dynasty_cals,
        target_dynasty[["position", "log_adp", "merge_name", "dynasty_pos_rank"]],
    ).rename(columns={
        "esv_hat": "esv_dynasty_ceiling",
        "esv_p25": "_dynasty_p25",
        "esv_p50": "_dynasty_p50",
        "esv_p75": "_dynasty_p75",
    })

    # ------------------------------------------------------------------
    # 3. Compute redraft positional rank from tv_df
    # ------------------------------------------------------------------
    out = tv_df.copy()
    out["_merge_name"] = out["player"].map(normalize_name)

    redraft_pos_ranks = (
        out.loc[out["adp"].notna()]
        .groupby("position")["adp"]
        .rank(method="first", ascending=True)
        .astype(int)
    )
    out["redraft_pos_rank"] = redraft_pos_ranks

    # ------------------------------------------------------------------
    # 4. Merge dynasty ceiling data into tv_df
    # ------------------------------------------------------------------
    dynasty_lookup = scored_dynasty[
        ["merge_name", "position", "esv_dynasty_ceiling",
         "_dynasty_p25", "_dynasty_p75", "dynasty_pos_rank"]
    ].drop_duplicates(subset=["merge_name", "position"])

    out = out.merge(dynasty_lookup, left_on=["_merge_name", "position"],
                    right_on=["merge_name", "position"], how="left",
                    suffixes=("", "_dynasty"))
    out = out.drop(columns=["merge_name_dynasty"], errors="ignore")

    # ------------------------------------------------------------------
    # 5. Compute delta = redraft_pos_rank - dynasty_pos_rank
    # ------------------------------------------------------------------
    out["dynasty_delta"] = out["redraft_pos_rank"] - out["dynasty_pos_rank"]

    # Position-level counts for delta normalization
    n_pos_map: dict[str, int] = (
        target_dynasty.groupby("position")["dynasty_pos_rank"].max().to_dict()
    )

    # ------------------------------------------------------------------
    # 6. Compute dynasty trajectory for Y1–Y3
    # ------------------------------------------------------------------
    has_age = "age" in out.columns
    dynasty_matched = out["esv_dynasty_ceiling"].notna()

    for k in (1, 2, 3):
        # Age-curve multiplier (vectorised via apply; small dataframes)
        if has_age:
            age_mult = out.apply(
                lambda row, _k=k: get_age_multiplier(
                    age_curves.get(row["position"],
                                   age_curves.get("WR")),  # type: ignore[arg-type]
                    float(row["age"]) if pd.notna(row.get("age")) else float("nan"),
                    _k,
                ),
                axis=1,
            )
        else:
            age_mult = pd.Series(1.0, index=out.index)

        # Delta correction
        n_pos_series = out["position"].map(n_pos_map).fillna(24).astype(float)
        norm_delta = (out["dynasty_delta"].fillna(0.0) / n_pos_series).clip(-1.0, 1.0)
        delta_correction = 1.0 + delta_alpha * norm_delta * k

        # Point estimate: ceiling * age_curve * delta_correction
        ceiling = out["esv_dynasty_ceiling"].fillna(out["tv_y0"])
        tv_yk = (ceiling * age_mult * delta_correction).clip(lower=0.0)

        # Preserve flat path for unmatched players
        out[f"tv_y{k}"] = np.where(dynasty_matched, tv_yk, out[f"tv_y{k}"])

        # ------------------------------------------------------------------
        # 7. Per-year uncertainty bands (asymmetric)
        # ------------------------------------------------------------------
        expand = 1.0 + band_expansion * k

        # Dynasty half-widths (from residual quantiles at the ceiling score)
        dynasty_hat = out["esv_dynasty_ceiling"].fillna(out["tv_y0"])
        hw_lower = (dynasty_hat - out["_dynasty_p25"].fillna(dynasty_hat)).clip(lower=0.0)
        hw_upper = (out["_dynasty_p75"].fillna(dynasty_hat) - dynasty_hat).clip(lower=0.0)

        # Asymmetric boost: positive delta → extra upside; negative → extra downside
        upside_extra = (norm_delta.clip(lower=0.0) * delta_alpha * k).fillna(0.0)
        downside_extra = ((-norm_delta).clip(lower=0.0) * delta_alpha * k).fillna(0.0)

        p25_yk = (out[f"tv_y{k}"] - hw_lower * expand * (1.0 + downside_extra)).clip(lower=0.0)
        p75_yk = out[f"tv_y{k}"] + hw_upper * expand * (1.0 + upside_extra)

        out[f"esv_p25_y{k}"] = np.where(dynasty_matched, p25_yk, np.nan)
        out[f"esv_p75_y{k}"] = np.where(dynasty_matched, p75_yk, np.nan)

    out["dynasty_tv_applied"] = dynasty_matched

    # Drop working columns
    out = out.drop(columns=["_merge_name", "_dynasty_p25", "_dynasty_p50",
                             "_dynasty_p75"], errors="ignore")

    return out.reset_index(drop=True)
