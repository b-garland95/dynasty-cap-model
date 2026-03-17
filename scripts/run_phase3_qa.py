from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.phase3_qa import build_phase3_qa_summary, format_phase3_qa_summary
from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule
from src.utils.config import load_league_config


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_phase3_qa.py <roster_csv_path>")
        return 1

    roster_csv_path = Path(sys.argv[1])
    ledger_df = build_contract_ledger(str(roster_csv_path))
    schedule_df = build_salary_schedule(ledger_df, load_league_config())
    summary = build_phase3_qa_summary(ledger_df, schedule_df)
    print(format_phase3_qa_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
