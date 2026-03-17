from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule


def export_phase3_tables(
    roster_csv_path: str,
    config: dict[str, Any],
    output_dir: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build and export the Phase 3 ledger and salary schedule as CSV files."""
    ledger_df = build_contract_ledger(roster_csv_path)
    schedule_df = build_salary_schedule(ledger_df, config)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ledger_df.to_csv(output_path / "player_contract_ledger.csv", index=False)
    schedule_df.to_csv(output_path / "contract_salary_schedule.csv", index=False)

    return ledger_df, schedule_df
