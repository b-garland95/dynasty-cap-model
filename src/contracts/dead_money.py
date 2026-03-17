from src.contracts.schedule_builder import build_rounded_salary_path


def dead_money_active_roster_cut_nominal(real_salary: float, years_remaining: int, inflation: float = 0.10) -> float:
    """
    Dead money if cut now (active roster):
      - 100% of current-year salary
      - 25% of each future year remaining using the rounded whole-dollar schedule
    """
    if years_remaining <= 0:
        return 0.0

    salary_path = build_rounded_salary_path(real_salary, years_remaining, inflation)
    year0 = salary_path[0]
    future = sum(salary_path[1:])
    return year0 + 0.25 * future


def dead_money_active_roster_cut_pv(
    real_salary: float,
    years_remaining: int,
    inflation: float,
    discount_rate: float,
) -> float:
    """
    Present value of dead money if cut now (active roster):
      - 100% of current-year salary
      - 25% of each future year remaining, discounted by (1 + discount_rate)^k,
        using the rounded whole-dollar schedule
    """
    if years_remaining <= 0:
        return 0.0

    salary_path = build_rounded_salary_path(real_salary, years_remaining, inflation)
    year0 = salary_path[0]
    future_pv = 0.0
    for k, nominal_k in enumerate(salary_path[1:], start=1):
        future_pv += nominal_k / ((1 + discount_rate) ** k)
    return year0 + 0.25 * future_pv
