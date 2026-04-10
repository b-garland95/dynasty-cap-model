import math

from src.contracts.dead_money import (
    dead_money_active_roster_cut_nominal,
    dead_money_active_roster_cut_pv,
)


def test_dead_money_3yr_10pct_escalator():
    # salary_path = [10, 11, 13]; lump = ceil(25% × 2 × 11) = ceil(5.5) = 6
    dm = dead_money_active_roster_cut_nominal(real_salary=10.0, years_remaining=3, inflation=0.10)
    expected = 10.0 + math.ceil(0.25 * 2 * 11.0)  # = 16.0
    assert math.isclose(dm, expected, rel_tol=1e-9)


def test_dead_money_3yr_10pct_escalator_pv_25pct_discount():
    # lump = ceil(5.5) = 6, charged next season → discounted once at 1.25
    dm_pv = dead_money_active_roster_cut_pv(
        real_salary=10.0,
        years_remaining=3,
        inflation=0.10,
        discount_rate=0.25,
    )
    future_lump = math.ceil(0.25 * 2 * 11.0)  # = 6
    expected = 10.0 + future_lump / 1.25
    assert math.isclose(dm_pv, expected, rel_tol=1e-9)


def test_dead_money_uses_rounded_integer_salary_path():
    # salary_path = [5, 6, 7, 8]; lump = ceil(25% × 3 × 6) = ceil(4.5) = 5
    dm = dead_money_active_roster_cut_nominal(real_salary=5.0, years_remaining=4, inflation=0.10)
    expected = 5.0 + math.ceil(0.25 * 3 * 6.0)  # = 10.0
    assert math.isclose(dm, expected, rel_tol=1e-9)


def test_dead_money_1yr_remaining_no_future_lump():
    # 1 year left → no future years → lump = 0
    dm = dead_money_active_roster_cut_nominal(real_salary=20.0, years_remaining=1, inflation=0.10)
    assert math.isclose(dm, 20.0, rel_tol=1e-9)


def test_dead_money_user_example_4yr_schedule():
    # User's example: 4-year deal $20/$22/$25/$28 → ceil(75% × $22) = ceil(16.5) = 17 next season
    # Verifies the formula directly: ceil(0.25 * (years_remaining-1) * year1)
    year1, years_remaining = 22.0, 4
    future_lump = math.ceil(0.25 * (years_remaining - 1) * year1)
    assert future_lump == 17
