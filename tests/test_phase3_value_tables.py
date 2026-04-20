import math
from pathlib import Path

import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule
from src.contracts.phase3_value_tables import (
    _windowed_annual_avg,
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

    # Player One: years_remaining=2, so only tv_y0 and tv_y1 count
    player_one = forecast_df.loc[forecast_df["player"] == "Player One"].iloc[0]
    expected = 20.0 + 15.0 / 1.25
    assert math.isclose(player_one["pv_tv"], expected, rel_tol=1e-9)

    # Player Two: years_remaining=1, so only tv_y0 counts
    player_two = forecast_df.loc[forecast_df["player"] == "Player Two"].iloc[0]
    assert math.isclose(player_two["pv_tv"], 25.0, rel_tol=1e-9)

    # Free Agent Six is not in the ledger (years_remaining=0), so pv_tv must be 0
    assert "Free Agent Six" in set(forecast_df["player"])
    fa_six = forecast_df.loc[forecast_df["player"] == "Free Agent Six"].iloc[0]
    assert fa_six["pv_tv"] == 0.0


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


# ── Windowed annualized surplus tests ─────────────────────────────────────────

def test_windowed_annual_avg_basic():
    values = [20.0, 15.0, 10.0, 5.0]
    # Window=1, years_remaining=2 → only first value
    assert _windowed_annual_avg(values, 2, 1) == 20.0
    # Window=3, years_remaining=2 → min(3,2,4)=2 → avg of first 2
    assert math.isclose(_windowed_annual_avg(values, 2, 3), (20.0 + 15.0) / 2, rel_tol=1e-9)
    # Window=5, years_remaining=4 → min(5,4,4)=4 → avg of all 4
    assert math.isclose(_windowed_annual_avg(values, 4, 5), (20.0 + 15.0 + 10.0 + 5.0) / 4, rel_tol=1e-9)
    # years_remaining=0 → free agent → always 0.0
    assert _windowed_annual_avg(values, 0, 3) == 0.0


def test_surplus_table_has_all_windowed_columns():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    expected_cols = [
        "value_1yr", "cap_1yr", "surplus_1yr",
        "value_3yr_ann", "cap_3yr_ann", "surplus_3yr_ann",
        "value_5yr_ann", "cap_5yr_ann", "surplus_5yr_ann",
    ]
    for col in expected_cols:
        assert col in surplus_df.columns, f"Missing column: {col}"


def test_surplus_1yr_is_current_season_value_minus_cap():
    # Player Two: years_remaining=1, real_salary=20, tv_y0=25
    # cap_y0=20 (real_salary inflated by year_index=0 → unchanged)
    # value_1yr = tv_y0 = 25.0, cap_1yr = cap_y0 = 20.0, surplus_1yr = 5.0
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    player_two = surplus_df.loc[surplus_df["player"] == "Player Two"].iloc[0]
    assert math.isclose(player_two["value_1yr"], 25.0, rel_tol=1e-9)
    assert math.isclose(player_two["cap_1yr"], 20.0, rel_tol=1e-9)
    assert math.isclose(player_two["surplus_1yr"], 5.0, rel_tol=1e-9)


def test_windowed_surplus_capped_at_years_remaining():
    # Player One: years_remaining=2, tv=[20,15,10,5], cap=[10,11,0,0]
    # 3yr window: min(3,2,4)=2 → avg of first 2 years
    # value_3yr_ann = (20+15)/2 = 17.5, cap_3yr_ann = (10+11)/2 = 10.5, surplus = 7.0
    # 5yr window: min(5,2,4)=2 → same as 3yr since capped at years_remaining
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    player_one = surplus_df.loc[surplus_df["player"] == "Player One"].iloc[0]
    assert math.isclose(player_one["value_3yr_ann"], (20.0 + 15.0) / 2, rel_tol=1e-9)
    assert math.isclose(player_one["cap_3yr_ann"], (10.0 + 11.0) / 2, rel_tol=1e-9)
    assert math.isclose(player_one["surplus_3yr_ann"], player_one["value_3yr_ann"] - player_one["cap_3yr_ann"], rel_tol=1e-9)
    # 5yr is capped at 2 years (years_remaining), so same result
    assert math.isclose(player_one["value_5yr_ann"], player_one["value_3yr_ann"], rel_tol=1e-9)
    assert math.isclose(player_one["surplus_5yr_ann"], player_one["surplus_3yr_ann"], rel_tol=1e-9)


def test_windowed_surplus_surplus_derivation_matches_value_minus_cap():
    # Check that surplus_Xyr == value_Xyr - cap_Xyr for all windows and all players.
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    for _, row in surplus_df.iterrows():
        assert math.isclose(row["surplus_1yr"], row["value_1yr"] - row["cap_1yr"], rel_tol=1e-9)
        assert math.isclose(row["surplus_3yr_ann"], row["value_3yr_ann"] - row["cap_3yr_ann"], rel_tol=1e-9)
        assert math.isclose(row["surplus_5yr_ann"], row["value_5yr_ann"] - row["cap_5yr_ann"], rel_tol=1e-9)


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


def test_team_cap_health_dashboard_includes_windowed_surplus_totals():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    dashboard_df = build_team_cap_health_dashboard(ledger_df, forecast_df, economics_df, surplus_df)

    windowed_cols = [
        "total_value_1yr", "total_cap_1yr", "total_surplus_1yr",
        "total_value_3yr_ann", "total_cap_3yr_ann", "total_surplus_3yr_ann",
        "total_value_5yr_ann", "total_cap_5yr_ann", "total_surplus_5yr_ann",
    ]
    for col in windowed_cols:
        assert col in dashboard_df.columns, f"Missing dashboard column: {col}"

    # Team A: Player One (surplus_1yr=10) + Player Two (surplus_1yr=5) = 15
    team_a = dashboard_df.loc[dashboard_df["team"] == "A"].iloc[0]
    expected_1yr = surplus_df.loc[surplus_df["team"] == "A", "surplus_1yr"].sum()
    assert math.isclose(team_a["total_surplus_1yr"], expected_1yr, rel_tol=1e-9)

    # 3yr and 5yr totals should be sums of per-player annualized surplus.
    expected_3yr = surplus_df.loc[surplus_df["team"] == "A", "surplus_3yr_ann"].sum()
    assert math.isclose(team_a["total_surplus_3yr_ann"], expected_3yr, rel_tol=1e-9)


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


# ── Contract Value columns ────────────────────────────────────────────────────


def test_contract_surplus_includes_years_remaining():
    # years_remaining must be present and match the ledger values.
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    assert "years_remaining" in surplus_df.columns
    player_one = surplus_df.loc[surplus_df["player"] == "Player One"].iloc[0]
    player_two = surplus_df.loc[surplus_df["player"] == "Player Two"].iloc[0]
    assert int(player_one["years_remaining"]) == 2
    assert int(player_two["years_remaining"]) == 1


def test_contract_surplus_includes_per_year_columns():
    # tv_y{i}, cap_y{i}, surplus_y{i} must be present and surplus_y{i} == tv_y{i} - cap_y{i}.
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    for i in range(4):
        assert f"tv_y{i}" in surplus_df.columns
        assert f"cap_y{i}" in surplus_df.columns
        assert f"surplus_y{i}" in surplus_df.columns

    for _, row in surplus_df.iterrows():
        for i in range(4):
            assert math.isclose(row[f"surplus_y{i}"], row[f"tv_y{i}"] - row[f"cap_y{i}"], rel_tol=1e-9)


def test_contract_total_value_sums_over_contract_years_only():
    # Player One: years_remaining=2, tv=[20,15,10,5]
    # contract_total_value = tv_y0 + tv_y1 = 20 + 15 = 35 (not tv_y2 or tv_y3)
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    player_one = surplus_df.loc[surplus_df["player"] == "Player One"].iloc[0]
    assert math.isclose(player_one["contract_total_value"], 20.0 + 15.0, rel_tol=1e-9)

    # Player Two: years_remaining=1, tv_y0=25
    player_two = surplus_df.loc[surplus_df["player"] == "Player Two"].iloc[0]
    assert math.isclose(player_two["contract_total_value"], 25.0, rel_tol=1e-9)


def test_contract_avg_value_is_total_divided_by_years():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    for _, row in surplus_df.iterrows():
        yr = int(row["years_remaining"])
        if yr > 0:
            assert math.isclose(row["contract_avg_value"], row["contract_total_value"] / yr, rel_tol=1e-9)
            assert math.isclose(row["contract_avg_cap"], row["contract_total_cap"] / yr, rel_tol=1e-9)


def test_contract_total_surplus_is_total_value_minus_total_cap():
    ledger_df, schedule_df, config = _build_base_inputs()
    forecast_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=_tv_inputs())
    economics_df = build_contract_economics(ledger_df, schedule_df, config)
    surplus_df = build_contract_surplus_table(forecast_df, economics_df)

    for _, row in surplus_df.iterrows():
        assert math.isclose(
            row["contract_total_surplus"],
            row["contract_total_value"] - row["contract_total_cap"],
            rel_tol=1e-9,
        )
        assert math.isclose(
            row["contract_avg_surplus"],
            row["contract_avg_value"] - row["contract_avg_cap"],
            rel_tol=1e-9,
        )
