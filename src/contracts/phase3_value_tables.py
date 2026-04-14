from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.contracts.dead_money import (
    dead_money_active_roster_cut_nominal,
    dead_money_active_roster_cut_pv,
)


TV_PATH_COLUMNS = ["tv_y0", "tv_y1", "tv_y2", "tv_y3"]
PLAYER_KEY_COLUMNS = ["player", "team", "position"]
OPTIONAL_BOOLEAN_COLUMNS = ["has_been_optioned", "option_eligible"]


def _discounted_present_value(values: list[float], discount_rate: float) -> float:
    return float(sum(float(value) / ((1.0 + discount_rate) ** idx) for idx, value in enumerate(values)))


def _coerce_optional_bool_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    return df[column].fillna(False).astype(bool)


def _build_tv_path_columns(tv_df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    working = tv_df.copy()
    explicit_cols = [col for col in TV_PATH_COLUMNS if col in working.columns]
    if len(explicit_cols) == len(TV_PATH_COLUMNS):
        for col in TV_PATH_COLUMNS:
            working[col] = pd.to_numeric(working[col], errors="raise").astype(float)
        return working, "explicit_path"

    for baseline_col in ("tv_baseline", "esv_hat", "esv"):
        if baseline_col in working.columns:
            baseline = pd.to_numeric(working[baseline_col], errors="raise").astype(float)
            for col in TV_PATH_COLUMNS:
                working[col] = baseline
            return working, f"flat_{baseline_col}"

    for col in TV_PATH_COLUMNS:
        working[col] = 0.0
    return working, "zero_default"


def build_production_value_forecast(
    ledger_df: pd.DataFrame,
    config: dict[str, Any],
    tv_inputs_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build Phase 3 Table 3 from a 4-year TV path and dynasty discounting."""
    discount_rate = float(config["cap"]["discount_rate"])

    if tv_inputs_df is None:
        base = ledger_df[PLAYER_KEY_COLUMNS].drop_duplicates().copy()
        working, tv_source = _build_tv_path_columns(base)
    else:
        required_keys = set(PLAYER_KEY_COLUMNS)
        missing = sorted(required_keys - set(tv_inputs_df.columns))
        if missing:
            raise ValueError(f"TV inputs missing required columns: {missing}")
        working, tv_source = _build_tv_path_columns(tv_inputs_df)
        working = working.copy()
        for col in PLAYER_KEY_COLUMNS:
            working[col] = working[col]

    working["pv_tv"] = working[TV_PATH_COLUMNS].apply(
        lambda row: _discounted_present_value(row.tolist(), discount_rate),
        axis=1,
    )
    working["tv_source"] = tv_source
    return working[PLAYER_KEY_COLUMNS + TV_PATH_COLUMNS + ["pv_tv", "tv_source"]].drop_duplicates(
        subset=PLAYER_KEY_COLUMNS,
        keep="first",
    ).reset_index(drop=True)


def build_contract_economics(
    ledger_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Build Phase 3 Table 4 from real-salary schedules and league dead-money rules."""
    annual_inflation = float(config["cap"]["annual_inflation"])
    discount_rate = float(config["cap"]["discount_rate"])
    dead_money_cfg = config["dead_money"]["active_roster_cut"]
    current_year_percent = float(dead_money_cfg["current_year_percent"])
    future_year_percent = float(dead_money_cfg["future_year_percent"])

    capped = schedule_df.loc[schedule_df["year_index"].between(0, 3)].copy()
    cap_wide = (
        capped.assign(cap_column=capped["year_index"].map(lambda idx: f"cap_y{int(idx)}"))
        .pivot_table(
            index=PLAYER_KEY_COLUMNS,
            columns="cap_column",
            values="cap_hit_real",
            aggfunc="first",
        )
        .reset_index()
    )

    for col in [f"cap_y{idx}" for idx in range(4)]:
        if col not in cap_wide.columns:
            cap_wide[col] = 0.0
        cap_wide[col] = cap_wide[col].fillna(0.0).astype(float)

    schedule_meta = (
        schedule_df.groupby(PLAYER_KEY_COLUMNS, as_index=False)
        .agg(
            schedule_source=("schedule_source", lambda s: "mixed" if len(set(s.dropna())) > 1 else s.iloc[0]),
            needs_schedule_validation=("needs_schedule_validation", "max"),
        )
    )
    schedule_meta["needs_schedule_validation"] = schedule_meta["needs_schedule_validation"].astype(bool)

    ledger_subset = ledger_df[
        PLAYER_KEY_COLUMNS + ["current_salary", "real_salary", "years_remaining"]
    ].copy()
    economics = ledger_subset.merge(cap_wide, on=PLAYER_KEY_COLUMNS, how="left").merge(
        schedule_meta,
        on=PLAYER_KEY_COLUMNS,
        how="left",
    )
    for col in [f"cap_y{idx}" for idx in range(4)]:
        economics[col] = economics[col].fillna(0.0).astype(float)

    economics["pv_cap"] = economics[[f"cap_y{idx}" for idx in range(4)]].apply(
        lambda row: _discounted_present_value(row.tolist(), discount_rate),
        axis=1,
    )
    economics["cap_today_current"] = economics["current_salary"].astype(float)
    economics["dead_money_cut_now_nominal"] = economics.apply(
        lambda row: dead_money_active_roster_cut_nominal(
            real_salary=float(row["real_salary"]),
            years_remaining=int(row["years_remaining"]),
            inflation=annual_inflation,
            current_year_percent=current_year_percent,
            future_year_percent=future_year_percent,
        ),
        axis=1,
    )
    economics["dead_money_cut_now_pv"] = economics.apply(
        lambda row: dead_money_active_roster_cut_pv(
            real_salary=float(row["real_salary"]),
            years_remaining=int(row["years_remaining"]),
            inflation=annual_inflation,
            discount_rate=discount_rate,
            current_year_percent=current_year_percent,
            future_year_percent=future_year_percent,
        ),
        axis=1,
    )

    return economics[
        PLAYER_KEY_COLUMNS
        + ["current_salary", "real_salary", "years_remaining", "cap_today_current"]
        + [f"cap_y{idx}" for idx in range(4)]
        + [
            "pv_cap",
            "dead_money_cut_now_nominal",
            "dead_money_cut_now_pv",
            "schedule_source",
            "needs_schedule_validation",
        ]
    ].reset_index(drop=True)


def build_contract_surplus_table(
    production_value_df: pd.DataFrame,
    contract_economics_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build Phase 3 Table 5 as the ESV-unit contract surplus bridge.

    ``surplus_value = pv_tv - pv_cap``

    .. note::
        Surplus is a heuristic comparison of demand-based TV (Phase 2 ADP→ESV
        regression, enriched with age-curve and delta corrections in Phase 3)
        against cap-accounting present value.  These two quantities are not on
        the same cardinal scale — ``pv_tv`` is denominated in ESV-equivalent
        dollars while ``pv_cap`` is nominal cap dollars discounted at the
        league discount rate.  A positive surplus therefore indicates *relative
        opportunity* (the player appears under-contracted versus their expected
        production value), not a risk-free arbitrage.  Cross-position and
        cross-season comparisons should be made with awareness of this
        approximation.
    """
    merged = production_value_df.merge(
        contract_economics_df[
            PLAYER_KEY_COLUMNS + ["pv_cap", "cap_today_current", "dead_money_cut_now_nominal", "dead_money_cut_now_pv", "needs_schedule_validation"]
        ],
        on=PLAYER_KEY_COLUMNS,
        how="inner",
    )
    merged["surplus_value"] = merged["pv_tv"] - merged["pv_cap"]
    return merged[
        PLAYER_KEY_COLUMNS
        + ["pv_tv", "pv_cap", "surplus_value", "cap_today_current", "dead_money_cut_now_nominal", "dead_money_cut_now_pv", "needs_schedule_validation"]
    ].reset_index(drop=True)


def build_team_cap_health_dashboard(
    ledger_df: pd.DataFrame,
    production_value_df: pd.DataFrame,
    contract_economics_df: pd.DataFrame,
    contract_surplus_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build Phase 3 Table 6 with present-cap and forward-burden rollups."""
    player_level = (
        ledger_df[PLAYER_KEY_COLUMNS + ["current_salary", "real_salary"]]
        .merge(production_value_df[PLAYER_KEY_COLUMNS + ["pv_tv"]], on=PLAYER_KEY_COLUMNS, how="left")
        .merge(
            contract_economics_df[
                PLAYER_KEY_COLUMNS
                + [f"cap_y{idx}" for idx in range(4)]
                + ["pv_cap", "dead_money_cut_now_nominal", "dead_money_cut_now_pv", "needs_schedule_validation"]
            ],
            on=PLAYER_KEY_COLUMNS,
            how="left",
        )
        .merge(contract_surplus_df[PLAYER_KEY_COLUMNS + ["surplus_value"]], on=PLAYER_KEY_COLUMNS, how="left")
    )

    player_level["needs_schedule_validation"] = player_level["needs_schedule_validation"].fillna(False).astype(bool)

    dashboard = player_level.groupby("team", as_index=False).agg(
        current_cap_usage=("current_salary", "sum"),
        real_cap_y0=("cap_y0", "sum"),
        real_cap_y1=("cap_y1", "sum"),
        real_cap_y2=("cap_y2", "sum"),
        real_cap_y3=("cap_y3", "sum"),
        total_pv_cap=("pv_cap", "sum"),
        total_pv_tv=("pv_tv", "sum"),
        total_surplus=("surplus_value", "sum"),
        dead_money_cut_now_nominal=("dead_money_cut_now_nominal", "sum"),
        dead_money_cut_now_pv=("dead_money_cut_now_pv", "sum"),
        validation_player_count=("needs_schedule_validation", "sum"),
    )

    validation_rows = player_level.loc[player_level["needs_schedule_validation"]].groupby("team", as_index=False).agg(
        validation_current_salary=("current_salary", "sum"),
        validation_real_salary=("real_salary", "sum"),
        validation_pv_cap=("pv_cap", "sum"),
    )
    dashboard = dashboard.merge(validation_rows, on="team", how="left")
    for col in ["validation_current_salary", "validation_real_salary", "validation_pv_cap"]:
        dashboard[col] = dashboard[col].fillna(0.0).astype(float)

    return dashboard.sort_values("team").reset_index(drop=True)


def _build_shortlist(
    ledger_df: pd.DataFrame,
    contract_surplus_df: pd.DataFrame,
    *,
    instrument_type: str,
    eligibility_col: str,
    additional_filter_col: str | None = None,
    final_year_only: bool = False,
) -> pd.DataFrame:
    """Filter players eligible for a contract instrument who have positive surplus.

    Instrument recommendations are based solely on:
      - ``eligibility_col`` flag (e.g. extension_eligible, tag_eligible)
      - ``contract_eligible`` flag
      - ``surplus_value > 0``  (TV present value exceeds cap present value)

    Age-curve risk and positional depth are intentionally NOT used as
    filters here because:
      (a) Dynasty TV already prices multi-year decline via the position age
          curve in Phase 2; a player approaching their decline will already
          have lower pv_tv.
      (b) Short extensions (1–2 years) can still be value-positive for older
          players depending on their contract situation — hard-coding an age
          gate would prevent surfacing legitimate opportunities.

    Analysts should review player age and situation context before acting on
    any recommendation produced by this shortlist.
    """
    merged = ledger_df.copy()
    merged["has_been_optioned"] = _coerce_optional_bool_column(merged, "has_been_optioned")
    merged["option_eligible"] = _coerce_optional_bool_column(merged, "option_eligible")
    if "needs_schedule_validation" in merged.columns:
        merged = merged.drop(columns=["needs_schedule_validation"])
    merged = merged.merge(
        contract_surplus_df[PLAYER_KEY_COLUMNS + ["pv_tv", "pv_cap", "surplus_value", "needs_schedule_validation"]],
        on=PLAYER_KEY_COLUMNS,
        how="inner",
    )

    eligible = merged[eligibility_col].fillna(False).astype(bool) & merged["contract_eligible"].fillna(False).astype(bool)
    if additional_filter_col is not None:
        eligible = eligible & ~merged[additional_filter_col].fillna(False).astype(bool)
    if final_year_only:
        eligible = eligible & merged["years_remaining"].eq(1)
    shortlisted = merged.loc[eligible & (merged["surplus_value"] > 0)].copy()
    shortlisted["instrument_type"] = instrument_type
    return shortlisted[
        ["instrument_type"]
        + PLAYER_KEY_COLUMNS
        + ["current_salary", "real_salary", "extension_salary", "years_remaining", "pv_tv", "pv_cap", "surplus_value", "needs_schedule_validation"]
    ].sort_values(["team", "surplus_value"], ascending=[True, False]).reset_index(drop=True)


def build_instrument_candidate_shortlists(
    ledger_df: pd.DataFrame,
    contract_surplus_df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build Phase 3 Table 7 shortlist outputs for extensions, tags, and options."""
    extension_df = _build_shortlist(
        ledger_df,
        contract_surplus_df,
        instrument_type="extension",
        eligibility_col="extension_eligible",
    )
    tag_df = _build_shortlist(
        ledger_df,
        contract_surplus_df,
        instrument_type="tag",
        eligibility_col="tag_eligible",
        additional_filter_col="has_been_tagged",
        final_year_only=True,
    )
    option_df = _build_shortlist(
        ledger_df,
        contract_surplus_df,
        instrument_type="option",
        eligibility_col="option_eligible",
        additional_filter_col="has_been_optioned",
    )

    return {
        "extension_candidates": extension_df,
        "tag_candidates": tag_df,
        "option_candidates": option_df,
        "instrument_candidates": pd.concat([extension_df, tag_df, option_df], ignore_index=True),
    }


def build_phase3_tables_3_to_7(
    ledger_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    config: dict[str, Any],
    tv_inputs_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the Phase 3 value outputs for Tables 3 through 7."""
    production_value_df = build_production_value_forecast(ledger_df, config, tv_inputs_df=tv_inputs_df)
    contract_economics_df = build_contract_economics(ledger_df, schedule_df, config)
    contract_surplus_df = build_contract_surplus_table(production_value_df, contract_economics_df)
    team_dashboard_df = build_team_cap_health_dashboard(
        ledger_df,
        production_value_df,
        contract_economics_df,
        contract_surplus_df,
    )
    shortlists = build_instrument_candidate_shortlists(ledger_df, contract_surplus_df)

    return {
        "production_value_forecast": production_value_df,
        "contract_economics": contract_economics_df,
        "contract_surplus": contract_surplus_df,
        "team_cap_health_dashboard": team_dashboard_df,
        **shortlists,
    }


def load_tv_inputs(path: str | Path | None) -> pd.DataFrame | None:
    """Load TV input CSV if present, otherwise return None."""
    if path is None:
        return None
    path_obj = Path(path)
    if not path_obj.exists():
        return None
    return pd.read_csv(path_obj)
