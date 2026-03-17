from pathlib import Path

import pandas as pd

from src.contracts.phase3_exports import export_phase3_tables
from src.utils.config import load_league_config


def test_export_phase3_tables_writes_both_csvs(tmp_path: Path):
    roster_path = Path(__file__).parent / "fixtures" / "tiny_roster.csv"

    ledger_df, schedule_df = export_phase3_tables(
        roster_csv_path=str(roster_path),
        config=load_league_config(),
        output_dir=str(tmp_path),
    )

    ledger_path = tmp_path / "player_contract_ledger.csv"
    schedule_path = tmp_path / "contract_salary_schedule.csv"

    assert ledger_path.exists()
    assert schedule_path.exists()

    written_ledger = pd.read_csv(ledger_path)
    written_schedule = pd.read_csv(schedule_path)

    assert len(written_ledger) == len(ledger_df) == 5
    assert len(written_schedule) == len(schedule_df) == 10
    assert written_ledger.columns.tolist() == ledger_df.columns.tolist()
    assert written_schedule.columns.tolist() == schedule_df.columns.tolist()
