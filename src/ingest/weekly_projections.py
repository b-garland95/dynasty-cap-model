from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.ingest.historical_weekly_points import get_config_player_positions


CANONICAL_PROJECTION_COLUMNS: list[str] = [
    "season",
    "week",
    "player_id",
    "player",
    "team",
    "position",
    "opponent",
    "projected_points",
    "source",
    "loaded_at",
]
PROJECTION_KEY_COLUMNS: list[str] = ["season", "week", "player_id"]



def detect_projection_schema(raw_df: pd.DataFrame) -> str:
    """Detect supported FantasyData weekly projections schema variants."""
    columns = set(raw_df.columns)
    legacy_required = {
        "PlayerID",
        "Name",
        "Team",
        "Position",
        "Opponent",
        "Year",
        "Week",
        "FantasyPointsHalfPointPpr",
    }
    current_required = {
        "id",
        "player",
        "team",
        "pos",
        "game.week",
        "opp",
        "fpts_half_ppr",
    }

    if legacy_required.issubset(columns):
        return "legacy"
    if current_required.issubset(columns):
        return "current"
    raise ValueError("Unrecognized FantasyData weekly projections schema")



def normalize_weekly_projections(
    raw_df: pd.DataFrame,
    config: dict[str, Any],
    loaded_at: str,
    season: int | None = None,
    source: str = "fantasydata.weekly_projections",
    validate_keys: bool = True,
) -> pd.DataFrame:
    """Normalize FantasyData weekly projections exports into one canonical schema."""
    schema_variant = detect_projection_schema(raw_df)
    positions = get_config_player_positions(config)

    if schema_variant == "legacy":
        normalized = raw_df.rename(
            columns={
                "PlayerID": "player_id",
                "Name": "player",
                "Team": "team",
                "Position": "position",
                "Opponent": "opponent",
                "Year": "season",
                "Week": "week",
                "FantasyPointsHalfPointPpr": "projected_points",
            }
        ).copy()
    else:
        if season is None:
            raise ValueError("season is required when normalizing the new FantasyData weekly projections schema")
        normalized = raw_df.rename(
            columns={
                "id": "player_id",
                "player": "player",
                "team": "team",
                "pos": "position",
                "opp": "opponent",
                "game.week": "week",
                "fpts_half_ppr": "projected_points",
            }
        ).copy()
        normalized["season"] = int(season)

    normalized["position"] = normalized["position"].astype(str).str.upper()
    normalized = normalized.loc[normalized["position"].isin(positions)].copy()
    normalized["source"] = source
    normalized["loaded_at"] = loaded_at

    result = normalized[CANONICAL_PROJECTION_COLUMNS].copy()
    result["season"] = result["season"].astype(int)
    result["week"] = result["week"].astype(int)
    result["player_id"] = result["player_id"].astype(str)
    result["projected_points"] = result["projected_points"].astype(float)
    result = result.reset_index(drop=True)
    if validate_keys:
        validate_unique_projection_keys(result, context="normalized projections")
    return result



def normalize_weekly_projections_csv(
    raw_csv_path: str,
    config: dict[str, Any],
    output_path: str | None = None,
    season: int | None = None,
    source: str = "fantasydata.weekly_projections",
    validate_keys: bool = True,
) -> pd.DataFrame:
    """Normalize a raw weekly projections CSV and optionally write the result to disk."""
    raw_df = pd.read_csv(raw_csv_path)
    normalized_df = normalize_weekly_projections(
        raw_df=raw_df,
        config=config,
        loaded_at=datetime.now(timezone.utc).isoformat(),
        season=season,
        source=source,
        validate_keys=validate_keys,
    )

    if output_path is not None:
        output_obj = Path(output_path)
        output_obj.parent.mkdir(parents=True, exist_ok=True)
        normalized_df.to_csv(output_obj, index=False)

    return normalized_df



def combine_normalized_weekly_projections(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine normalized weekly projections and fail if projection keys overlap."""
    if not frames:
        return pd.DataFrame(columns=CANONICAL_PROJECTION_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    validate_unique_projection_keys(combined, context="combined projections")
    return combined.sort_values(PROJECTION_KEY_COLUMNS + ["position", "player"]).reset_index(drop=True)



def find_duplicate_projection_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return duplicate player-week projection rows sorted for reporting."""
    duplicated = df.duplicated(subset=PROJECTION_KEY_COLUMNS, keep=False)
    if not duplicated.any():
        return pd.DataFrame(columns=df.columns)

    return df.loc[duplicated].sort_values(PROJECTION_KEY_COLUMNS + ["team", "opponent", "player"]).reset_index(drop=True)



def resolve_projection_key_conflicts(df: pd.DataFrame) -> pd.DataFrame:
    """Resolve duplicate player-week keys by keeping the highest projection, then first row on ties."""
    if df.empty:
        return df.copy()

    ranked = df.reset_index(names="_input_order")
    ranked = ranked.sort_values(
        PROJECTION_KEY_COLUMNS + ["projected_points", "_input_order"],
        ascending=[True, True, True, False, True],
        kind="mergesort",
    )
    resolved = ranked.drop_duplicates(subset=PROJECTION_KEY_COLUMNS, keep="first")
    resolved = resolved.sort_values("_input_order", kind="mergesort").drop(columns=["_input_order"])
    return resolved.reset_index(drop=True)



def validate_unique_projection_keys(df: pd.DataFrame, context: str) -> None:
    """Raise if normalized weekly projections contain duplicate player-week rows."""
    duplicate_rows = find_duplicate_projection_rows(df)
    if duplicate_rows.empty:
        return

    sample = duplicate_rows[PROJECTION_KEY_COLUMNS].drop_duplicates().head(5).to_dict(orient="records")
    raise ValueError(
        f"Duplicate projection keys detected in {context} for columns {PROJECTION_KEY_COLUMNS}: {sample}"
    )



def normalize_weekly_projections_batch(
    raw_csv_paths: list[str],
    config: dict[str, Any],
    season: int | None = None,
    source: str = "fantasydata.weekly_projections",
) -> pd.DataFrame:
    """Normalize multiple weekly projections files and fail on overlapping player-week keys."""
    frames = [
        normalize_weekly_projections_csv(
            raw_csv_path=path,
            config=config,
            season=season,
            source=source,
        )
        for path in raw_csv_paths
    ]
    return combine_normalized_weekly_projections(frames)
