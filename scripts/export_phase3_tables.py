from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.phase3_exports import export_phase3_tables
from src.utils.config import load_league_config


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_phase3_tables.py <roster_csv_path> [output_dir]")
        return 1

    roster_csv_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO_ROOT / "data" / "processed"

    ledger_df, schedule_df = export_phase3_tables(
        roster_csv_path=str(roster_csv_path),
        config=load_league_config(),
        output_dir=str(output_dir),
    )

    print(f"Wrote {len(ledger_df)} ledger rows to {output_dir / 'player_contract_ledger.csv'}")
    print(f"Wrote {len(schedule_df)} schedule rows to {output_dir / 'contract_salary_schedule.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
