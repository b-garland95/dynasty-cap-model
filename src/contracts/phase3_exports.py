from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.contracts.free_agent_market import build_free_agent_market_table
from src.contracts.phase3_tables import (
    apply_schedule_overrides,
    build_contract_ledger,
    build_salary_schedule,
    load_schedule_overrides,
)
from src.contracts.phase3_value_tables import build_phase3_tables_3_to_7, load_tv_inputs
from src.contracts.team_adjustments import load_team_adjustments


def export_phase3_tables(
    roster_csv_path: str,
    config: dict[str, Any],
    output_dir: str,
    schedule_overrides_path: str | None = None,
    tv_inputs_path: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Build and export Phase 3 Tables 1 through 7 as CSV files."""
    ledger_df = build_contract_ledger(
        roster_csv_path,
        ps_cap_percent=float(config["practice_squad"]["cap_percent"]),
    )
    schedule_df = build_salary_schedule(ledger_df, config)
    schedule_df = apply_schedule_overrides(
        schedule_df,
        load_schedule_overrides(schedule_overrides_path),
    )
    tv_inputs_df = load_tv_inputs(tv_inputs_path)
    downstream_tables = build_phase3_tables_3_to_7(
        ledger_df,
        schedule_df,
        config,
        tv_inputs_df=tv_inputs_df,
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ledger_df.to_csv(output_path / "player_contract_ledger.csv", index=False)
    schedule_df.to_csv(output_path / "contract_salary_schedule.csv", index=False)
    downstream_tables["production_value_forecast"].to_csv(output_path / "production_value_forecast.csv", index=False)
    downstream_tables["contract_economics"].to_csv(output_path / "contract_economics.csv", index=False)
    downstream_tables["contract_surplus"].to_csv(output_path / "contract_surplus.csv", index=False)
    downstream_tables["team_cap_health_dashboard"].to_csv(output_path / "team_cap_health_dashboard.csv", index=False)
    downstream_tables["extension_candidates"].to_csv(output_path / "extension_candidates.csv", index=False)
    downstream_tables["tag_candidates"].to_csv(output_path / "tag_candidates.csv", index=False)
    downstream_tables["option_candidates"].to_csv(output_path / "option_candidates.csv", index=False)
    downstream_tables["instrument_candidates"].to_csv(output_path / "instrument_candidates.csv", index=False)
    if not downstream_tables["team_rav_summary"].empty:
        downstream_tables["team_rav_summary"].to_csv(output_path / "team_rav_summary.csv", index=False)
    if not downstream_tables["trade_gap_screen"].empty:
        downstream_tables["trade_gap_screen"].to_csv(output_path / "trade_gap_screen.csv", index=False)

    fa_tables: dict[str, pd.DataFrame] = {}
    if tv_inputs_df is not None:
        team_adj = load_team_adjustments()
        fa_market_df, fa_env = build_free_agent_market_table(
            tv_df=tv_inputs_df,
            cap_health_df=downstream_tables["team_cap_health_dashboard"],
            config=config,
            team_adjustments=team_adj,
            include_rostered=False,
        )
        fa_market_df.to_csv(output_path / "free_agent_market.csv", index=False)
        fa_env_df = pd.DataFrame([fa_env])
        fa_env_df.to_csv(output_path / "fa_market_environment.csv", index=False)

        # Attach per-team effective cap to the cap health dashboard.
        # effective_cap_remaining = cap_remaining / market_multiplier so that
        # inflated markets reduce purchasing power rather than inflating player values.
        multiplier = fa_env["market_multiplier"]
        base_cap = float(config["cap"]["base_cap"])
        cap_dash = downstream_tables["team_cap_health_dashboard"].copy()

        def _cap_remaining(row: pd.Series) -> float:
            t = team_adj.get(str(row["team"]), {})
            raw = (
                base_cap
                - float(row["current_cap_usage"])
                - float(t.get("dead_money", 0.0))
                - float(t.get("cap_transactions", 0.0))
                + float(t.get("rollover", 0.0))
            )
            return max(raw, 0.0)

        cap_dash["cap_remaining"] = cap_dash.apply(_cap_remaining, axis=1)
        cap_dash["effective_cap_remaining"] = cap_dash["cap_remaining"] / multiplier
        downstream_tables["team_cap_health_dashboard"] = cap_dash
        cap_dash.to_csv(output_path / "team_cap_health_dashboard.csv", index=False)

        fa_tables = {"free_agent_market": fa_market_df, "fa_market_environment": fa_env_df}

    return {
        "player_contract_ledger": ledger_df,
        "contract_salary_schedule": schedule_df,
        **downstream_tables,
        **fa_tables,
    }
