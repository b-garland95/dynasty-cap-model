import math
from pathlib import Path

import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule
from src.contracts.phase3_value_tables import (
    build_contract_economics,
    build_contract_surplus_table,
    build_instrument_candidate_shortlists,
    build_phase3_tables_3_to_7,
    build_production_value_forecast,
    build_team_cap_health_dashboard,
)
from src.utils.config import load_league_config


def _fixture_roster_path() -> str:
    return str(Path(__file__).parent / "fixtures" / "tiny_roster.csv")


def _build_base_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    ledger_df = build_contract_ledger(_fixture_roster_path())
    ledger_df["option_eligible"] = [False, False, False, False, True]
    ledger_df["has_been_optioned"] = False
    config = load_league_config()
    schedule_df = build_salary_schedule(ledger_df, config)
    return ledger_df, schedule_df, config


def _tv_inputs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player": "Player One", "team": "A", "position": "RB", "tv_y0": 20.0, "tv_y1": 15.0, "tv_y2": 10.0, "tv_y3": 5.0},
            {"player": "Player Two", "team": "A", "position": "QB", "tv_y0": 25.0, "tv_y1": 20.0, "tv_y2": 15.0, "tv_y3": 10.0},
            {"player": "Player Three", "team": "B", "position": "WR", "tv_y0": 3.0, "tv_y1": 3.0, "tv_y2": 3.0, "tv_y3": 3.0},
            {"player": "Player Four", "team": "B", "position": "RB", "tv_y0": 50.0, "tv_y1": 40.0, "tv_y2": 30.0, "tv_y3": 20.0},
            {"player": "Player Five", "team": "B", "position": "TE", "tv_y0": 8.0, "tv_y1": 8.0, "tv_y2": 8.0, "tv_y3": 8.0},
            {"player": "Free Agent Six", "team": "", "position": "WR", "tv_y0": 12.0, "tv_y1": 10.0, "tv_y2": 8.0, "tv_y3": 6.0},
        ]
    )


def test_build_production_value_forecast_uses_25pct_discounting():
    ledger_df, _, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())

    player_one = forecast_df.loc[forecast_df["player"] == "Player One"].iloc[0]
    expected = 20.0 + 15.0 / 1.25 + 10.0 / (1.25**2) + 5.0 / (1.25**3)
    assert math.isclose(player_one["pv_tv"], expected, rel_tol=1e-9)
    assert "Free Agent Six" in set(forecast_df["player"])


def test_contract_economics_uses_real_salary_not_current_salary():
    ledger_df, _, config = _build_base_inputs()
    ledger_df.loc[ledger_df["player"] == "Player One", "current_salary"] = 2.0
    schedule_df = build_salary_schedule(ledger_df, config)

    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    player_one = economics_df.loc[economics_df["player"] == "Player One"].iloc[0]

    assert player_one["cap_today_current"] == 2.0
    assert player_one["cap_y0"] == 10.0
    assert player_one["cap_y1"] == 11.0
    assert math.isclose(player_one["pv_cap"], 10.0 + 11.0 / 1.25, rel_tol=1e-9)


def test_contract_surplus_table_is_pv_tv_minus_pv_cap():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)

    surplus_df = build_contract_surplus_table(forecast_df, economics_df)
    player_two = surplus_df.loc[surplus_df["player"] == "Player Two"].iloc[0]

    assert math.isclose(player_two["surplus_value"], player_two["pv_tv"] - player_two["pv_cap"], rel_tol=1e-9)


def test_team_cap_health_dashboard_aggregates_team_rollups():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    dashboard_df = build_team_cap_health_dashboard(ledger_df, forecast_df, economics_df, surplus_df)
    team_a = dashboard_df.loc[dashboard_df["team"] == "A"].iloc[0]

    assert team_a["current_cap_usage"] == 30.0
    assert team_a["real_cap_y0"] == 30.0
    assert team_a["real_cap_y1"] == 11.0
    assert team_a["validation_player_count"] == 0
    assert math.isclose(team_a["total_surplus"], surplus_df.loc[surplus_df["team"] == "A", "surplus_value"].sum(), rel_tol=1e-9)


def test_instrument_shortlists_filter_to_surplus_positive_and_preserve_flags():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    shortlists = build_instrument_candidate_shortlists(ledger_df, surplus_df)

    assert shortlists["extension_candidates"]["player"].tolist() == ["Player One", "Player Four", "Player Five"]
    assert shortlists["tag_candidates"]["player"].tolist() == ["Player Two"]
    assert shortlists["option_candidates"]["player"].tolist() == ["Player Five"]

    player_four = shortlists["extension_candidates"].loc[shortlists["extension_candidates"]["player"] == "Player Four"].iloc[0]
    assert bool(player_four["needs_schedule_validation"]) is True


def test_build_phase3_tables_3_to_7_end_to_end_fixture():
    ledger_df, schedule_df, config = _build_base_inputs()
    tables = build_phase3_tables_3_to_7(ledger_df, schedule_df, config, tv_inputs_df=_tv_inputs())

    assert set(tables) == {
        "production_value_forecast",
        "contract_economics",
        "contract_surplus",
        "team_cap_health_dashboard",
        "extension_candidates",
        "tag_candidates",
        "option_candidates",
        "instrument_candidates",
    }
    assert len(tables["production_value_forecast"]) == 6
    assert len(tables["contract_economics"]) == 5
    assert len(tables["contract_surplus"]) == 5
    assert len(tables["team_cap_health_dashboard"]) == 2
    assert tables["instrument_candidates"]["instrument_type"].tolist() == [
        "extension",
        "extension",
        "extension",
        "tag",
        "option",
    ]
