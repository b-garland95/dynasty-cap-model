"""Tests for src/contracts/pick_values.py"""

import pytest

from src.contracts.pick_values import pick_base_salary, pick_value_metrics

# ── Minimal config fixture matching league_config.yaml defaults ────────────

ROOKIE_SCALE = {
    "round1": {
        "1.01": 14,
        "1.02": 12,
        "1.03": 12,
        "1.04": 10,
        "1.05": 10,
        "1.06": 10,
        "1.07": 8,
        "1.08": 8,
        "1.09": 8,
        "1.10": 6,
    },
    "round2_salary": 4,
    "round3_salary": 2,
    "round4_salary": 1,
    "contract_years": 3,
    "option_years": 1,
}

CONFIG = {
    "rookie_scale": ROOKIE_SCALE,
    "cap": {
        "base_cap": 300,
        "annual_inflation": 0.10,
        "discount_rate": 0.25,
    },
    "season": {
        "target_season": 2026,
    },
}

CURRENT_SEASON = 2026


# ── pick_base_salary ───────────────────────────────────────────────────────


def test_base_salary_r1_known_slot():
    assert pick_base_salary(1, 1, ROOKIE_SCALE) == 14.0
    assert pick_base_salary(1, 4, ROOKIE_SCALE) == 10.0
    assert pick_base_salary(1, 7, ROOKIE_SCALE) == 8.0
    assert pick_base_salary(1, 10, ROOKIE_SCALE) == 6.0


def test_base_salary_r1_unknown_slot():
    # Average of 14+12+12+10+10+10+8+8+8+6 = 98 / 10 = 9.8
    avg = pick_base_salary(1, None, ROOKIE_SCALE)
    assert abs(avg - 9.8) < 1e-9


def test_base_salary_rounds_2_4():
    assert pick_base_salary(2, None, ROOKIE_SCALE) == 4.0
    assert pick_base_salary(2, 3, ROOKIE_SCALE) == 4.0   # slot irrelevant
    assert pick_base_salary(3, None, ROOKIE_SCALE) == 2.0
    assert pick_base_salary(4, None, ROOKIE_SCALE) == 1.0


# ── pick_value_metrics — offset=0 (current-year pick) ─────────────────────


def test_r1_slot4_current_year_value():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    # cap_path = [10, ceil(11)=11, ceil(12.1)=13]
    assert m["value_1yr"] == 10.0
    assert m["cap_1yr"] == 10.0


def test_r1_slot4_current_year_3yr():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    # (10 + 11 + 13) / 3 = 34/3
    assert abs(m["value_3yr_ann"] - 34 / 3) < 1e-9
    assert abs(m["cap_3yr_ann"] - 34 / 3) < 1e-9


def test_r1_slot4_current_year_pv():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    # pv = 10/1.25^0 + 11/1.25^1 + 13/1.25^2
    expected_pv = 10.0 + 11.0 / 1.25 + 13.0 / 1.5625
    assert abs(m["pv_cap"] - expected_pv) < 1e-6
    assert abs(m["pv_tv"] - expected_pv) < 1e-6


def test_r1_unknown_slot_current_year():
    # base = 9.8; cap_path = [9.8, ceil(10.78)=11, ceil(12.1)=13]
    m = pick_value_metrics(9.8, 2026, CURRENT_SEASON, CONFIG)
    assert abs(m["value_1yr"] - 9.8) < 1e-9
    assert m["surplus_1yr"] == 0.0


# ── pick_value_metrics — offset=1 (one year future) ───────────────────────


def test_r1_slot4_offset1_value_1yr_is_zero():
    m = pick_value_metrics(10.0, 2027, CURRENT_SEASON, CONFIG)
    assert m["value_1yr"] == 0.0
    assert m["cap_1yr"] == 0.0


def test_r1_slot4_offset1_3yr():
    m = pick_value_metrics(10.0, 2027, CURRENT_SEASON, CONFIG)
    # window: pos0=0 (contract idx -1), pos1=10 (idx 0), pos2=11 (idx 1)
    # (0 + 10 + 11) / 3 = 7.0
    assert abs(m["value_3yr_ann"] - 7.0) < 1e-9


def test_r1_slot4_offset1_pv_discounted_extra_year():
    m = pick_value_metrics(10.0, 2027, CURRENT_SEASON, CONFIG)
    # pv = 10/1.25^1 + 11/1.25^2 + 13/1.25^3
    expected_pv = 10.0 / 1.25 + 11.0 / 1.5625 + 13.0 / 1.953125
    assert abs(m["pv_cap"] - expected_pv) < 1e-6


