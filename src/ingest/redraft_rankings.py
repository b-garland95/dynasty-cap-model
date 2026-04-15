"""Ingest and normalize pre-season redraft rankings/ADP.

Two source formats are supported:

1. **FantasyPros OP Rankings** (``data/raw/rankings/redraft/``)
   Legacy format with schema variants across years. ID resolution via
   nflverse ``merge_name + position`` crosswalk join.

2. **FantasyData 2QB ADP** (``data/raw/rankings/redraft_adp/``)
   Preferred format: ``nfl-2qb-adp-*_YYYY.csv`` files with columns
   ``rank, id, player, team, bye_week, age, pos, adp_2qb_pos_rank, adp_2qb``.
   The ``id`` column is a FantasyData player ID — resolved directly via the
   nflverse crosswalk's ``fantasy_data_id``. Covers 2015–present with true
   ADP float values (vs integer rank in the legacy format).

Output columns (master file, both formats):
    season, rank, tier, player, team, position, pos_rank, merge_name, gsis_id

The ``adp_2qb`` value is stored as ``rank`` (float) in the master for the
ADP format; the legacy format stores integer overall rank.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from src.ingest.player_ids import (
    load_player_id_crosswalk,
    normalize_name,
)

# Regex to split "QB3" → ("QB", 3)
_POS_RANK_RE = re.compile(r"^([A-Z]+)(\d+)$")

# Columns common to every schema variant
_COMMON_RENAMES = {
    "RK": "rank",
    "TIERS": "tier",
    "PLAYER NAME": "player",
    "TEAM": "team",
    "POS": "pos_raw",
}


def _extract_season_from_path(path: Path) -> int:
    """Pull the four-digit year from a FantasyPros filename."""
    m = re.search(r"(\d{4})", path.name)
    if m is None:
        raise ValueError(f"Cannot extract season year from filename: {path.name}")
    return int(m.group(1))


def _split_pos_rank(pos_raw: pd.Series) -> pd.DataFrame:
    """Split composite position string like 'QB3' into position + pos_rank."""
    parts = pos_raw.str.extract(r"^([A-Z]+)(\d+)$")
    return pd.DataFrame({
        "position": parts[0],
        "pos_rank": pd.to_numeric(parts[1], errors="coerce").astype("Int64"),
    })


def load_single_redraft_rankings(path: Path, *, season: Optional[int] = None) -> pd.DataFrame:
    """Load and normalize a single FantasyPros redraft rankings CSV.

    Parameters
    ----------
    path:
        Path to a ``FantasyPros_YYYY_Draft_OP_Rankings.csv`` file.
    season:
        Override the season year; if None it is extracted from the filename.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank
    """
    if season is None:
        season = _extract_season_from_path(path)

    df = pd.read_csv(path)

    # Only keep the columns we care about (schema varies by year).
    rename_map = {col: target for col, target in _COMMON_RENAMES.items() if col in df.columns}
    df = df.rename(columns=rename_map)
    keep = [v for v in rename_map.values()]
    df = df[keep].copy()

    # Clean rank — may be quoted string
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
    df["tier"] = pd.to_numeric(df["tier"], errors="coerce").astype("Int64")

    # Split POS into position + pos_rank
    pos_parts = _split_pos_rank(df["pos_raw"])
    df["position"] = pos_parts["position"]
    df["pos_rank"] = pos_parts["pos_rank"]
    df = df.drop(columns=["pos_raw"])

    # Filter to skill positions only
    df = df[df["position"].isin({"QB", "RB", "WR", "TE"})].copy()

    df["season"] = season
    df = df[["season", "rank", "tier", "player", "team", "position", "pos_rank"]].copy()
    df = df.reset_index(drop=True)
    return df


def _load_name_overrides(path: Path) -> pd.DataFrame:
    """Load the manual name-override CSV.

    Each row maps a ``(ranking_name, position)`` to either a corrected
    ``merge_name_override`` (for nickname/alias mismatches resolved via
    crosswalk) or a direct ``gsis_id_override`` (for position-mismatch
    cases where the crosswalk position differs from the ranking position).
    """
    if not path.exists():
        return pd.DataFrame(
            columns=["ranking_name", "position", "merge_name_override", "gsis_id_override"]
        )
    return pd.read_csv(path, dtype=str).fillna("")


def _load_ambiguous_resolutions(path: Path) -> pd.DataFrame:
    """Load the manual ambiguity-resolution CSV.

    Each row maps a ``(merge_name, position, season)`` to the chosen
    ``gsis_id`` for players whose name+position matches multiple
    crosswalk entries.
    """
    if not path.exists():
        return pd.DataFrame(columns=["merge_name", "position", "season", "gsis_id"])
    df = pd.read_csv(path, dtype={"season": int, "gsis_id": str})
    return df


def build_master_redraft_rankings(
    raw_dir: Path,
    *,
    crosswalk: Optional[pd.DataFrame] = None,
    name_overrides_path: Optional[Path] = None,
    ambiguous_ids_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Load all per-year ranking CSVs, stack, and attach IDs.

    Parameters
    ----------
    raw_dir:
        Directory containing ``FantasyPros_YYYY_Draft_OP_Rankings.csv`` files.
    crosswalk:
        Optional pre-loaded crosswalk; fetched live if None.
    name_overrides_path:
        Path to ``redraft_ranking_name_overrides.csv``. If None, looks for
        it at ``data/external/redraft_ranking_name_overrides.csv`` relative
        to the repo root.
    ambiguous_ids_path:
        Path to ``redraft_ranking_ambiguous_ids.csv``. If None, looks for
        it at ``data/external/redraft_ranking_ambiguous_ids.csv`` relative
        to the repo root.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank,
                 merge_name, gsis_id
    """
    files = sorted(raw_dir.glob("FantasyPros_*_Draft_OP_Rankings.csv"))
    if not files:
        raise FileNotFoundError(f"No ranking CSVs found in {raw_dir}")

    frames = [load_single_redraft_rankings(p) for p in files]
    master = pd.concat(frames, ignore_index=True)

    # Attach merge_name for downstream joins
    master["merge_name"] = master["player"].map(normalize_name)

    # --- Apply name overrides ------------------------------------------------
    repo_root = Path(__file__).resolve().parents[2]
    if name_overrides_path is None:
        name_overrides_path = repo_root / "data" / "external" / "redraft_ranking_name_overrides.csv"
    overrides = _load_name_overrides(name_overrides_path)

    # Build lookup dicts keyed on (normalize_name(ranking_name), position)
    override_merge = {}   # (merge_name, position) → corrected merge_name
    override_gsis = {}    # (merge_name, position) → direct gsis_id
    for _, row in overrides.iterrows():
        key = (normalize_name(row["ranking_name"]), row["position"])
        if row["merge_name_override"]:
            override_merge[key] = row["merge_name_override"]
        if row["gsis_id_override"]:
            override_gsis[key] = row["gsis_id_override"]

    # Apply merge_name overrides
    for (mn, pos), new_mn in override_merge.items():
        mask = (master["merge_name"] == mn) & (master["position"] == pos)
        master.loc[mask, "merge_name"] = new_mn

    # --- Attach gsis_id via crosswalk merge_name + position ------------------
    if crosswalk is None:
        crosswalk = load_player_id_crosswalk()

    cw = crosswalk[["merge_name", "position", "gsis_id"]].copy()
    cw["position"] = cw["position"].astype(str).str.upper()

    # Prefer rows that have a gsis_id, then de-duplicate. Many legacy players
    # appear twice in the crosswalk (once with gsis_id, once without); sorting
    # so non-null IDs come first and keeping the first resolves these cleanly.
    # Truly ambiguous keys (multiple *different* gsis_ids) are still dropped.
    cw = cw.sort_values("gsis_id", na_position="last")
    cw_deduped = cw.drop_duplicates(subset=["merge_name", "position"], keep="first")

    # Detect truly ambiguous keys: multiple distinct non-null gsis_ids
    has_id = cw[cw["gsis_id"].notna()]
    ambig = (
        has_id.drop_duplicates(subset=["merge_name", "position", "gsis_id"])
        .duplicated(subset=["merge_name", "position"], keep=False)
    )
    ambig_keys = set(
        map(tuple, has_id.loc[ambig.values, ["merge_name", "position"]].values)
    )
    if ambig_keys:
        cw_deduped = cw_deduped[
            ~cw_deduped.set_index(["merge_name", "position"]).index.isin(ambig_keys)
        ]
    cw_unique = cw_deduped

    master = master.merge(
        cw_unique,
        on=["merge_name", "position"],
        how="left",
    )

    # --- Apply direct gsis_id overrides (position-mismatch cases) ------------
    for (mn, pos), gsis in override_gsis.items():
        mask = (master["merge_name"] == mn) & (master["position"] == pos) & master["gsis_id"].isna()
        master.loc[mask, "gsis_id"] = gsis

    # --- Apply ambiguous-ID resolutions (season-specific) --------------------
    if ambiguous_ids_path is None:
        ambiguous_ids_path = repo_root / "data" / "external" / "redraft_ranking_ambiguous_ids.csv"
    resolutions = _load_ambiguous_resolutions(ambiguous_ids_path)

    for _, row in resolutions.iterrows():
        mask = (
            (master["merge_name"] == row["merge_name"])
            & (master["position"] == row["position"])
            & (master["season"] == row["season"])
            & master["gsis_id"].isna()
        )
        master.loc[mask, "gsis_id"] = row["gsis_id"]

    col_order = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id",
    ]
    return master[col_order].copy()


