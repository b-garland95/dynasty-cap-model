"""Player dimensional data layer.

Thin wrapper around ``nflreadpy.load_players()`` that pulls static player
attributes (birth date, draft info, physical measurements, college) and
attaches season-specific derived fields (age, years of experience, rookie
flag, log draft capital) to any DataFrame that carries a ``gsis_id`` column.

Usage pattern::

    from src.ingest.player_dimensions import enrich_with_player_dimensions

    enriched = enrich_with_player_dimensions(season_values, season_col="season")

The enrichment is a pure left-join decoration — no existing rows are dropped
and no existing columns are modified.  Players whose ``gsis_id`` has no match
in the dimensions table receive ``NaN`` for all added columns.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Column manifest
# ---------------------------------------------------------------------------

DIMENSION_COLUMNS = [
    "gsis_id",          # primary join key — must be first
    "display_name",     # canonical nflreadpy name (for display / debugging)
    "birth_date",       # raw date; used to derive age
    "rookie_season",    # year they first appeared on an NFL roster
    "draft_year",       # year drafted (may differ from rookie_season for taxi-squad players)
    "draft_round",      # 1–7; NaN = undrafted
    "draft_pick",       # overall pick number; NaN = undrafted
    "height",           # inches
    "weight",           # pounds
    "college_name",     # alma mater
    "status",           # active / inactive / etc.
    "pfr_id",           # Pro Football Reference ID (future join key)
    "espn_id",          # ESPN ID (future join key)
]


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_player_dimensions(
    cache_path: Optional[Path] = None,
    *,
    refresh: bool = False,
) -> pd.DataFrame:
    """Load the nflreadpy player-dimensions table as a pandas DataFrame.

    Parameters
    ----------
    cache_path:
        If provided, the table is read from disk when the file exists (unless
        ``refresh=True``) and written to disk after a live fetch.  Use this
        for offline pipeline runs; tests should pass ``cache_path`` pointing
        to the sample fixture instead of hitting the network.
    refresh:
        Force a live fetch even when a cache file exists.

    Returns
    -------
    pd.DataFrame
        DataFrame containing exactly ``DIMENSION_COLUMNS``.  ``birth_date``
        is returned as-is (string or date-like) — type coercion happens in
        ``enrich_with_player_dimensions`` where the season context is known.
    """
    if cache_path is not None and Path(cache_path).exists() and not refresh:
        df = pd.read_csv(cache_path)
    else:
        import nflreadpy as nfl  # deferred: mirrors player_ids.py pattern

        # Convert via dict-comprehension to avoid the pyarrow requirement that
        # polars' native .to_pandas() needs.  The table is ~5 k rows; overhead
        # is negligible.
        pl_df = nfl.load_players()
        df = pd.DataFrame({name: pl_df[name].to_list() for name in pl_df.columns})

        if cache_path is not None:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path, index=False)

    missing = [c for c in DIMENSION_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"player-dimensions table missing expected columns: {missing}"
        )

    return df[DIMENSION_COLUMNS].copy()


# ---------------------------------------------------------------------------
# Enrich
# ---------------------------------------------------------------------------

def enrich_with_player_dimensions(
    df: pd.DataFrame,
    season_col: str = "season",
    dims: Optional[pd.DataFrame] = None,
    cache_path: Optional[Path] = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """Left-join player dimensions onto *df* and append season-specific fields.

    Parameters
    ----------
    df:
        DataFrame that contains at minimum a ``gsis_id`` column.  If
        ``season_col`` is present its values are used to compute age and
        years-of-experience relative to each row's season.
    season_col:
        Name of the integer season column (e.g. ``"season"``).  The column
        must contain four-digit year integers (2021, 2022, …).
    dims:
        Pre-loaded dimensions DataFrame (from ``load_player_dimensions``).
        If ``None``, dimensions are loaded fresh (optionally from cache).
    cache_path:
        Passed through to ``load_player_dimensions`` when ``dims`` is None.
    refresh:
        Passed through to ``load_player_dimensions`` when ``dims`` is None.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with static dimension columns appended, followed by
        four derived columns:

        ``age``
            Float.  Player age as of September 1 of ``season_col``'s year
            (NFL standard measurement date).  ``NaN`` when ``birth_date`` is
            missing or unparseable.

        ``years_of_experience``
            Nullable integer.  ``max(0, season - rookie_season)``.  Zero in
            the rookie year; ``pd.NA`` when ``rookie_season`` is missing.

        ``is_rookie``
            Bool.  ``True`` when ``season == rookie_season``.  ``False`` when
            ``rookie_season`` is missing (safe default — do not assume rookie).

        ``log_draft_number``
            Float.  Natural log of the overall draft pick number (``draft_pick``).
            ``NaN`` for undrafted free agents.
    """
    if dims is None:
        dims = load_player_dimensions(cache_path=cache_path, refresh=refresh)

    if "gsis_id" not in df.columns:
        raise ValueError("enrich_with_player_dimensions: df must contain a 'gsis_id' column")

    # Deduplicate dims on gsis_id to prevent fan-out from any upstream duplicates.
    static_cols = [c for c in DIMENSION_COLUMNS if c != "gsis_id"]
    dims_right = dims[["gsis_id"] + static_cols].drop_duplicates(subset=["gsis_id"])

    out = df.merge(dims_right, on="gsis_id", how="left")

    # ------------------------------------------------------------------
    # Derived field: age (float, as of Sep 1 of the season year)
    # ------------------------------------------------------------------
    if season_col in out.columns and "birth_date" in out.columns:
        bd = pd.to_datetime(out["birth_date"], errors="coerce")
        # Build a Sep-1 timestamp for each row's season year.
        cutoff = out[season_col].map(lambda s: pd.Timestamp(int(s), 9, 1))
        out["age"] = (cutoff - bd).dt.days / 365.25
    else:
        out["age"] = np.nan
        if season_col not in out.columns:
            warnings.warn(
                f"enrich_with_player_dimensions: season column '{season_col}' not found; "
                "age will be NaN",
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # Derived field: years_of_experience (nullable Int64)
    # ------------------------------------------------------------------
    if season_col in out.columns and "rookie_season" in out.columns:
        rs = pd.to_numeric(out["rookie_season"], errors="coerce")
        season_int = pd.to_numeric(out[season_col], errors="coerce")
        yoe = (season_int - rs).clip(lower=0)
        # Preserve NaN where rookie_season was missing.
        out["years_of_experience"] = yoe.where(rs.notna()).astype("Int64")
    else:
        out["years_of_experience"] = pd.array([pd.NA] * len(out), dtype="Int64")

    # ------------------------------------------------------------------
    # Derived field: is_rookie (bool)
    # ------------------------------------------------------------------
    if season_col in out.columns and "rookie_season" in out.columns:
        rs = pd.to_numeric(out["rookie_season"], errors="coerce")
        season_int = pd.to_numeric(out[season_col], errors="coerce")
        # NaN == NaN is False in pandas — correct safe default for missing data.
        out["is_rookie"] = season_int == rs
    else:
        out["is_rookie"] = False

    # ------------------------------------------------------------------
    # Derived field: log_draft_number (float; NaN for undrafted)
    # ------------------------------------------------------------------
    if "draft_pick" in out.columns:
        draft_num = pd.to_numeric(out["draft_pick"], errors="coerce")
        out["log_draft_number"] = np.where(draft_num.notna(), np.log(draft_num), np.nan)
    else:
        out["log_draft_number"] = np.nan

    return out