# ── pick_value_metrics — offset=2 (two years future) ──────────────────────


def test_r1_slot4_offset2_windows():
    m = pick_value_metrics(10.0, 2028, CURRENT_SEASON, CONFIG)
    # window: pos0=0, pos1=0, pos2=10 (idx 0)
    assert m["value_1yr"] == 0.0
    assert abs(m["value_3yr_ann"] - 10.0 / 3) < 1e-9


# ── pick_value_metrics — round 2 flat ─────────────────────────────────────


def test_r2_current_year():
    m = pick_value_metrics(4.0, 2026, CURRENT_SEASON, CONFIG)
    # cap_path = [4, ceil(4.4)=5, ceil(5.5)=6]
    assert m["value_1yr"] == 4.0
    assert m["surplus_1yr"] == 0.0


def test_r2_offset1():
    m = pick_value_metrics(4.0, 2027, CURRENT_SEASON, CONFIG)
    # window: pos0=0, pos1=4, pos2=5
    assert m["value_1yr"] == 0.0
    assert abs(m["value_3yr_ann"] - (0 + 4 + 5) / 3) < 1e-9


# ── Surplus always zero ────────────────────────────────────────────────────


@pytest.mark.parametrize("rnd,slot,year", [
    (1, 1, 2026),
    (1, 4, 2026),
    (1, None, 2026),
    (1, 4, 2027),
    (1, 4, 2028),
    (2, None, 2026),
    (2, None, 2027),
    (3, None, 2026),
    (4, None, 2026),
])
def test_surplus_always_zero(rnd, slot, year):
    base = pick_base_salary(rnd, slot, ROOKIE_SCALE)
    m = pick_value_metrics(base, year, CURRENT_SEASON, CONFIG)
    assert m["surplus_value"] == 0.0
    assert m["surplus_1yr"] == 0.0
    assert m["surplus_3yr_ann"] == 0.0
    assert m["surplus_5yr_ann"] == 0.0
    assert m["contract_total_surplus"] == 0.0
    assert m["contract_avg_surplus"] == 0.0


# ── pv_tv == pv_cap ────────────────────────────────────────────────────────


@pytest.mark.parametrize("rnd,slot,year", [
    (1, 1, 2026),
    (1, None, 2026),
    (1, 4, 2027),
    (2, None, 2026),
])
def test_pv_tv_equals_pv_cap(rnd, slot, year):
    base = pick_base_salary(rnd, slot, ROOKIE_SCALE)
    m = pick_value_metrics(base, year, CURRENT_SEASON, CONFIG)
    assert m["pv_tv"] == m["pv_cap"]


# ── tv_yi == cap_yi (contract-relative columns) ───────────────────────────


def test_tv_equals_cap_per_year():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    for i in range(4):
        assert m[f"tv_y{i}"] == m[f"cap_y{i}"]


# ── cap path escalation ────────────────────────────────────────────────────


def test_cap_path_escalation_r1_slot4():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    assert m["cap_y0"] == 10.0
    assert m["cap_y1"] == 11.0   # ceil(10 * 1.10)
    assert m["cap_y2"] == 13.0   # ceil(11 * 1.10) = ceil(12.1)
    assert m["cap_y3"] == 0.0    # padded (only 3-year contract)


def test_cap_path_r2():
    m = pick_value_metrics(4.0, 2026, CURRENT_SEASON, CONFIG)
    assert m["cap_y0"] == 4.0
    assert m["cap_y1"] == 5.0    # ceil(4.4)
    assert m["cap_y2"] == 6.0    # ceil(5.5)


# ── contract aggregates ────────────────────────────────────────────────────


def test_contract_total_r1_slot4():
    m = pick_value_metrics(10.0, 2026, CURRENT_SEASON, CONFIG)
    # 10 + 11 + 13 = 34
    assert m["contract_total_value"] == 34.0
    assert m["contract_total_cap"] == 34.0
    assert abs(m["contract_avg_value"] - 34.0 / 3) < 1e-9


# ── metadata fields ────────────────────────────────────────────────────────


def test_metadata_fields():
    m = pick_value_metrics(10.0, 2027, CURRENT_SEASON, CONFIG)
    assert m["pick_year"] == 2027
    assert m["offset_from_current"] == 1
    assert m["years_remaining"] == 3
