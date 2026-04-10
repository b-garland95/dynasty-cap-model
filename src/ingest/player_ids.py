"""Player name / ID normalization layer.

Thin wrapper around ``nflreadpy.load_ff_playerids()`` that crosswalks the
identifier spaces used across this repo's ingest paths:

- FantasyData weekly projections carry a FantasyData ``player_id`` (stored
  as str; see ``src/ingest/weekly_projections.py``).
- nflverse historical weekly points carry a ``gsis_id`` as their
  ``player_id`` (see ``src/ingest/historical_weekly_points.py``).
- League Tycoon roster exports carry only a player name with no ID column
  (see ``src/contracts/phase3_tables.py``).

``nflreadpy.load_ff_playerids()`` returns a single table that contains
``fantasy_data_id``, ``gsis_id``, ``fantasypros_id``, ``sleeper_id``,
``merge_name`` (lowercased/punctuation-stripped canonical name), plus
several other identifier columns. That table is the crosswalk.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

CROSSWALK_COLUMNS = [
    "gsis_id",
    "fantasy_data_id",
    "fantasypros_id",
    "sleeper_id",
    "mfl_id",
    "name",
    "merge_name",
    "position",
    "team",
    "birthdate",
]

_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Return the nflverse-style ``merge_name`` form of a player name.

    Lowercases, strips punctuation, drops common generational suffixes
    (``jr``, ``sr``, ``ii``..``v``), and collapses whitespace. This matches
    the canonical form stored in ``load_ff_playerids().merge_name``, so a
    roster-export name like ``"Travis Etienne Jr."`` normalizes to
    ``"travis etienne"`` — directly joinable against the crosswalk.
    """
    if raw is None:
        return ""
    s = str(raw).lower()
    s = _PUNCT_RE.sub(" ", s)
    tokens = [t for t in _WS_RE.split(s) if t and t not in _SUFFIX_TOKENS]
    return " ".join(tokens)


def load_player_id_crosswalk(
    cache_path: Optional[Path] = None,
    *,
    refresh: bool = False,
) -> pd.DataFrame:
    """Load the nflverse player-ID crosswalk as a pandas DataFrame.

    Parameters
    ----------
    cache_path:
        If provided, the crosswalk is read from disk when present (unless
        ``refresh=True``) and written to disk after a live fetch. Use this
        for offline runs; tests should instead monkeypatch this function
        with a fixture-backed stub.
    refresh:
        Force a live fetch even when a cache file exists.

    Returns
    -------
    pd.DataFrame
        DataFrame containing at least ``CROSSWALK_COLUMNS``. ``fantasy_data_id``
        is coerced to string to match the projections ingest pipeline.
    """
    if cache_path is not None and cache_path.exists() and not refresh:
        df = pd.read_csv(cache_path, dtype={"fantasy_data_id": "string"})
    else:
        import nflreadpy as nfl

        # Convert via a python dict to avoid pulling in pyarrow, which
        # polars' native to_pandas() requires in this version. The
        # crosswalk is small (~25k rows) so the overhead is negligible.
        pl_df = nfl.load_ff_playerids()
        df = pd.DataFrame({name: pl_df[name].to_list() for name in pl_df.columns})
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_path, index=False)

    missing = [c for c in CROSSWALK_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"player-id crosswalk missing expected columns: {missing}"
        )

    out = df[CROSSWALK_COLUMNS].copy()
    # ``fantasy_data_id`` in the live crosswalk comes through as a nullable
    # numeric (polars int64 with nulls -> float64). Round-trip it through
    # Int64 before stringifying so values render as "21696" rather than
    # "21696.0", matching how the projections pipeline stores them.
    fd = pd.to_numeric(out["fantasy_data_id"], errors="coerce").astype("Int64")
    out["fantasy_data_id"] = fd.astype("string")
    return out


def _crosswalk_for_attach(
    crosswalk: Optional[pd.DataFrame],
) -> pd.DataFrame:
    if crosswalk is None:
        crosswalk = load_player_id_crosswalk()
    return crosswalk


