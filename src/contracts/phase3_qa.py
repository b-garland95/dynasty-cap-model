from __future__ import annotations

from typing import Any

import pandas as pd


def build_phase3_qa_summary(
    ledger_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    top_n: int = 15,
) -> dict[str, Any]:
    """Build reusable QA summary tables for Phase 3 ledger and schedule outputs."""
    year0_schedule = schedule_df.loc[schedule_df["year_index"] == 0].copy()
    validation_players = ledger_df.loc[
        ledger_df["needs_schedule_validation"],
        [
            "player",
            "team",
            "position",
            "real_salary",
            "extension_salary",
            "years_remaining",
            "has_been_extended",
            "has_been_tagged",
        ],
    ].sort_values(["team", "player"])

    bool_columns = [
        "ps_eligible",
        "has_been_extended",
        "has_been_tagged",
        "contract_eligible",
        "extension_eligible",
        "tag_eligible",
    ]

    return {
        "row_counts": {
            "ledger_rows": int(len(ledger_df)),
            "schedule_rows": int(len(schedule_df)),
        },
        "team_player_counts": ledger_df.groupby("team").size().sort_values(ascending=False),
        "team_current_salary": ledger_df.groupby("team")["current_salary"].sum().sort_values(ascending=False),
        "team_real_salary": ledger_df.groupby("team")["real_salary"].sum().sort_values(ascending=False),
        "top_current_salary": ledger_df.sort_values(
            ["current_salary", "real_salary"],
            ascending=False,
        )[
            [
                "player",
                "team",
                "position",
                "current_salary",
                "real_salary",
                "years_remaining",
                "contract_type_bucket",
            ]
        ].head(top_n),
        "top_year0_real": year0_schedule.sort_values(
            ["cap_hit_real", "cap_hit_current"],
            ascending=False,
        )[
            [
                "player",
                "team",
                "position",
                "cap_hit_real",
                "cap_hit_current",
                "schedule_source",
                "needs_schedule_validation",
            ]
        ].head(top_n),
        "validation_players": validation_players,
        "team_validation_counts": ledger_df.groupby("team")["needs_schedule_validation"].sum().sort_values(ascending=False),
        "boolean_counts": {
            column: ledger_df[column].value_counts(dropna=False).to_dict()
            for column in bool_columns
        },
        "numeric_nulls": ledger_df[
            ["current_salary", "real_salary", "extension_salary", "years_remaining"]
        ].isna().sum().to_dict(),
        "years_range": {
            "min": int(ledger_df["years_remaining"].min()),
            "max": int(ledger_df["years_remaining"].max()),
        },
    }


def format_phase3_qa_summary(summary: dict[str, Any]) -> str:
    """Render a human-readable QA report from summary tables."""
    sections = [
        _format_dict_section("ROW_COUNTS", summary["row_counts"]),
        _format_series_section("TEAM_PLAYER_COUNTS", summary["team_player_counts"]),
        _format_series_section("TEAM_CURRENT_SALARY", summary["team_current_salary"].round(2)),
        _format_series_section("TEAM_REAL_SALARY", summary["team_real_salary"].round(2)),
        _format_dataframe_section("TOP_CURRENT_SALARY", summary["top_current_salary"]),
        _format_dataframe_section("TOP_YEAR0_REAL", summary["top_year0_real"]),
        _format_dataframe_section("VALIDATION_PLAYERS", summary["validation_players"]),
        _format_series_section("TEAM_VALIDATION_COUNTS", summary["team_validation_counts"]),
        _format_dict_section("BOOLEAN_COUNTS", summary["boolean_counts"]),
        _format_dict_section("NUMERIC_NULLS", summary["numeric_nulls"]),
        _format_dict_section("YEARS_RANGE", summary["years_range"]),
    ]
    return "\n\n".join(section for section in sections if section)


def _format_series_section(name: str, series: pd.Series) -> str:
    return f"{name}\n{series.to_string()}"



def _format_dataframe_section(name: str, frame: pd.DataFrame) -> str:
    if frame.empty:
        return f"{name}\n<empty>"
    return f"{name}\n{frame.to_string(index=False)}"



def _format_dict_section(name: str, values: dict[str, Any]) -> str:
    return f"{name}\n{values}"
