from __future__ import annotations

import numpy as np
import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger
from src.ingest.player_ids import normalize_name
from src.modeling.age_curve import get_age_multiplier, load_age_curves
from src.modeling.dynasty_calibration import (
    build_dynasty_training_data,
    compute_positional_rank,
    fit_dynasty_calibration,
    predict_dynasty_ceiling,
)
from src.modeling.isotonic import fit_calibration, predict
from src.utils.config import load_league_config


def build_phase2_tv_inputs(
    roster_csv_path: str,
    training_df: pd.DataFrame,
    redraft_rankings_df: pd.DataFrame,
    *,
    target_season: int = 2026,
) -> pd.DataFrame:
    """Build Phase 3 TV inputs by scoring target-season ranks through Phase 2."""
    ledger_df = build_contract_ledger(roster_csv_path)
    return build_phase2_tv_inputs_from_frames(
        ledger_df,
        training_df,
        redraft_rankings_df,
        target_season=target_season,
    )


def build_phase2_tv_inputs_from_frames(
    ledger_df: pd.DataFrame,
    training_df: pd.DataFrame,
    redraft_rankings_df: pd.DataFrame,
    *,
    target_season: int = 2026,
) -> pd.DataFrame:
    """Score the full target-season player universe into a flat 4-year TV path."""
    required_training = {"season", "position", "log_adp", "esv"}
    missing_training = sorted(required_training - set(training_df.columns))
    if missing_training:
        raise ValueError(f"Training data missing required columns: {missing_training}")

    required_rankings = {"season", "rank", "player", "position"}
    missing_rankings = sorted(required_rankings - set(redraft_rankings_df.columns))
    if missing_rankings:
        raise ValueError(f"Redraft rankings missing required columns: {missing_rankings}")

    target_rankings = redraft_rankings_df.loc[redraft_rankings_df["season"] == target_season].copy()
    if target_rankings.empty:
        raise ValueError(f"No redraft rankings found for target season {target_season}")

    target_rankings["merge_name"] = target_rankings["player"].map(normalize_name)
    target_rankings["position"] = target_rankings["position"].astype(str).str.upper()
    target_rankings["adp"] = pd.to_numeric(target_rankings["rank"], errors="raise").astype(int)
    target_rankings["log_adp"] = np.log(target_rankings["adp"])

    dupes = target_rankings.duplicated(subset=["merge_name", "position"], keep=False)
    if dupes.any():
        duplicate_keys = (
            target_rankings.loc[dupes, ["merge_name", "position"]]
            .drop_duplicates()
            .to_dict(orient="records")
        )
        raise ValueError(f"Target-season rankings contain duplicate merge_name/position keys: {duplicate_keys}")

    calibrations = fit_calibration(training_df.copy())
    scored = predict(
        calibrations,
        target_rankings[["season", "player", "team", "position", "merge_name", "adp", "log_adp"]],
    ).rename(columns={"player": "rankings_player", "team": "nfl_team"})

    # Carry ranking_source through if present (set by build_master_redraft_adp_with_fallback)
    has_ranking_source = "ranking_source" in target_rankings.columns
    if has_ranking_source:
        source_lookup = target_rankings[["merge_name", "position", "ranking_source"]].copy()
        scored = scored.merge(source_lookup, on=["merge_name", "position"], how="left")

    roster = ledger_df.copy()
    roster["merge_name"] = roster["player"].map(normalize_name)
    roster["position"] = roster["position"].astype(str).str.upper()
    roster = roster.rename(
        columns={
            "player": "roster_player",
            "team": "fantasy_team",
        }
    )

    merged = scored.merge(
        roster[["merge_name", "position", "roster_player", "fantasy_team"]],
        on=["merge_name", "position"],
        how="left",
    )

    merged["player"] = merged["roster_player"].fillna(merged["rankings_player"])
    merged["team"] = merged["fantasy_team"].fillna("")
    merged["tv_y0"] = merged["esv_hat"].fillna(0.0).astype(float)
    for col in ["tv_y1", "tv_y2", "tv_y3"]:
        merged[col] = merged["tv_y0"]

    # Build tv_input_source; use ranking_source-aware labels when available
    if has_ranking_source:
        _source_labels = {
            "fantasydata_adp": f"phase2_{target_season}_adp",
            "fantasypros_rankings": f"phase2_{target_season}_rankings_fallback",
        }
        matched_label = merged["ranking_source"].map(_source_labels).fillna(
            f"phase2_{target_season}_redraft_flat_path"
        )
        merged["tv_input_source"] = np.where(
            merged["esv_hat"].isna(), "unranked_zero", matched_label
        )
    else:
        merged["tv_input_source"] = np.where(
            merged["esv_hat"].notna(),
            f"phase2_{target_season}_redraft_flat_path",
            "unranked_zero",
        )

    merged["matched_rankings"] = merged["esv_hat"].notna()
    merged["is_rostered"] = merged["fantasy_team"].notna()

    output_cols = [
        "player",
        "team",
        "position",
        "tv_y0",
        "tv_y1",
        "tv_y2",
        "tv_y3",
        "adp",
        "esv_hat",
        "esv_p25",
        "esv_p50",
        "esv_p75",
        "rankings_player",
        "nfl_team",
        "matched_rankings",
        "is_rostered",
        "tv_input_source",
    ]
    if has_ranking_source:
        output_cols.append("ranking_source")

    return merged[output_cols].sort_values(
        ["is_rostered", "team", "position", "player"], ascending=[False, True, True, True]
    ).reset_index(drop=True)


def apply_dynasty_tv_path(
    tv_df: pd.DataFrame,
    dynasty_rankings_df: pd.DataFrame,
    training_df: pd.DataFrame,
    *,
    target_season: int = 2026,
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
