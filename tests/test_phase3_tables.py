import math
from pathlib import Path

import pandas as pd

from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule
from src.contracts.schedule_builder import build_rounded_salary_path
from src.utils.config import load_league_config


def _fixture_roster_path() -> str:
    return str(Path(__file__).parent / "fixtures" / "tiny_roster.csv")


def test_build_contract_ledger_parsing_and_flags():
    ledger_df = build_contract_ledger(_fixture_roster_path())

    assert pd.api.types.is_float_dtype(ledger_df["current_salary"])
    assert pd.api.types.is_float_dtype(ledger_df["real_salary"])
    assert pd.api.types.is_float_dtype(ledger_df["extension_salary"])
    assert pd.api.types.is_integer_dtype(ledger_df["years_remaining"])

    player_one = ledger_df.loc[ledger_df["player"] == "Player One"].iloc[0]
    player_three = ledger_df.loc[ledger_df["player"] == "Player Three"].iloc[0]
    assert bool(player_three["ps_eligible"]) is True
    assert bool(player_three["has_been_extended"]) is False
    assert bool(player_three["has_been_tagged"]) is False
    assert bool(player_three["tag_eligible"]) is False

    player_one = ledger_df.loc[ledger_df["player"] == "Player One"].iloc[0]
    player_four = ledger_df.loc[ledger_df["player"] == "Player Four"].iloc[0]
    assert player_one["contract_type_bucket"] == "standard"
    assert bool(player_one["needs_schedule_validation"]) is False
    assert player_four["contract_type_bucket"] == "instrument_adjusted"
    assert bool(player_four["needs_schedule_validation"]) is True


def test_build_salary_schedule_values_and_shape():
    ledger_df = build_contract_ledger(_fixture_roster_path())
    config = load_league_config()
    schedule_df = build_salary_schedule(ledger_df, config)

    assert len(schedule_df) == 10

    player_one = schedule_df.loc[schedule_df["player"] == "Player One"].sort_values("year_index")
    assert player_one["cap_hit_real"].tolist() == [10.0, 11.0]
    assert (player_one["schedule_source"] == "standard_rule").all()
    assert not player_one["needs_schedule_validation"].any()

    player_four = schedule_df.loc[schedule_df["player"] == "Player Four"].sort_values("year_index")
    assert player_four["cap_hit_real"].tolist() == [8.0, 32.0]
    assert (player_four["schedule_source"] == "best_effort_instrument").all()
    assert player_four["needs_schedule_validation"].all()

    player_two = schedule_df.loc[schedule_df["player"] == "Player Two"]
    assert len(player_two) == 1
    assert int(player_two.iloc[0]["year_index"]) == 0

    for _, player_rows in schedule_df.groupby("player"):
        player_rows = player_rows.sort_values("year_index")
        year0 = player_rows.iloc[0]
        assert year0["cap_hit_current"] == year0["cap_hit_current"]
        if len(player_rows) > 1:
            for v in player_rows.iloc[1:]["cap_hit_current"].tolist():
                assert math.isnan(v)


def test_salary_schedule_rounds_up_each_future_year():
    rounded_path = build_rounded_salary_path(base_salary=5.0, years_remaining=4, annual_inflation=0.10)
    assert rounded_path == [5.0, 6.0, 7.0, 8.0]
