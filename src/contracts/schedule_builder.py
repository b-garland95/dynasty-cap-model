from __future__ import annotations

import math
from typing import Any


def standard_cap_hits(real_salary: float, years_remaining: int, annual_inflation: float) -> list[float]:
    """Return standard escalator cap hits built from real salary."""
    return [real_salary * ((1.0 + annual_inflation) ** k) for k in range(years_remaining)]


def instrument_best_effort_cap_hits(
    real_salary: float,
    extension_salary: float,
    years_remaining: int,
    annual_inflation: float,
) -> list[float]:
    """Return best-effort cap hits for an instrument-adjusted contract."""
    if years_remaining <= 0:
        return []

    if extension_salary > 0.0:
        hits = [real_salary]
        for k in range(1, years_remaining):
            hits.append(extension_salary * ((1.0 + annual_inflation) ** (k - 1)))
        return hits

    return standard_cap_hits(real_salary, years_remaining, annual_inflation)


def build_player_schedule_rows(player_row: dict[str, Any], annual_inflation: float) -> list[dict[str, Any]]:
    """Expand one ledger row into year-by-year schedule rows."""
    years_remaining = int(player_row["years_remaining"])
    if years_remaining <= 0:
        return []

    is_instrument = player_row["contract_type_bucket"] == "instrument_adjusted"
    schedule_source = "best_effort_instrument" if is_instrument else "standard_rule"

    if is_instrument:
        cap_hits = instrument_best_effort_cap_hits(
            real_salary=float(player_row["real_salary"]),
            extension_salary=float(player_row["extension_salary"]),
            years_remaining=years_remaining,
            annual_inflation=annual_inflation,
        )
    else:
        cap_hits = standard_cap_hits(
            real_salary=float(player_row["real_salary"]),
            years_remaining=years_remaining,
            annual_inflation=annual_inflation,
        )

    rows: list[dict[str, Any]] = []
    for year_index, cap_hit_real in enumerate(cap_hits):
        rows.append(
            {
                "player": player_row["player"],
                "team": player_row["team"],
                "position": player_row["position"],
                "year_index": int(year_index),
                "cap_hit_real": float(cap_hit_real),
                "cap_hit_current": float(player_row["current_salary"]) if year_index == 0 else math.nan,
                "schedule_source": schedule_source,
                "needs_schedule_validation": bool(player_row["needs_schedule_validation"]),
            }
        )
    return rows
