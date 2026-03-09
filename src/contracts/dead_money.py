def dead_money_active_roster_cut_nominal(real_salary: float, years_remaining: int, inflation: float = 0.10) -> float:
    """
    Dead money if cut now (active roster):
      - 100% of current-year salary
      - 25% of each future year remaining (with standard inflation applied)
    """
    if years_remaining <= 0:
        return 0.0
    year0 = real_salary
    future = 0.0
    for k in range(1, years_remaining):
        future += real_salary * ((1 + inflation) ** k)
    return year0 + 0.25 * future
