from __future__ import annotations

from typing import Any

import pandas as pd


def compute_market_salary(adp_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Attach a cap-scaled market salary proxy to preseason ADP rows.

    The proxy uses within-season ADP rank as market demand and scales the
    resulting salary curve into a realistic cap environment using config only.
    """
    if adp_df.empty:
        return adp_df.copy()

    roster_model = config["capture_model"]["roster_model"]
    teams = int(config["league"]["teams"])
    active_spots = int(roster_model["active_roster_spots_per_team"])
    beta = float(roster_model["salary_beta"])
    cap_scale = float(roster_model["cap_scale"])
    top_k = teams * active_spots

    id_cols = [col for col in ("gsis_id", "player") if col in adp_df.columns]
    sort_cols = ["season", "rank", *id_cols]

    salary_df = adp_df.copy().sort_values(sort_cols).reset_index(drop=True)
    salary_df["adp_rank_within_season"] = salary_df.groupby("season").cumcount() + 1
    salary_df["s_raw"] = (1.0 / salary_df["adp_rank_within_season"].astype(float)) ** beta

    season_alpha: dict[int, float] = {}
    for season, group in salary_df.groupby("season", sort=False):
        denom = float(group["s_raw"].head(top_k).sum())
        season_alpha[int(season)] = 0.0 if denom <= 0.0 else (teams * cap_scale) / denom

    salary_df["market_salary"] = salary_df["season"].map(season_alpha).astype(float) * salary_df["s_raw"]
    return salary_df.drop(columns=["s_raw"]).reset_index(drop=True)
