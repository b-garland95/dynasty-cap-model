import math

from src.contracts.dead_money import (
    dead_money_active_roster_cut_nominal,
    dead_money_active_roster_cut_pv,
)


def test_dead_money_3yr_10pct_escalator():
    dm = dead_money_active_roster_cut_nominal(real_salary=10.0, years_remaining=3, inflation=0.10)
    expected = 10.0 + 0.25 * (11.0 + 13.0)
    assert math.isclose(dm, expected, rel_tol=1e-9)


def test_dead_money_3yr_10pct_escalator_pv_25pct_discount():
    dm_pv = dead_money_active_roster_cut_pv(
        real_salary=10.0,
        years_remaining=3,
        inflation=0.10,
        discount_rate=0.25,
    )
    expected = 10.0 + 0.25 * ((11.0 / 1.25) + (13.0 / (1.25 ** 2)))
    assert math.isclose(dm_pv, expected, rel_tol=1e-9)


def test_dead_money_uses_rounded_integer_salary_path():
    dm = dead_money_active_roster_cut_nominal(real_salary=5.0, years_remaining=4, inflation=0.10)
    expected = 5.0 + 0.25 * (6.0 + 7.0 + 8.0)
    assert math.isclose(dm, expected, rel_tol=1e-9)
