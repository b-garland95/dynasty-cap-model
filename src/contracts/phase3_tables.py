from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.contracts.schedule_builder import build_player_schedule_rows


def _normalize_column_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    return normalized.strip("_")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "t", "1", "yes", "y"}


ROSTER_REQUIRED_COLUMNS = {
    "team",
    "player",
    "position",
    "current_salary",
    "real_salary",
    "extension_salary",
    "years",
    "ps_eligible",
    "has_been_extended",
    "has_been_tagged",
    "contract_eligible",
    "extension_eligible",
    "tag_eligible",
}

ROSTER_NUMERIC_COLUMNS = {"current_salary", "real_salary", "extension_salary", "years"}
ROSTER_BOOLEAN_COLUMNS = {
    "ps_eligible", "has_been_extended", "has_been_tagged",
    "contract_eligible", "extension_eligible", "tag_eligible",
}


def validate_roster_csv(file_path: str) -> dict[str, Any]:
    """Validate a roster CSV file without building the full ledger.

    Returns ``{"valid": True, "rows": N, "teams": [...]}`` on success,
    or ``{"valid": False, "error": "..."}`` on failure.
    """
    try:
        raw_df = pd.read_csv(file_path)
    except Exception as exc:
        return {"valid": False, "error": f"Cannot read CSV: {exc}"}

    if raw_df.empty:
        return {"valid": False, "error": "Roster CSV has no data rows"}

    normalized_columns = {_normalize_column_name(col): col for col in raw_df.columns}
    missing = sorted(ROSTER_REQUIRED_COLUMNS - set(normalized_columns))
    if missing:
        return {"valid": False, "error": f"Missing required columns: {missing}"}

    for col_key in ROSTER_NUMERIC_COLUMNS:
        original_col = normalized_columns[col_key]
        try:
            pd.to_numeric(raw_df[original_col], errors="raise")
        except (ValueError, TypeError) as exc:
            return {"valid": False, "error": f"Column {original_col!r} has non-numeric values: {exc}"}

    teams = sorted(raw_df[normalized_columns["team"]].dropna().unique().tolist())
    return {"valid": True, "rows": len(raw_df), "teams": teams}


def build_contract_ledger(roster_csv_path: str) -> pd.DataFrame:
    """
    Build Phase 3 Table 1 (Player Contract Ledger) from a League Tycoon roster CSV.
    """
    raw_df = pd.read_csv(roster_csv_path)
    normalized_columns = {_normalize_column_name(col): col for col in raw_df.columns}

    missing = sorted(ROSTER_REQUIRED_COLUMNS.difference(normalized_columns))
    if missing:
        raise ValueError(f"Missing required columns in roster export: {missing}")

    rename_map = {
        normalized_columns["team"]: "team",
        normalized_columns["player"]: "player",
        normalized_columns["position"]: "position",
        normalized_columns["current_salary"]: "current_salary",
        normalized_columns["real_salary"]: "real_salary",
        normalized_columns["extension_salary"]: "extension_salary",
        normalized_columns["years"]: "years_remaining",
        normalized_columns["ps_eligible"]: "ps_eligible",
        normalized_columns["has_been_extended"]: "has_been_extended",
        normalized_columns["has_been_tagged"]: "has_been_tagged",
        normalized_columns["contract_eligible"]: "contract_eligible",
        normalized_columns["extension_eligible"]: "extension_eligible",
        normalized_columns["tag_eligible"]: "tag_eligible",
    }
    ledger_df = raw_df.rename(columns=rename_map)[list(rename_map.values())].copy()

    # Normalize multi-value position strings (e.g. "DB, WR" → "WR").
    # League Tycoon occasionally exports two-way players with comma-separated
    # positions; we keep the last value which is the fantasy-relevant slot.
    ledger_df["position"] = (
        ledger_df["position"]
        .astype(str)
        .str.split(",")
        .str[-1]
        .str.strip()
    )

    numeric_cols = ["current_salary", "real_salary", "extension_salary", "years_remaining"]
    for col in numeric_cols:
        ledger_df[col] = pd.to_numeric(ledger_df[col], errors="raise")
    for col in ["current_salary", "real_salary", "extension_salary"]:
        ledger_df[col] = ledger_df[col].astype(float)
    ledger_df["years_remaining"] = ledger_df["years_remaining"].astype(int)

    bool_cols = [
        "ps_eligible",
        "has_been_extended",
        "has_been_tagged",
        "contract_eligible",
        "extension_eligible",
        "tag_eligible",
    ]
    for col in bool_cols:
        ledger_df[col] = ledger_df[col].map(_to_bool).astype(bool)

    is_instrument = ledger_df["has_been_extended"] | ledger_df["has_been_tagged"]
    ledger_df["contract_type_bucket"] = is_instrument.map(
        lambda x: "instrument_adjusted" if x else "standard"
    )
    ledger_df["needs_schedule_validation"] = ledger_df["contract_type_bucket"].eq("instrument_adjusted")

    return ledger_df


