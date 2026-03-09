import math
from src.contracts.dead_money import dead_money_active_roster_cut_nominal

def test_dead_money_3yr_10pct_escalator():
    # $10 year0, $11 year1, $12.1 year2
    dm = dead_money_active_roster_cut_nominal(real_salary=10.0, years_remaining=3, inflation=0.10)
    expected = 10.0 + 0.25 * (11.0 + 12.1)
    assert math.isclose(dm, expected, rel_tol=1e-9)
