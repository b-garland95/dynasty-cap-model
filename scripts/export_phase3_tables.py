from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.phase3_exports import export_phase3_tables
from src.utils.config import load_league_config

DEFAULT_ROSTER_CSV = REPO_ROOT / "data" / "raw" / "roster_exports" / "lbb_rosters_2025.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "interim" / "rosters"
DEFAULT_SCHEDULE_OVERRIDES_CSV = REPO_ROOT / "data" / "raw" / "roster_exports" / "contract_salary_schedule_overrides.csv"
DEFAULT_TV_INPUTS_CSV = REPO_ROOT / "data" / "interim" / "phase3" / "tv_inputs.csv"


def main() -> int:
    roster_csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROSTER_CSV
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR

    if not roster_csv_path.exists():
        print("Usage: python scripts/export_phase3_tables.py <roster_csv_path> [output_dir]")
        print(f"Default roster CSV not found at {roster_csv_path}")
        return 1

    exported = export_phase3_tables(
        roster_csv_path=str(roster_csv_path),
        config=load_league_config(),
        output_dir=str(output_dir),
        schedule_overrides_path=str(DEFAULT_SCHEDULE_OVERRIDES_CSV),
        tv_inputs_path=str(DEFAULT_TV_INPUTS_CSV),
    )

    print(f"Wrote {len(exported['player_contract_ledger'])} ledger rows to {output_dir / 'player_contract_ledger.csv'}")
    print(f"Wrote {len(exported['contract_salary_schedule'])} schedule rows to {output_dir / 'contract_salary_schedule.csv'}")
    print(f"Wrote {len(exported['production_value_forecast'])} rows to {output_dir / 'production_value_forecast.csv'}")
    print(f"Wrote {len(exported['contract_economics'])} rows to {output_dir / 'contract_economics.csv'}")
    print(f"Wrote {len(exported['contract_surplus'])} rows to {output_dir / 'contract_surplus.csv'}")
    print(f"Wrote {len(exported['team_cap_health_dashboard'])} rows to {output_dir / 'team_cap_health_dashboard.csv'}")
    print(f"Wrote {len(exported['instrument_candidates'])} rows to {output_dir / 'instrument_candidates.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
