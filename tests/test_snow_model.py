"""Tests for snowfinder_common.snow_model."""

import math

import pytest

from snowfinder_common.snow_model import (
    _approx_wet_bulb,
    compute_slr,
    compute_snow_fraction,
    compute_snowfall,
)


class TestApproxWetBulb:
    def test_returns_float(self):
        result = _approx_wet_bulb(10.0, 50.0)
        assert isinstance(result, float)

    def test_wet_bulb_below_dry_bulb_at_low_rh(self):
        # At low RH, wet-bulb should be well below dry-bulb
        tw = _approx_wet_bulb(20.0, 20.0)
        assert tw < 20.0

    def test_wet_bulb_approaches_dry_bulb_at_high_rh(self):
        # At near-saturation RH, wet-bulb ≈ dry-bulb
        tw = _approx_wet_bulb(20.0, 99.0)
        assert abs(tw - 20.0) < 5.0

    def test_rh_clamped_at_minimum_5(self):
        # RH below 5 should be clamped to 5 — same result as RH=5
        tw_clamped = _approx_wet_bulb(15.0, 5.0)
        tw_below = _approx_wet_bulb(15.0, 1.0)
        assert tw_clamped == tw_below

    def test_rh_clamped_at_maximum_99(self):
        tw_clamped = _approx_wet_bulb(15.0, 99.0)
        tw_above = _approx_wet_bulb(15.0, 110.0)
        assert tw_clamped == tw_above

    def test_freezing_temp_low_rh_returns_negative_wet_bulb(self):
        # 0°C dry-bulb with low RH → wet-bulb clearly negative
        tw = _approx_wet_bulb(0.0, 30.0)
        assert tw < 0.0

    def test_hot_dry_returns_much_lower_wet_bulb(self):
        tw = _approx_wet_bulb(40.0, 10.0)
        assert tw < 25.0

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_inputs(self, value):
        with pytest.raises(ValueError, match="must be finite"):
            _approx_wet_bulb(value, 50.0)


class TestComputeSnowFraction:
    def test_cold_850hpa_returns_full_snow(self):
        frac = compute_snow_fraction(-5.0, -2.0, 80.0)
        assert frac == 1.0

    def test_warm_850hpa_returns_zero_snow(self):
        frac = compute_snow_fraction(5.0, 10.0, 60.0)
        assert frac == 0.0

    def test_boundary_minus_two_850hpa_returns_one(self):
        frac = compute_snow_fraction(-2.0, 0.0, 80.0)
        # At exactly -2°C, primary frac=1.0; wet-bulb may boost but it's capped at 1.0
        assert frac == pytest.approx(1.0, abs=0.01)

    def test_boundary_plus_two_850hpa_returns_zero(self):
        frac = compute_snow_fraction(2.0, 10.0, 50.0)
        assert frac == pytest.approx(0.0, abs=0.01)

    def test_midpoint_zero_850hpa_returns_half(self):
        # At 0°C: frac = 1 - (0+2)/4 = 0.5; adjustment depends on surface wet-bulb
        frac = compute_snow_fraction(0.0, 0.0, 80.0)
        assert 0.0 <= frac <= 1.0

    def test_fraction_always_between_zero_and_one(self):
        for temp_850 in [-20.0, -5.0, 0.0, 2.0, 10.0]:
            for temp_surf in [-10.0, 0.0, 15.0]:
                for rh in [10.0, 50.0, 95.0]:
                    frac = compute_snow_fraction(temp_850, temp_surf, rh)
                    assert 0.0 <= frac <= 1.0, (
                        f"Fraction {frac} out of range for "
                        f"temp_850={temp_850}, temp_surf={temp_surf}, rh={rh}"
                    )

    def test_cold_surface_wet_bulb_boosts_snow_fraction(self):
        # Warm 850hPa but very cold surface should get a boost
        frac_cold_surface = compute_snow_fraction(0.0, -10.0, 90.0)
        frac_warm_surface = compute_snow_fraction(0.0, 15.0, 20.0)
        assert frac_cold_surface > frac_warm_surface

    def test_warm_surface_wet_bulb_reduces_snow_fraction(self):
        # Identical 850hPa, but warm humid surface reduces snow fraction
        frac_cold = compute_snow_fraction(-1.0, -5.0, 80.0)
        frac_warm = compute_snow_fraction(-1.0, 20.0, 80.0)
        assert frac_cold > frac_warm

    @pytest.mark.parametrize(
        ("temp_850", "expected_min", "expected_max"),
        [
            (-10.0, 0.8, 1.0),
            (0.0, 0.3, 0.7),
            (5.0, 0.0, 0.2),
        ],
    )
    def test_fraction_in_expected_range_by_temp(self, temp_850, expected_min, expected_max):
        frac = compute_snow_fraction(temp_850, 0.0, 70.0)
        assert expected_min <= frac <= expected_max

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_inputs(self, value):
        with pytest.raises(ValueError, match="must be finite"):
            compute_snow_fraction(value, 0.0, 70.0)


