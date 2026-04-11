from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.contracts.phase3_tables import (
    apply_schedule_overrides,
    build_contract_ledger,
    build_salary_schedule,
    load_schedule_overrides,
)
from src.contracts.phase3_value_tables import build_phase3_tables_3_to_7, load_tv_inputs


def export_phase3_tables(
    roster_csv_path: str,
    config: dict[str, Any],
    output_dir: str,
    schedule_overrides_path: str | None = None,
    tv_inputs_path: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Build and export Phase 3 Tables 1 through 7 as CSV files."""
    ledger_df = build_contract_ledger(roster_csv_path)
    schedule_df = build_salary_schedule(ledger_df, config)
    schedule_df = apply_schedule_overrides(
        schedule_df,
        load_schedule_overrides(schedule_overrides_path),
    )
    downstream_tables = build_phase3_tables_3_to_7(
        ledger_df,
        schedule_df,
        config,
        tv_inputs_df=load_tv_inputs(tv_inputs_path),
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ledger_df.to_csv(output_path / "player_contract_ledger.csv", index=False)
    schedule_df.to_csv(output_path / "contract_salary_schedule.csv", index=False)
    downstream_tables["production_value_forecast"].to_csv(output_path / "production_value_forecast.csv", index=False)
    downstream_tables["contract_economics"].to_csv(output_path / "contract_economics.csv", index=False)
    downstream_tables["contract_surplus"].to_csv(output_path / "contract_surplus.csv", index=False)
    downstream_tables["team_cap_health_dashboard"].to_csv(output_path / "team_cap_health_dashboard.csv", index=False)
    downstream_tables["extension_candidates"].to_csv(output_path / "extension_candidates.csv", index=False)
    downstream_tables["tag_candidates"].to_csv(output_path / "tag_candidates.csv", index=False)
    downstream_tables["option_candidates"].to_csv(output_path / "option_candidates.csv", index=False)
    downstream_tables["instrument_candidates"].to_csv(output_path / "instrument_candidates.csv", index=False)

    return {
        "player_contract_ledger": ledger_df,
        "contract_salary_schedule": schedule_df,
        **downstream_tables,
    }