def build_salary_schedule(ledger_df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """
    Build Phase 3 Table 2 (Contract Salary Schedule) from ledger rows and config.
    """
    annual_inflation = float(config["cap"]["annual_inflation"])

    rows: list[dict[str, Any]] = []
    for ledger_row in ledger_df.to_dict(orient="records"):
        rows.extend(build_player_schedule_rows(ledger_row, annual_inflation=annual_inflation))

    schedule_df = pd.DataFrame(
        rows,
        columns=[
            "player",
            "team",
            "position",
            "year_index",
            "cap_hit_real",
            "cap_hit_current",
            "schedule_source",
            "needs_schedule_validation",
        ],
    )
    return schedule_df


def apply_schedule_overrides(
    schedule_df: pd.DataFrame,
    overrides_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Apply row-level schedule overrides keyed by player/team/position/year_index."""
    if overrides_df is None or overrides_df.empty:
        return schedule_df.copy()

    key_cols = ["player", "team", "position", "year_index"]
    required = set(key_cols + ["cap_hit_real", "cap_hit_current", "schedule_source", "needs_schedule_validation"])
    missing = sorted(required - set(overrides_df.columns))
    if missing:
        raise ValueError(f"Schedule overrides missing required columns: {missing}")

    working = schedule_df.copy()
    overrides = overrides_df.copy()

    overrides["year_index"] = pd.to_numeric(overrides["year_index"], errors="raise").astype(int)
    overrides["cap_hit_real"] = pd.to_numeric(overrides["cap_hit_real"], errors="raise").astype(float)
    overrides["cap_hit_current"] = pd.to_numeric(overrides["cap_hit_current"], errors="coerce").astype(float)
    overrides["needs_schedule_validation"] = overrides["needs_schedule_validation"].map(_to_bool).astype(bool)

    dup_mask = overrides.duplicated(subset=key_cols, keep=False)
    if dup_mask.any():
        dupes = overrides.loc[dup_mask, key_cols].drop_duplicates().to_dict(orient="records")
        raise ValueError(f"Schedule overrides contain duplicate keys: {dupes}")

    working["_row_order"] = range(len(working))
    merged = working.merge(
        overrides,
        on=key_cols,
        how="left",
        suffixes=("", "_override"),
    )

    for col in ["cap_hit_real", "cap_hit_current", "schedule_source", "needs_schedule_validation"]:
        override_col = f"{col}_override"
        merged[col] = merged[override_col].combine_first(merged[col])

    merged["needs_schedule_validation"] = merged["needs_schedule_validation"].map(_to_bool).astype(bool)

    drop_cols = [f"{col}_override" for col in ["cap_hit_real", "cap_hit_current", "schedule_source", "needs_schedule_validation"]]
    merged = merged.drop(columns=drop_cols).sort_values("_row_order").drop(columns="_row_order")
    return merged.reset_index(drop=True)


def load_schedule_overrides(path: str | Path | None) -> pd.DataFrame | None:
    """Load schedule overrides CSV if present, otherwise return None."""
    if path is None:
        return None
    path_obj = Path(path)
    if not path_obj.exists():
        return None
    return pd.read_csv(path_obj)
