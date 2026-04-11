from __future__ import annotations

import numpy as np
import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger
from src.ingest.player_ids import normalize_name
from src.modeling.isotonic import fit_calibration, predict


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
    required_training = {"season", "position", "log_adp", "rsv"}
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
    merged["tv_y0"] = merged["rsv_hat"].fillna(0.0).astype(float)
    for col in ["tv_y1", "tv_y2", "tv_y3"]:
        merged[col] = merged["tv_y0"]
    merged["tv_input_source"] = np.where(
        merged["rsv_hat"].notna(),
        "phase2_2026_redraft_flat_path",
        "unranked_zero",
    )
    merged["matched_2026_rankings"] = merged["rsv_hat"].notna()
    merged["is_rostered"] = merged["fantasy_team"].notna()

    return merged[
        [
            "player",
            "team",
            "position",
            "tv_y0",
            "tv_y1",
            "tv_y2",
            "tv_y3",
            "adp",
            "rsv_hat",
            "rsv_p25",
            "rsv_p50",
            "rsv_p75",
            "rankings_player",
            "nfl_team",
            "matched_2026_rankings",
            "is_rostered",
            "tv_input_source",
        ]
    ].sort_values(["is_rostered", "team", "position", "player"], ascending=[False, True, True, True]).reset_index(drop=True)
