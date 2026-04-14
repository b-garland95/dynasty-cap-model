import math

from src.contracts.schedule_builder import build_rounded_salary_path


def dead_money_active_roster_cut(
    real_salary: float,
    years_remaining: int,
    inflation: float = 0.10,
    discount_rate: float = 0.0,
    current_year_percent: float = 1.0,
    future_year_percent: float = 0.25,
) -> float:
    """Dead money if a player is cut from the active roster.

    Charges:
    - ``current_year_percent`` of the current-year salary (owed immediately).
    - A lump sum charged *next* season equal to
      ``ceil(future_year_percent × (years_remaining − 1) × year-1 salary)``.
      Cap charges are whole dollars, so the lump is rounded up (ceil).

    When ``discount_rate > 0`` the lump sum is discounted once at the given
    rate (present value as of today).  Pass ``discount_rate=0.0`` (the default)
    for the nominal / undiscounted amount.

    Parameters
    ----------
    real_salary:
        Real (base) salary for the current contract year.
    years_remaining:
        Number of years remaining on the contract including the current year.
    inflation:
        Annual salary escalation rate (default 10% per LT league rules).
    discount_rate:
        Discount rate applied to the future lump sum.  Use 0.0 for nominal,
        config["cap"]["discount_rate"] for PV calculations.
    current_year_percent:
        Fraction of current-year salary charged as dead money (default 1.0).
    future_year_percent:
        Fraction applied to future years in the lump-sum formula (default 0.25).
    """
    if years_remaining <= 0:
        return 0.0

    salary_path = build_rounded_salary_path(real_salary, years_remaining, inflation)
    year0 = salary_path[0]
    year1 = salary_path[1] if len(salary_path) > 1 else 0.0
    future_lump = math.ceil(future_year_percent * (years_remaining - 1) * year1)
    discounted_lump = future_lump / (1.0 + discount_rate)
    return (current_year_percent * year0) + discounted_lump


# ---------------------------------------------------------------------------
# Convenience aliases kept for readability at call sites.
# ---------------------------------------------------------------------------

def dead_money_active_roster_cut_nominal(
    real_salary: float,
    years_remaining: int,
    inflation: float = 0.10,
    current_year_percent: float = 1.0,
    future_year_percent: float = 0.25,
) -> float:
    """Nominal (undiscounted) dead money on active roster cut."""
    return dead_money_active_roster_cut(
        real_salary=real_salary,
        years_remaining=years_remaining,
        inflation=inflation,
        discount_rate=0.0,
        current_year_percent=current_year_percent,
        future_year_percent=future_year_percent,
    )


def dead_money_active_roster_cut_pv(
    real_salary: float,
    years_remaining: int,
    inflation: float,
    discount_rate: float,
    current_year_percent: float = 1.0,
    future_year_percent: float = 0.25,
) -> float:
    """Present value of dead money on active roster cut."""
    return dead_money_active_roster_cut(
        real_salary=real_salary,
        years_remaining=years_remaining,
        inflation=inflation,
        discount_rate=discount_rate,
        current_year_percent=current_year_percent,
        future_year_percent=future_year_percent,
    )
