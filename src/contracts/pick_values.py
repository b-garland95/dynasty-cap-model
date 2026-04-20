"""Calendar-aligned value metrics for draft picks.

Design
------
All picks are assumed to have zero surplus: projected_value == contract_salary
for every year of the rookie contract.  The cap path is built from the rookie
scale salary using the same +10 %/yr rounded-up escalation as player contracts.

Metrics are *calendar-aligned* to the current season so that a 2027 pick
contributes nothing to "This Yr Value" (window position 0) but does appear in
the 3-Year Value window (positions 1–2).

  offset = pick_year - current_season

  window_val[p] = cap_path[p - offset]  if 0 <= p - offset < years_remaining
                = 0                      otherwise

  value_1yr      = window_val[0]
  value_3yr_ann  = mean(window_val[0:3])
  pv             = Σ cap_path[i] / (1 + discount_rate)^(offset + i)

All surplus fields are 0 by assumption.
"""

from __future__ import annotations

from typing import Any

from src.contracts.schedule_builder import build_rounded_salary_path


def pick_base_salary(rnd: int, slot: int | None, rookie_scale: dict[str, Any]) -> float:
    """Return the base salary for a pick.

    Round 1, slot known  → slot-specific salary from rookie_scale["round1"]
    Round 1, slot None   → simple average of all round-1 salaries
    Rounds 2–4           → flat salary (slot irrelevant)
    """
    if rnd == 1:
        round1: dict[str, int] = rookie_scale["round1"]
        if slot is not None:
            return float(round1[f"1.{slot:02d}"])
        return sum(round1.values()) / len(round1)
    return float(rookie_scale[f"round{rnd}_salary"])


def pick_value_metrics(
    base_salary: float,
    pick_year: int,
    current_season: int,
    config: dict[str, Any],
) -> dict[str, float]:
    """Return calendar-aligned value/cap/surplus metrics for a pick.

    All surplus fields are 0 (value == cap by design).
    The returned dict mirrors the column schema of contract_surplus.csv so the
    trade-proposal view can treat picks and players uniformly.
    """
    rookie = config["rookie_scale"]
    cap_cfg = config["cap"]

    years_remaining: int = int(rookie["contract_years"])
    inflation: float = float(cap_cfg["annual_inflation"])
    discount_rate: float = float(cap_cfg["discount_rate"])
    offset: int = pick_year - current_season

    # Contract-relative cap (and TV) path.
    cap_path = build_rounded_salary_path(base_salary, years_remaining, inflation)

    # Pad contract path to 4 slots for cap_y0..cap_y3 / tv_y0..tv_y3 fields.
    padded = cap_path + [0.0] * (4 - len(cap_path))
    cap_y0, cap_y1, cap_y2, cap_y3 = padded[:4]

    # Calendar-window helper: value at window position p (0 = current season).
    def _win(p: int) -> float:
        idx = p - offset
        if 0 <= idx < len(cap_path):
            return cap_path[idx]
        return 0.0

    # 1-year window (current season only).
    value_1yr = _win(0)

    # 3-year window.
    w3 = [_win(p) for p in range(3)]
    value_3yr_ann = sum(w3) / 3.0

    # 5-year window (capped at 4 forecast years per contract length).
    forecast_cap = min(4, years_remaining)
    w5 = [_win(p) for p in range(5)]
    non_zero_5 = [v for i, v in enumerate(w5) if i - offset < forecast_cap]
    value_5yr_ann = sum(w5) / 5.0

    # Present value: discount over the actual contract years, shifted by offset.
    pv = sum(
        cap_path[i] / (1.0 + discount_rate) ** (offset + i)
        for i in range(len(cap_path))
    )

    contract_total = sum(cap_path)
    contract_avg = contract_total / years_remaining if years_remaining > 0 else 0.0

    return {
        # Contract-relative year columns (match contract_surplus.csv schema).
        "cap_y0": cap_y0,
        "cap_y1": cap_y1,
        "cap_y2": cap_y2,
        "cap_y3": cap_y3,
        "tv_y0": cap_y0,
        "tv_y1": cap_y1,
        "tv_y2": cap_y2,
        "tv_y3": cap_y3,
        # Present value (same for cap and TV since surplus = 0).
        "pv_cap": pv,
        "pv_tv": pv,
        "surplus_value": 0.0,
        # Calendar-aligned windowed metrics.
        "value_1yr": value_1yr,
        "cap_1yr": value_1yr,
        "surplus_1yr": 0.0,
        "value_3yr_ann": value_3yr_ann,
        "cap_3yr_ann": value_3yr_ann,
        "surplus_3yr_ann": 0.0,
        "value_5yr_ann": value_5yr_ann,
        "cap_5yr_ann": value_5yr_ann,
        "surplus_5yr_ann": 0.0,
        # Per-year surplus (always 0).
        "surplus_y0": 0.0,
        "surplus_y1": 0.0,
        "surplus_y2": 0.0,
        "surplus_y3": 0.0,
        # Contract-length aggregates.
        "contract_total_value": contract_total,
        "contract_total_cap": contract_total,
        "contract_total_surplus": 0.0,
        "contract_avg_value": contract_avg,
        "contract_avg_cap": contract_avg,
        "contract_avg_surplus": 0.0,
        # Metadata.
        "years_remaining": years_remaining,
        "pick_year": pick_year,
        "offset_from_current": offset,
    }