# ---------------------------------------------------------------------------
# FantasyData 2QB ADP format (data/raw/rankings/redraft_adp/)

# ---------------------------------------------------------------------------

def _extract_season_from_adp_path(path: Path) -> int:
    """Pull the four-digit year from a ``nfl-2qb-adp-*_YYYY.csv`` filename."""
    m = re.search(r"_(\d{4})\.csv$", path.name)
    if m is None:
        raise ValueError(f"Cannot extract season year from filename: {path.name}")
    return int(m.group(1))


def load_single_redraft_adp(path: Path, *, season: Optional[int] = None) -> pd.DataFrame:
    """Load and normalize a single FantasyData 2QB ADP CSV.

    Parameters
    ----------
    path:
        Path to a ``nfl-2qb-adp-*_YYYY.csv`` file.
    season:
        Override the season year; if None it is extracted from the filename.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank, fantasy_data_id

        ``rank`` contains the ``adp_2qb`` float value (true ADP).
        ``tier`` is always ``pd.NA`` (not present in this format).
        ``fantasy_data_id`` is the raw ``id`` column as a string for crosswalk join.
    """
    if season is None:
        season = _extract_season_from_adp_path(path)

    df = pd.read_csv(path, dtype={"id": "string"})

    # Drop DST/team rows — their ``id`` is a team abbreviation, not numeric
    df = df[pd.to_numeric(df["id"], errors="coerce").notna()].copy()

    # Filter to skill positions only
    df = df[df["pos"].isin({"QB", "RB", "WR", "TE"})].copy()

    # Split adp_2qb_pos_rank (e.g. "QB3") into position + pos_rank
    pos_parts = df["adp_2qb_pos_rank"].str.extract(r"^([A-Z]+)(\d+)$")
    df["position"] = pos_parts[0]
    df["pos_rank"] = pd.to_numeric(pos_parts[1], errors="coerce").astype("Int64")

    # Use adp_2qb as the rank (true ADP float); drop the integer ordinal rank
    df = df.drop(columns=["rank"])
    df = df.rename(columns={"adp_2qb": "rank"})
    df["tier"] = pd.NA
    df["season"] = season
    df["fantasy_data_id"] = df["id"].astype("string")

    return df[["season", "rank", "tier", "player", "team", "position", "pos_rank", "fantasy_data_id"]].copy().reset_index(drop=True)


