from pathlib import Path

from src.contracts.phase3_qa import build_phase3_qa_summary, format_phase3_qa_summary
from src.contracts.phase3_tables import build_contract_ledger, build_salary_schedule
from src.utils.config import load_league_config


def test_phase3_qa_summary_uses_ledger_and_schedule_outputs():
    roster_path = Path(__file__).parent / "fixtures" / "tiny_roster.csv"
    ledger_df = build_contract_ledger(str(roster_path))
    schedule_df = build_salary_schedule(ledger_df, load_league_config())

    summary = build_phase3_qa_summary(ledger_df, schedule_df, top_n=3)

    assert summary["row_counts"] == {"ledger_rows": 5, "schedule_rows": 10}
    assert summary["years_range"] == {"min": 1, "max": 3}
    assert int(summary["team_player_counts"].loc["B"]) == 3
    assert float(summary["team_current_salary"].loc["A"]) == 30.0
    assert float(summary["team_real_salary"].loc["B"]) == 16.0
    assert len(summary["validation_players"]) == 2
    assert int(summary["team_validation_counts"].loc["B"]) == 2
    assert summary["boolean_counts"]["has_been_extended"] == {False: 3, True: 2}
    assert summary["numeric_nulls"] == {
        "current_salary": 0,
        "real_salary": 0,
        "extension_salary": 0,
        "years_remaining": 0,
    }

    report = format_phase3_qa_summary(summary)
    assert "ROW_COUNTS" in report
    assert "VALIDATION_PLAYERS" in report
    assert "Player Four" in report
    # The formatted report must cover all major QA sections
    for section in ("BOOLEAN_COUNTS", "NUMERIC_NULLS", "YEARS_RANGE"):
        assert section in report, f"Expected section {section!r} in QA report"
    # Team cap salary check: team A has Player One ($20 current) + Player Two ($20 current) = $30
    assert float(summary["team_current_salary"].loc["A"]) == 30.0
    # Numeric nulls must be zero for all key salary fields
    for field in ("current_salary", "real_salary", "extension_salary", "years_remaining"):
        assert summary["numeric_nulls"][field] == 0, f"Unexpected nulls in {field}"