def attach_gsis_id_by_fantasy_data_id(
    df: pd.DataFrame,
    *,
    fd_id_col: str = "player_id",
    crosswalk: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Attach ``gsis_id``/``fantasypros_id`` via a FantasyData-ID join.

    Expects ``df[fd_id_col]`` to carry FantasyData IDs (the shape produced
    by ``src/ingest/weekly_projections.py``). Unmatched rows receive null
    IDs and ``id_match_source`` is left null.
    """
    cw = _crosswalk_for_attach(crosswalk)
    left = df.copy()
    left["_fd_id_str"] = left[fd_id_col].astype("string")

    right = cw[["fantasy_data_id", "gsis_id", "fantasypros_id"]].drop_duplicates(
        subset=["fantasy_data_id"]
    )
    merged = left.merge(
        right,
        how="left",
        left_on="_fd_id_str",
        right_on="fantasy_data_id",
    )
    merged = merged.drop(columns=["_fd_id_str", "fantasy_data_id"])
    merged["id_match_source"] = merged["gsis_id"].where(
        merged["gsis_id"].isna(), "fantasy_data_id"
    )
    # Where gsis_id is null, id_match_source stays null (pandas preserves NaN).
    merged.loc[merged["gsis_id"].isna(), "id_match_source"] = pd.NA
    return merged


def attach_gsis_id_by_name(
    df: pd.DataFrame,
    *,
    name_col: str = "player",
    position_col: str = "position",
    crosswalk: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Attach IDs to name-only rows via normalized-name + position join.

    Used for League Tycoon roster exports which carry no identifier column.
    Matches ``normalize_name(df[name_col])`` against the crosswalk's
    ``merge_name`` plus the player's position. Ambiguous ``(merge_name,
    position)`` collisions are left unmatched and flagged as
    ``"ambiguous"``; unmatched rows get null ``id_match_source``.
    """
    cw = _crosswalk_for_attach(crosswalk)
    left = df.copy()
    left["_merge_name"] = left[name_col].map(normalize_name)
    left["_position_u"] = left[position_col].astype(str).str.upper()

    right = cw[["merge_name", "position", "gsis_id", "fantasy_data_id",
                "fantasypros_id"]].copy()
    right["_position_u"] = right["position"].astype(str).str.upper()

    # Detect ambiguous (merge_name, position) keys in the crosswalk.
    dup_mask = right.duplicated(
        subset=["merge_name", "_position_u"], keep=False
    )
    ambiguous_keys = set(
        map(tuple, right.loc[dup_mask, ["merge_name", "_position_u"]].values)
    )
    right_unique = right.loc[~dup_mask].drop(columns=["position"])

    merged = left.merge(
        right_unique,
        how="left",
        left_on=["_merge_name", "_position_u"],
        right_on=["merge_name", "_position_u"],
    )
    merged = merged.drop(columns=["merge_name"])

    # Build id_match_source: matched / ambiguous / null.
    key_tuples = list(
        zip(merged["_merge_name"].tolist(), merged["_position_u"].tolist())
    )
    is_ambiguous = pd.Series(
        [k in ambiguous_keys for k in key_tuples], index=merged.index
    )
    matched = merged["gsis_id"].notna()
    source = pd.Series(pd.NA, index=merged.index, dtype="object")
    source[matched] = "merge_name+position"
    source[(~matched) & is_ambiguous] = "ambiguous"
    merged["id_match_source"] = source

    return merged.drop(columns=["_merge_name", "_position_u"])


def harmonize_projection_names(
    proj_df: pd.DataFrame,
    *,
    fd_id_col: str = "player_id",
    crosswalk: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Attach ``gsis_id`` and replace player names with nflverse canonical form.

    Intended for weekly-projection DataFrames that carry a FantasyData
    ``player_id``.  The crosswalk is used to look up each player's
    ``gsis_id`` and nflverse ``name``; the ``player`` column is then
    overwritten with the nflverse name where a match exists (original
    name is kept as a fallback).

    Returns a copy of *proj_df* with ``gsis_id`` added and ``player``
    harmonized.  Intermediate join columns are dropped.
    """
    cw = _crosswalk_for_attach(crosswalk)

    # Step 1: attach gsis_id via FantasyData ID.
    with_ids = attach_gsis_id_by_fantasy_data_id(
        proj_df, fd_id_col=fd_id_col, crosswalk=cw,
    )

    # Step 2: bring in the nflverse canonical name for matched rows.
    name_lookup = (
        cw[["gsis_id", "name"]]
        .dropna(subset=["gsis_id"])
        .drop_duplicates(subset=["gsis_id"])
        .rename(columns={"name": "_nflverse_name"})
    )
    with_ids = with_ids.merge(name_lookup, on="gsis_id", how="left")

    # Overwrite player with nflverse name where available.
    matched = with_ids["_nflverse_name"].notna()
    with_ids.loc[matched, "player"] = with_ids.loc[matched, "_nflverse_name"]
    with_ids = with_ids.drop(columns=["_nflverse_name"])

    # Clean up columns added by attach_gsis_id_by_fantasy_data_id that
    # the caller doesn't need beyond gsis_id.
    drop_cols = [c for c in ("fantasypros_id", "id_match_source") if c in with_ids.columns]
    with_ids = with_ids.drop(columns=drop_cols)

    n_unmatched = with_ids["gsis_id"].isna().sum()
    if n_unmatched:
        import warnings
        warnings.warn(
            f"harmonize_projection_names: {n_unmatched} of {len(with_ids)} "
            f"projection rows have no crosswalk gsis_id match",
            stacklevel=2,
        )

    return with_ids