def build_master_redraft_adp(
    raw_dir: Path,
    *,
    crosswalk: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Load all per-year FantasyData 2QB ADP CSVs, stack, and attach gsis_id.

    Parameters
    ----------
    raw_dir:
        Directory containing ``nfl-2qb-adp-*_YYYY.csv`` files.
    crosswalk:
        Optional pre-loaded nflverse crosswalk; fetched live if None.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank,
                 merge_name, gsis_id

        ``rank`` is the ``adp_2qb`` float value. ``tier`` is always NA.
    """
    files = sorted(raw_dir.glob("nfl-2qb-adp-*.csv"))
    if not files:
        raise FileNotFoundError(f"No ADP CSVs found in {raw_dir}")

    frames = [load_single_redraft_adp(p) for p in files]
    master = pd.concat(frames, ignore_index=True)

    master["merge_name"] = master["player"].map(normalize_name)

    if crosswalk is None:
        crosswalk = load_player_id_crosswalk()

    # Join via fantasy_data_id — convert both sides to nullable Int64
    cw = crosswalk[["fantasy_data_id", "gsis_id"]].copy()
    cw["_fd_int"] = pd.to_numeric(cw["fantasy_data_id"], errors="coerce").astype("Int64")
    cw = cw.dropna(subset=["_fd_int"]).drop_duplicates(subset=["_fd_int"])

    master["_fd_int"] = pd.to_numeric(master["fantasy_data_id"], errors="coerce").astype("Int64")
    master = master.merge(cw[["_fd_int", "gsis_id"]], on="_fd_int", how="left")
    master = master.drop(columns=["_fd_int", "fantasy_data_id"])

    col_order = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id",
    ]
    return master[col_order].copy()


# ---------------------------------------------------------------------------
# Combined ADP + FantasyPros fallback
# ---------------------------------------------------------------------------


def build_master_redraft_adp_with_fallback(
    adp_dir: Path,
    rankings_fallback_dir: Path,
    *,
    crosswalk: Optional[pd.DataFrame] = None,
    name_overrides_path: Optional[Path] = None,
    ambiguous_ids_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Build master redraft ADP, using FantasyPros rankings as a per-season fallback.

    For each season, FantasyData ADP is preferred.  When ADP data is absent for a
    season (e.g. because FantasyData has not yet published rankings for the upcoming
    year), the corresponding FantasyPros rankings file is used instead.

    Parameters
    ----------
    adp_dir:
        Directory containing ``nfl-2qb-adp-*_YYYY.csv`` FantasyData ADP files.
    rankings_fallback_dir:
        Directory containing ``FantasyPros_YYYY_Draft_OP_Rankings.csv`` files
        used as a fallback when ADP is not available for a season.
    crosswalk:
        Optional pre-loaded nflverse crosswalk; fetched live if None.
    name_overrides_path, ambiguous_ids_path:
        Passed through to :func:`build_master_redraft_rankings` for the fallback
        seasons.  See that function for defaults.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank,
                 merge_name, gsis_id, ranking_source

        ``ranking_source`` is ``"fantasydata_adp"`` for rows sourced from
        FantasyData ADP files and ``"fantasypros_rankings"`` for rows sourced
        from FantasyPros fallback files.

    Raises
    ------
    FileNotFoundError
        If no files are found in either directory.
    """
    if crosswalk is None:
        crosswalk = load_player_id_crosswalk()

    frames: list[pd.DataFrame] = []
    adp_seasons: set[int] = set()

    # --- Primary: FantasyData ADP -------------------------------------------
    adp_files = sorted(adp_dir.glob("nfl-2qb-adp-*.csv"))
    if adp_files:
        adp_master = build_master_redraft_adp(adp_dir, crosswalk=crosswalk)
        adp_master["ranking_source"] = "fantasydata_adp"
        adp_seasons = set(adp_master["season"].unique())
        frames.append(adp_master)

    # --- Fallback: FantasyPros rankings for seasons not covered by ADP -------
    rankings_files = sorted(
        rankings_fallback_dir.glob("FantasyPros_*_Draft_OP_Rankings.csv")
    )
    if rankings_files:
        rankings_master = build_master_redraft_rankings(
            rankings_fallback_dir,
            crosswalk=crosswalk,
            name_overrides_path=name_overrides_path,
            ambiguous_ids_path=ambiguous_ids_path,
        )
        fallback = rankings_master[
            ~rankings_master["season"].isin(adp_seasons)
        ].copy()
        if not fallback.empty:
            fallback["ranking_source"] = "fantasypros_rankings"
            frames.append(fallback)

    if not frames:
        raise FileNotFoundError(
            f"No ADP files found in {adp_dir} and no rankings files found in "
            f"{rankings_fallback_dir}"
        )

    combined = pd.concat(frames, ignore_index=True)
    col_order = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id", "ranking_source",
    ]
    return combined[col_order].copy()


