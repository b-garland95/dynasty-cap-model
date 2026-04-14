from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


CANONICAL_COLUMNS: list[str] = [
    "season",
    "week",
    "player_id",
    "player",
    "position",
    "team",
    "opponent",
    "points",
    "games_played",
    "season_type",
    "source",
    "loaded_at",
]



def load_historical_weekly_points(
    start_season: int,
    end_season: int,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Load and normalize historical weekly player fantasy points from nflreadpy."""
    try:
        import nflreadpy as nfl  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local install
        raise ModuleNotFoundError(
            "nflreadpy is required for direct historical weekly point ingestion."
        ) from exc

    seasons = list(range(int(start_season), int(end_season) + 1))
    raw_df = nfl.load_player_stats(seasons=seasons, summary_level="week")
    if hasattr(raw_df, "to_pandas"):
        raw_df = raw_df.to_pandas()

    return normalize_historical_weekly_points(
        raw_df=raw_df,
        config=config,
        start_season=start_season,
        end_season=end_season,
        loaded_at=datetime.now(timezone.utc).isoformat(),
        source="nflreadpy.load_player_stats",
    )



def normalize_historical_weekly_points(
    raw_df: pd.DataFrame,
    config: dict[str, Any],
    start_season: int,
    end_season: int,
    loaded_at: str,
    source: str = "nflverse.player_stats",
    include_playoffs: bool = False,
) -> pd.DataFrame:
    """Normalize nflverse player stats into the model's canonical weekly points schema.

    Parameters
    ----------
    include_playoffs:
        When ``False`` (default), only regular-season weeks (``season_type == "REG"``)
        are included. This is controlled by ``valuation.include_playoffs`` in
        ``league_config.yaml`` (default ``False``). Dynasty league value is based on
        regular-season performance; playoff weeks are excluded by default to keep
        the replacement-level calculation stable across teams.
    """
    player_col = _first_present(raw_df, ["player_display_name", "player_name", "player"])
    position_col = _first_present(raw_df, ["position", "position_group"])
    team_col = _first_present(raw_df, ["recent_team", "team"])
    opponent_col = _first_present(raw_df, ["opponent_team", "opponent"])

    required = ["season", "week", "player_id", "season_type", "fantasy_points", "receptions"]
    missing = [column for column in required if column not in raw_df.columns]
    if missing:
        raise ValueError(f"Missing required nflverse player stats columns: {missing}")

    positions = get_config_player_positions(config)
    normalized = raw_df.copy()
    season_type_filter = (
        normalized["season_type"].notna()  # keep all weeks
        if include_playoffs
        else normalized["season_type"].eq("REG")
    )
    normalized = normalized.loc[
        normalized["season"].between(int(start_season), int(end_season))
        & normalized[position_col].isin(positions)
        & season_type_filter
    ].copy()

    normalized["player"] = normalized[player_col].fillna("")
    normalized["position"] = normalized[position_col]
    normalized["team"] = normalized[team_col] if team_col in normalized.columns else pd.NA
    normalized["opponent"] = normalized[opponent_col] if opponent_col in normalized.columns else pd.NA
    normalized["points"] = compute_weekly_fantasy_points(normalized, config)
    normalized["games_played"] = 1
    normalized["season_type"] = normalized["season_type"]
    normalized["source"] = source
    normalized["loaded_at"] = loaded_at

    result = normalized[CANONICAL_COLUMNS].copy()
    result["season"] = result["season"].astype(int)
    result["week"] = result["week"].astype(int)
    result["points"] = result["points"].astype(float)
    result["games_played"] = result["games_played"].astype(int)
    return result.reset_index(drop=True)



def normalize_historical_weekly_points_csv(
    raw_csv_path: str,
    config: dict[str, Any],
    start_season: int,
    end_season: int,
    output_path: str | None = None,
    source: str = "nflreadr.load_player_stats",
) -> pd.DataFrame:
    """Normalize a raw nflverse weekly player stats CSV exported outside Python."""
    raw_df = pd.read_csv(raw_csv_path)
    normalized_df = normalize_historical_weekly_points(
        raw_df=raw_df,
        config=config,
        start_season=start_season,
        end_season=end_season,
        loaded_at=datetime.now(timezone.utc).isoformat(),
        source=source,
    )

    if output_path is not None:
        output_obj = Path(output_path)
        output_obj.parent.mkdir(parents=True, exist_ok=True)
        normalized_df.to_csv(output_obj, index=False)

    return normalized_df



def export_historical_weekly_points(
    start_season: int,
    end_season: int,
    config: dict[str, Any],
    output_path: str,
) -> pd.DataFrame:
    """Load, normalize, and export historical weekly points to CSV."""
    weekly_df = load_historical_weekly_points(start_season, end_season, config)
    path_obj = Path(output_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    weekly_df.to_csv(path_obj, index=False)
    return weekly_df



def get_config_player_positions(config: dict[str, Any]) -> list[str]:
    """Return allowed player positions from config."""
    positions = config.get("player_positions")
    if not isinstance(positions, list) or not positions:
        raise ValueError("Config must define non-empty player_positions")
    return [str(position).upper() for position in positions]



def compute_weekly_fantasy_points(raw_df: pd.DataFrame, config: dict[str, Any]) -> pd.Series:
    """Compute weekly fantasy points from nflverse stats using league scoring config.

    nflverse ``fantasy_points`` column = standard scoring: 6 pts/passing TD,
    4 pts/rushing-or-receiving TD, 0.1 pts/passing yard, 0.1 pts/rushing-or-receiving yard.
    Half-PPR scoring adds 0.5 * receptions additively on top of the base column.
    This is the correct interpretation of the nflverse ``fantasy_points`` base column.
    """
    if bool(config["league"]["scoring"].get("half_ppr", False)):
        return raw_df["fantasy_points"].astype(float) + 0.5 * raw_df["receptions"].astype(float)
    return raw_df["fantasy_points"].astype(float)



def _first_present(df: pd.DataFrame, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    raise ValueError(f"Missing expected columns from candidates: {candidates}")
