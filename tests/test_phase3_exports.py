from pathlib import Path

import pandas as pd

from src.contracts.phase3_exports import export_phase3_tables
from src.utils.config import load_league_config


def test_export_phase3_tables_writes_all_phase3_csvs(tmp_path: Path):
    roster_path = Path(__file__).parent / "fixtures" / "tiny_roster.csv"
    tv_inputs_path = tmp_path / "tv_inputs.csv"
    pd.DataFrame(
        [
            {"player": "Player One", "team": "A", "position": "RB", "esv_hat": 20.0},
            {"player": "Player Two", "team": "A", "position": "QB", "esv_hat": 25.0},
            {"player": "Player Three", "team": "B", "position": "WR", "esv_hat": 3.0},
            {"player": "Player Four", "team": "B", "position": "RB", "esv_hat": 50.0},
            {"player": "Player Five", "team": "B", "position": "TE", "esv_hat": 8.0},
        ]
    ).to_csv(tv_inputs_path, index=False)

    exported = export_phase3_tables(
        roster_csv_path=str(roster_path),
        config=load_league_config(),
        output_dir=str(tmp_path),
        tv_inputs_path=str(tv_inputs_path),
    )

    expected_files = {
        "player_contract_ledger": "player_contract_ledger.csv",
        "contract_salary_schedule": "contract_salary_schedule.csv",
        "production_value_forecast": "production_value_forecast.csv",
        "contract_economics": "contract_economics.csv",
        "contract_surplus": "contract_surplus.csv",
        "team_cap_health_dashboard": "team_cap_health_dashboard.csv",
        "extension_candidates": "extension_candidates.csv",
        "tag_candidates": "tag_candidates.csv",
        "option_candidates": "option_candidates.csv",
        "instrument_candidates": "instrument_candidates.csv",
    }

    for export_key, filename in expected_files.items():
        path = tmp_path / filename
        assert path.exists()
        written = pd.read_csv(path)
        assert written.columns.tolist() == exported[export_key].columns.tolist()

    assert len(exported["player_contract_ledger"]) == 5
    assert len(exported["contract_salary_schedule"]) == 10
    assert len(exported["production_value_forecast"]) == 5
    assert len(exported["team_cap_health_dashboard"]) == 2

    # Column-presence checks
    for col in ("player", "team", "position", "pv_cap", "dead_money_cut_now_nominal", "dead_money_cut_now_pv"):
        assert col in exported["contract_economics"].columns, f"Missing column in contract_economics: {col}"
    for col in ("player", "team", "position", "pv_tv", "pv_cap", "surplus_value"):
        assert col in exported["contract_surplus"].columns, f"Missing column in contract_surplus: {col}"

    # Escalation invariant: Player One has real_salary=10, years_remaining=2.
    # Year-1 cap hit must equal ceil(10 * 1.10) = 11.
    config = load_league_config()
    inflation = float(config["cap"]["annual_inflation"])
    import math
    expected_y1 = float(math.ceil(10.0 * (1.0 + inflation)))
    sched = exported["contract_salary_schedule"]
    p1_y1 = sched.loc[(sched["player"] == "Player One") & (sched["year_index"] == 1), "cap_hit_real"]
    assert len(p1_y1) == 1
    assert math.isclose(float(p1_y1.iloc[0]), expected_y1, abs_tol=1e-9), (
        f"Player One year-1 cap_hit_real={p1_y1.iloc[0]} != expected {expected_y1}"
    )