# ---------------------------------------------------------------------------
# FantasyData Dynasty ADP format (data/raw/rankings/dynasty_adp/)
# ---------------------------------------------------------------------------


def load_single_dynasty_adp(path: Path, *, season: Optional[int] = None) -> pd.DataFrame:
    """Load and normalize a single FantasyData dynasty ADP CSV.

    Parameters
    ----------
    path:
        Path to a ``nfl-dynasty-adp-*_YYYY.csv`` file.
    season:
        Override the season year; if None it is extracted from the filename.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank, fantasy_data_id

        ``rank`` contains the ``adp_dynasty`` float value (true ADP).
        ``tier`` is always ``pd.NA`` (not present in this format).
        ``fantasy_data_id`` is the raw ``id`` column as a string for crosswalk join.
    """
    if season is None:
        season = _extract_season_from_adp_path(path)

    df = pd.read_csv(path, dtype={"id": "string"})

    # Drop DST/team rows — their ``id`` is a team abbreviation, not numeric
    df = df[pd.to_numeric(df["id"], errors="coerce").notna()].copy()

    # Filter to skill positions only
    df = df[df["pos"].isin({"QB", "RB", "WR", "TE"})].copy()

    # Split adp_dynasty_pos_rank (e.g. "WR1") into position + pos_rank
    pos_parts = df["adp_dynasty_pos_rank"].str.extract(r"^([A-Z]+)(\d+)$")
    df["position"] = pos_parts[0]
    df["pos_rank"] = pd.to_numeric(pos_parts[1], errors="coerce").astype("Int64")

    # Use adp_dynasty as the rank (true ADP float); drop the integer ordinal rank
    df = df.drop(columns=["rank"])
    df = df.rename(columns={"adp_dynasty": "rank"})
    df["tier"] = pd.NA
    df["season"] = season
    df["fantasy_data_id"] = df["id"].astype("string")

    return df[["season", "rank", "tier", "player", "team", "position", "pos_rank", "fantasy_data_id"]].copy().reset_index(drop=True)


