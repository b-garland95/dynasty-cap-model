"""Tests for position-specific age-curve multipliers."""

from __future__ import annotations

import math

import pytest

from src.modeling.age_curve import (
    AgeCurveParams,
    get_age_multiplier,
    get_age_multipliers,
    load_age_curves,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WR_PARAMS = AgeCurveParams(peak_age=27.0, rise_slope=0.07, decline_slope=0.08)
RB_PARAMS = AgeCurveParams(peak_age=25.0, rise_slope=0.09, decline_slope=0.12)
QB_PARAMS = AgeCurveParams(peak_age=29.0, rise_slope=0.04, decline_slope=0.06)


# ---------------------------------------------------------------------------
# get_age_multiplier — correctness at peak
# ---------------------------------------------------------------------------

class TestMultiplierAtPeak:

    def test_multiplier_is_one_at_peak_year_zero(self):
        """If current_age == peak_age, offset=0 → multiplier = 1.0."""
        assert math.isclose(get_age_multiplier(WR_PARAMS, 27.0, 0), 1.0)

    def test_multiplier_is_one_at_peak_via_offset(self):
        """If current_age=22 and peak_age=27, multiplier = 1.0 at offset=5."""
        val = get_age_multiplier(WR_PARAMS, 22.0, 5)
        assert math.isclose(val, 1.0, abs_tol=1e-12)

    def test_multiplier_is_one_at_rb_peak_via_offset(self):
        val = get_age_multiplier(RB_PARAMS, 22.0, 3)  # 22+3=25
        assert math.isclose(val, 1.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# get_age_multiplier — pre-peak (rising) behaviour
# ---------------------------------------------------------------------------

class TestMultiplierPrePeak:

    def test_pre_peak_multiplier_less_than_one(self):
        """A player younger than their peak age should have multiplier < 1 at offset=0."""
        val = get_age_multiplier(WR_PARAMS, current_age=22.0, year_offset=0)
        assert val < 1.0

    def test_pre_peak_multiplier_increases_toward_peak(self):
        """Each year approaching peak, the multiplier should rise."""
        values = [get_age_multiplier(WR_PARAMS, 22.0, k) for k in range(6)]
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1], (
                f"Multiplier should be non-decreasing pre-peak: {values}"
            )

    def test_pre_peak_then_post_peak_transition(self):
        """Multiplier rises to 1.0 at peak then declines."""
        # current_age=22, peak=27 → peak at k=5
        mults = [get_age_multiplier(WR_PARAMS, 22.0, k) for k in range(8)]
        assert mults[5] > mults[4]     # still rising at k=4→5
        assert math.isclose(mults[5], 1.0, abs_tol=1e-12)
        assert mults[6] < mults[5]     # declining after peak


# ---------------------------------------------------------------------------
# get_age_multiplier — post-peak (declining) behaviour
# ---------------------------------------------------------------------------

class TestMultiplierPostPeak:

    def test_post_peak_multiplier_less_than_one(self):
        """A player past their peak at offset=0 should have multiplier < 1."""
        val = get_age_multiplier(WR_PARAMS, current_age=31.0, year_offset=0)
        assert val < 1.0

    def test_post_peak_multiplier_decreases_over_time(self):
        """Each year past peak, the multiplier should fall."""
        values = [get_age_multiplier(WR_PARAMS, 31.0, k) for k in range(5)]
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1], (
                f"Multiplier should be non-increasing post-peak: {values}"
            )

    def test_rb_declines_faster_than_qb(self):
        """RB decline slope > QB decline slope: same years past peak → RB lower."""
        years_past_rb_peak = 3
        years_past_qb_peak = 3
        rb_age = RB_PARAMS.peak_age + years_past_rb_peak
        qb_age = QB_PARAMS.peak_age + years_past_qb_peak
        rb_mult = get_age_multiplier(RB_PARAMS, rb_age, 0)
        qb_mult = get_age_multiplier(QB_PARAMS, qb_age, 0)
        assert rb_mult < qb_mult, (
            f"RB mult {rb_mult:.3f} should be < QB mult {qb_mult:.3f} "
            f"at same years-past-peak"
        )


# ---------------------------------------------------------------------------
# get_age_multiplier — edge cases
# ---------------------------------------------------------------------------

class TestMultiplierEdgeCases:

    def test_nan_age_returns_one(self):
        val = get_age_multiplier(WR_PARAMS, current_age=float("nan"), year_offset=1)
        assert math.isclose(val, 1.0)

    def test_inf_age_returns_one(self):
        val = get_age_multiplier(WR_PARAMS, current_age=float("inf"), year_offset=1)
        assert math.isclose(val, 1.0)

    def test_negative_offset_raises(self):
        with pytest.raises(ValueError, match="year_offset"):
            get_age_multiplier(WR_PARAMS, 26.0, -1)

    def test_multiplier_in_valid_range(self):
        for age in [18.0, 22.0, 27.0, 32.0, 38.0]:
            for k in range(5):
                val = get_age_multiplier(WR_PARAMS, age, k)
                assert 0.0 < val <= 1.0 + 1e-12


# ---------------------------------------------------------------------------
# get_age_multipliers (batch helper)
# ---------------------------------------------------------------------------

class TestGetAgeMultipliers:

    def test_returns_max_offset_plus_one_values(self):
        mults = get_age_multipliers(WR_PARAMS, 25.0, max_offset=3)
        assert len(mults) == 4  # offsets 0,1,2,3

    def test_first_entry_matches_single_call(self):
        mults = get_age_multipliers(WR_PARAMS, 25.0)
        assert math.isclose(mults[0], get_age_multiplier(WR_PARAMS, 25.0, 0))


# ---------------------------------------------------------------------------
# load_age_curves
# ---------------------------------------------------------------------------

class TestLoadAgeCurves:

    def _config(self):
        return {
            "age_curves": {
                "QB": {"peak_age": 30, "rise_slope": 0.03, "decline_slope": 0.05},
                "WR": {"peak_age": 26, "rise_slope": 0.08, "decline_slope": 0.09},
                "RB": {"peak_age": 24, "rise_slope": 0.10, "decline_slope": 0.13},
                "TE": {"peak_age": 28, "rise_slope": 0.04, "decline_slope": 0.06},
            }
        }

    def test_loads_all_positions(self):
        curves = load_age_curves(self._config())
        for pos in ["QB", "WR", "RB", "TE"]:
            assert pos in curves

    def test_loaded_params_match_config(self):
        curves = load_age_curves(self._config())
        qb = curves["QB"]
        assert math.isclose(qb.peak_age, 30.0)
        assert math.isclose(qb.rise_slope, 0.03)
        assert math.isclose(qb.decline_slope, 0.05)

    def test_empty_config_uses_defaults(self):
        curves = load_age_curves({})
        # Should still have all standard positions from built-in defaults
        for pos in ["QB", "WR", "RB", "TE"]:
            assert pos in curves
            assert curves[pos].peak_age > 0

    def test_params_are_immutable(self):
        curves = load_age_curves(self._config())
        with pytest.raises(Exception):
            curves["QB"].peak_age = 999  # type: ignore[misc]
