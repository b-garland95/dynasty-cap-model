import math

from src.contracts.schedule_builder import build_rounded_salary_path


def dead_money_active_roster_cut_nominal(real_salary: float, years_remaining: int, inflation: float = 0.10) -> float:
    """
    Dead money if cut now (active roster):
      - 100% of current-year salary (owed immediately when the league year begins)
      - Lump-sum next season: ceil(25% × (years_remaining − 1) × year-1 scheduled salary)
        Cap charges are whole dollars, so the lump is rounded up.
    """
    if years_remaining <= 0:
        return 0.0

    salary_path = build_rounded_salary_path(real_salary, years_remaining, inflation)
    year0 = salary_path[0]
    year1 = salary_path[1] if len(salary_path) > 1 else 0.0
    future_lump = math.ceil(0.25 * (years_remaining - 1) * year1)
    return year0 + future_lump


def dead_money_active_roster_cut_pv(
    real_salary: float,
    years_remaining: int,
    inflation: float,
    discount_rate: float,
) -> float:
    """
    Present value of dead money if cut now (active roster):
      - 100% of current-year salary at k=0 (owed immediately, no discounting)
      - Lump-sum future dead money charged next season (k=1):
        ceil(25% × (years_remaining − 1) × year-1 scheduled salary), discounted once
    """
    if years_remaining <= 0:
        return 0.0

    salary_path = build_rounded_salary_path(real_salary, years_remaining, inflation)
    year0 = salary_path[0]
    year1 = salary_path[1] if len(salary_path) > 1 else 0.0
    future_lump = math.ceil(0.25 * (years_remaining - 1) * year1)
    return year0 + future_lump / (1 + discount_rate)