def build_master_dynasty_adp(
    raw_dir: Path,
    *,
    crosswalk: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Load all per-year FantasyData dynasty ADP CSVs, stack, and attach gsis_id.

    Parameters
    ----------
    raw_dir:
        Directory containing ``nfl-dynasty-adp-*_YYYY.csv`` files.
    crosswalk:
        Optional pre-loaded nflverse crosswalk; fetched live if None.

    Returns
    -------
    pd.DataFrame
        Columns: season, rank, tier, player, team, position, pos_rank,
                 merge_name, gsis_id

        ``rank`` is the ``adp_dynasty`` float value. ``tier`` is always NA.
    """
    files = sorted(raw_dir.glob("nfl-dynasty-adp-*.csv"))
    if not files:
        raise FileNotFoundError(f"No dynasty ADP CSVs found in {raw_dir}")

    frames = [load_single_dynasty_adp(p) for p in files]
    master = pd.concat(frames, ignore_index=True)

    master["merge_name"] = master["player"].map(normalize_name)

    if crosswalk is None:
        crosswalk = load_player_id_crosswalk()

    # Join via fantasy_data_id — convert both sides to nullable Int64
    cw = crosswalk[["fantasy_data_id", "gsis_id"]].copy()
    cw["_fd_int"] = pd.to_numeric(cw["fantasy_data_id"], errors="coerce").astype("Int64")
    cw = cw.dropna(subset=["_fd_int"]).drop_duplicates(subset=["_fd_int"])

    master["_fd_int"] = pd.to_numeric(master["fantasy_data_id"], errors="coerce").astype("Int64")
    master = master.merge(cw[["_fd_int", "gsis_id"]], on="_fd_int", how="left")
    master = master.drop(columns=["_fd_int", "fantasy_data_id"])

    col_order = [
        "season", "rank", "tier", "player", "team",
        "position", "pos_rank", "merge_name", "gsis_id",
    ]
    return master[col_order].copy()


def ensure_redraft_ranking_season(
    rankings_df: pd.DataFrame,
    *,
    target_season: int,
    adp_dir: Path,
    rankings_fallback_dir: Path,
    crosswalk: Optional[pd.DataFrame] = None,
    name_overrides_path: Optional[Path] = None,
    ambiguous_ids_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Ensure the rankings master includes ``target_season`` coverage.

    If the supplied master already contains the requested season, it is
    returned unchanged. Otherwise the master is rebuilt from raw ADP files
    plus the FantasyPros fallback, preserving the source-priority rule that
    ADP wins whenever a season exists in both places.
    """
    if "season" not in rankings_df.columns:
        raise ValueError("Redraft rankings DataFrame is missing required column: season")

    if int(target_season) in set(pd.to_numeric(rankings_df["season"], errors="coerce").dropna().astype(int)):
        return rankings_df

    rebuilt = build_master_redraft_adp_with_fallback(
        adp_dir=adp_dir,
        rankings_fallback_dir=rankings_fallback_dir,
        crosswalk=crosswalk,
        name_overrides_path=name_overrides_path,
        ambiguous_ids_path=ambiguous_ids_path,
    )
    rebuilt_seasons = set(pd.to_numeric(rebuilt["season"], errors="coerce").dropna().astype(int))
    if int(target_season) not in rebuilt_seasons:
        raise ValueError(
            f"Target season {target_season} is missing after rebuilding redraft rankings master"
        )
    return rebuilt