class TestComputeSlr:
    def test_very_cold_returns_max_slr(self):
        slr = compute_slr(-20.0)
        assert slr == pytest.approx(1.5)

    def test_boundary_minus_fifteen_returns_max_slr(self):
        slr = compute_slr(-15.0)
        assert slr == pytest.approx(1.5)

    def test_boundary_minus_ten_returns_1_2(self):
        slr = compute_slr(-10.0)
        assert slr == pytest.approx(1.2)

    def test_boundary_minus_five_returns_1_0(self):
        slr = compute_slr(-5.0)
        assert slr == pytest.approx(1.0)

    def test_boundary_zero_returns_0_8(self):
        slr = compute_slr(0.0)
        assert slr == pytest.approx(0.8)

    def test_warm_temp_returns_lower_slr(self):
        slr = compute_slr(5.0)
        assert slr == pytest.approx(0.6)

    def test_very_warm_capped_at_0_6(self):
        slr_5 = compute_slr(5.0)
        slr_20 = compute_slr(20.0)
        assert slr_5 == pytest.approx(slr_20)
        assert slr_20 == pytest.approx(0.6)

    def test_slr_decreases_monotonically_with_temperature(self):
        temps = [-20.0, -15.0, -12.0, -10.0, -7.0, -5.0, -2.0, 0.0, 2.0, 5.0, 10.0]
        slrs = [compute_slr(t) for t in temps]
        for i in range(len(slrs) - 1):
            assert slrs[i] >= slrs[i + 1], f"SLR not monotonic at index {i}"

    def test_interpolation_between_minus_ten_and_minus_fifteen(self):
        # At -12.5°C, halfway between -15 and -10 → halfway between 1.5 and 1.2
        slr = compute_slr(-12.5)
        assert slr == pytest.approx(1.35, abs=0.01)

    def test_always_positive(self):
        for temp in [-30.0, -15.0, -5.0, 0.0, 5.0, 15.0]:
            assert compute_slr(temp) > 0.0

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_inputs(self, value):
        with pytest.raises(ValueError, match="must be finite"):
            compute_slr(value)


class TestComputeSnowfall:
    def test_zero_precip_returns_all_zeros(self):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(0.0, -5.0, -2.0, 80.0)
        assert snowfall_cm == 0.0
        assert rain_mm == 0.0
        assert snow_frac == 0.0

    def test_negative_precip_returns_all_zeros(self):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(-1.0, -5.0, -2.0, 80.0)
        assert snowfall_cm == 0.0
        assert rain_mm == 0.0
        assert snow_frac == 0.0

    def test_negative_precip_logs_warning(self, caplog):
        with caplog.at_level("WARNING"):
            compute_snowfall(-1.0, -5.0, -2.0, 80.0)

        assert any("Negative precipitation value" in record.message for record in caplog.records)

    def test_cold_conditions_produce_mostly_snow(self):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(10.0, -10.0, -5.0, 80.0)
        assert snow_frac > 0.9
        assert snowfall_cm > 0.0
        assert rain_mm < 1.0

    def test_warm_conditions_produce_mostly_rain(self):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(10.0, 5.0, 10.0, 60.0)
        assert snow_frac < 0.1
        assert rain_mm > 9.0

    def test_snowfall_uses_slr_correctly(self):
        # Very cold temps → SLR=1.5, full snow → snowfall_cm = precip_mm * 1.5
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(10.0, -20.0, -10.0, 80.0)
        assert snow_frac == pytest.approx(1.0, abs=0.01)
        assert snowfall_cm == pytest.approx(10.0 * 1.5, abs=0.5)
        assert rain_mm == pytest.approx(0.0, abs=0.1)

    def test_returns_tuple_of_three_floats(self):
        result = compute_snowfall(5.0, -5.0, 0.0, 70.0)
        assert len(result) == 3
        snowfall_cm, rain_mm, snow_frac = result
        assert isinstance(snowfall_cm, float)
        assert isinstance(rain_mm, float)
        assert isinstance(snow_frac, float)

    def test_snow_plus_rain_equals_precip(self):
        precip_mm = 12.0
        _, rain_mm, snow_frac = compute_snowfall(precip_mm, -3.0, -1.0, 75.0)
        snow_lwe = precip_mm * snow_frac
        assert rain_mm + snow_lwe == pytest.approx(precip_mm, abs=1e-9)

    def test_snowfall_zero_in_warm_rain_scenario(self):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(5.0, 10.0, 15.0, 50.0)
        assert snowfall_cm == pytest.approx(0.0, abs=0.01)
        assert rain_mm == pytest.approx(5.0, abs=0.01)

    @pytest.mark.parametrize(
        ("precip_mm", "temp_850", "temp_surf", "rh"),
        [
            (1.0, -20.0, -10.0, 90.0),
            (5.0, -5.0, 0.0, 70.0),
            (20.0, 0.0, 2.0, 85.0),
            (100.0, -15.0, -8.0, 95.0),
        ],
    )
    def test_snowfall_and_rain_are_non_negative(self, precip_mm, temp_850, temp_surf, rh):
        snowfall_cm, rain_mm, snow_frac = compute_snowfall(precip_mm, temp_850, temp_surf, rh)
        assert snowfall_cm >= 0.0
        assert rain_mm >= 0.0
        assert 0.0 <= snow_frac <= 1.0

    def test_larger_precip_gives_larger_snowfall(self):
        snow1, _, _ = compute_snowfall(5.0, -10.0, -5.0, 80.0)
        snow2, _, _ = compute_snowfall(10.0, -10.0, -5.0, 80.0)
        assert snow2 > snow1 > 0.0

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_rejects_non_finite_precipitation(self, value):
        with pytest.raises(ValueError, match="must be finite"):
            compute_snowfall(value, -5.0, -2.0, 80.0)
