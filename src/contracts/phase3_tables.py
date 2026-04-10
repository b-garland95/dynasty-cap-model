from __future__ import annotations

import re
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


def build_contract_ledger(roster_csv_path: str) -> pd.DataFrame:
    """
    Build Phase 3 Table 1 (Player Contract Ledger) from a League Tycoon roster CSV.
    """
    raw_df = pd.read_csv(roster_csv_path)
    normalized_columns = {_normalize_column_name(col): col for col in raw_df.columns}

    required = {
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
    missing = sorted(required.difference(normalized_columns))
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

    return pd.DataFrame(
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
