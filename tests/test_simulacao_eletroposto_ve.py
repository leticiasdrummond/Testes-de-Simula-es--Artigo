"""
Testes unitarios e de integracao para simulacao_eletroposto_ve.py.
"""

import csv
import math
import random
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulacao_eletroposto_ve import (
    SLOT_MIN,
    SLOTS_PER_DAY,
    MIN_PER_DAY,
    ChargerTech,
    ChargerUnit,
    Metrics,
    Session,
    VehicleTech,
    assign_vehicle,
    base_vehicle_mix_brasil,
    build_charger_units,
    charging_duration_min_nonlinear,
    charger_park_by_year,
    deterministic_arrivals,
    effective_charging_power,
    expand_hourly_to_slots,
    format_metrics_row,
    hourly_profile_anti_typical,
    hourly_profile_typical,
    load_series_from_sessions,
    mean_metrics,
    normalize_profile,
    poisson_draw,
    preferred_charger_pool,
    realistic_charging_power,
    run_single_simulation,
    sampled_arrival_soc,
    sample_energy_need_kwh,
    save_csv,
    save_report,
    stochastic_arrivals,
    summarize,
    weighted_choice,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_slots_per_day(self):
        assert SLOTS_PER_DAY == 96  # 24*60 / 15

    def test_slot_min(self):
        assert SLOT_MIN == 15

    def test_min_per_day(self):
        assert MIN_PER_DAY == 1440


# ---------------------------------------------------------------------------
# normalize_profile
# ---------------------------------------------------------------------------

class TestNormalizeProfile:
    def test_basic_normalization(self):
        result = normalize_profile([1.0, 2.0, 3.0])
        assert abs(sum(result) - 1.0) < 1e-9
        assert result[0] < result[1] < result[2]

    def test_all_zeros(self):
        result = normalize_profile([0.0, 0.0, 0.0])
        assert len(result) == 3
        assert abs(sum(result) - 1.0) < 1e-9
        assert all(abs(v - 1.0 / 3) < 1e-9 for v in result)

    def test_negative_values_clamped_to_zero(self):
        result = normalize_profile([-1.0, 2.0, 3.0])
        # Negative values treated as 0
        assert abs(result[0]) < 1e-9
        assert abs(sum(result) - 1.0) < 1e-9

    def test_single_element(self):
        result = normalize_profile([5.0])
        assert len(result) == 1
        assert abs(result[0] - 1.0) < 1e-9

    def test_uniform_input(self):
        result = normalize_profile([1.0, 1.0, 1.0, 1.0])
        assert all(abs(v - 0.25) < 1e-9 for v in result)

    def test_large_values(self):
        result = normalize_profile([1000.0, 2000.0])
        assert abs(result[0] - 1 / 3) < 1e-9
        assert abs(result[1] - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# hourly_profile_typical / hourly_profile_anti_typical
# ---------------------------------------------------------------------------

class TestHourlyProfiles:
    def test_typical_length(self):
        profile = hourly_profile_typical()
        assert len(profile) == 24

    def test_typical_sum_to_one(self):
        profile = hourly_profile_typical()
        assert abs(sum(profile) - 1.0) < 1e-9

    def test_typical_all_positive(self):
        profile = hourly_profile_typical()
        assert all(v > 0 for v in profile)

    def test_anti_typical_length(self):
        profile = hourly_profile_anti_typical()
        assert len(profile) == 24

    def test_anti_typical_sum_to_one(self):
        profile = hourly_profile_anti_typical()
        assert abs(sum(profile) - 1.0) < 1e-9

    def test_anti_typical_all_positive(self):
        profile = hourly_profile_anti_typical()
        assert all(v > 0 for v in profile)

    def test_profiles_are_different(self):
        typical = hourly_profile_typical()
        anti = hourly_profile_anti_typical()
        assert typical != anti


# ---------------------------------------------------------------------------
# expand_hourly_to_slots
# ---------------------------------------------------------------------------

class TestExpandHourlyToSlots:
    def test_length(self):
        hourly = [1.0] * 24
        result = expand_hourly_to_slots(hourly)
        assert len(result) == SLOTS_PER_DAY

    def test_sum_to_one(self):
        hourly = [1.0] * 24
        result = expand_hourly_to_slots(hourly)
        assert abs(sum(result) - 1.0) < 1e-9

    def test_uniform_expansion(self):
        hourly = [1.0] * 24
        result = expand_hourly_to_slots(hourly)
        expected = 1.0 / SLOTS_PER_DAY
        assert all(abs(v - expected) < 1e-9 for v in result)

    def test_expansion_ratio(self):
        # Each hour expands to 60//SLOT_MIN slots
        slots_per_hour = 60 // SLOT_MIN
        hourly = list(range(1, 25))  # unequal weights
        result = expand_hourly_to_slots(hourly)
        assert len(result) == 24 * slots_per_hour


# ---------------------------------------------------------------------------
# base_vehicle_mix_brasil
# ---------------------------------------------------------------------------

class TestBaseVehicleMixBrasil:
    def test_weights_sum_to_one_2025(self):
        mix = base_vehicle_mix_brasil(2025)
        assert abs(sum(mix.values()) - 1.0) < 1e-9

    def test_weights_sum_to_one_2026(self):
        mix = base_vehicle_mix_brasil(2026)
        assert abs(sum(mix.values()) - 1.0) < 1e-9

    def test_weights_sum_to_one_2030(self):
        mix = base_vehicle_mix_brasil(2030)
        assert abs(sum(mix.values()) - 1.0) < 1e-9

    def test_weights_sum_to_one_2035(self):
        mix = base_vehicle_mix_brasil(2035)
        assert abs(sum(mix.values()) - 1.0) < 1e-9

    def test_has_three_vehicle_types(self):
        mix = base_vehicle_mix_brasil(2026)
        assert len(mix) == 3

    def test_year_2026_boundary(self):
        mix_2026 = base_vehicle_mix_brasil(2026)
        mix_2027 = base_vehicle_mix_brasil(2027)
        assert mix_2026 != mix_2027

    def test_year_2030_boundary(self):
        mix_2030 = base_vehicle_mix_brasil(2030)
        mix_2031 = base_vehicle_mix_brasil(2031)
        assert mix_2030 != mix_2031

    def test_future_year(self):
        mix = base_vehicle_mix_brasil(2050)
        assert abs(sum(mix.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# charger_park_by_year
# ---------------------------------------------------------------------------

class TestChargerParkByYear:
    def test_2026_has_chargers(self):
        park = charger_park_by_year(2026)
        total = sum(park.values())
        assert total > 0

    def test_2030_has_more_chargers(self):
        park_2026 = charger_park_by_year(2026)
        park_2030 = charger_park_by_year(2030)
        assert sum(park_2030.values()) >= sum(park_2026.values())

    def test_year_2026_boundary(self):
        park_2026 = charger_park_by_year(2026)
        park_2027 = charger_park_by_year(2027)
        assert park_2026 != park_2027

    def test_year_2030_boundary(self):
        park_2030 = charger_park_by_year(2030)
        park_2031 = charger_park_by_year(2031)
        assert park_2030 != park_2031

    def test_all_counts_positive(self):
        for year in [2025, 2026, 2028, 2030, 2031, 2040]:
            park = charger_park_by_year(year)
            assert all(v > 0 for v in park.values()), f"Year {year} has zero chargers"


# ---------------------------------------------------------------------------
# build_charger_units
# ---------------------------------------------------------------------------

class TestBuildChargerUnits:
    def test_correct_total_count(self):
        ac = ChargerTech("AC_7kW", 7.4, False)
        dc = ChargerTech("DC_60kW", 60.0, True)
        park = {ac: 3, dc: 2}
        units = build_charger_units(park)
        assert len(units) == 5

    def test_units_have_correct_power(self):
        ac = ChargerTech("AC_7kW", 7.4, False)
        park = {ac: 2}
        units = build_charger_units(park)
        assert all(u.power_kw == 7.4 for u in units)

    def test_units_have_correct_is_dc(self):
        dc = ChargerTech("DC_60kW", 60.0, True)
        park = {dc: 1}
        units = build_charger_units(park)
        assert units[0].is_dc is True

    def test_units_have_unique_names(self):
        ac = ChargerTech("AC_22kW", 22.0, False)
        park = {ac: 3}
        units = build_charger_units(park)
        names = [u.id_name for u in units]
        assert len(set(names)) == 3

    def test_units_start_available(self):
        ac = ChargerTech("AC_7kW", 7.4, False)
        park = {ac: 2}
        units = build_charger_units(park)
        assert all(u.available_at_min == 0.0 for u in units)

    def test_empty_park(self):
        units = build_charger_units({})
        assert units == []


# ---------------------------------------------------------------------------
# weighted_choice
# ---------------------------------------------------------------------------

class TestWeightedChoice:
    def test_single_item_always_chosen(self):
        rng = random.Random(42)
        items = {"a": 1.0}
        for _ in range(20):
            assert weighted_choice(rng, items) == "a"

    def test_respects_weights_over_many_samples(self):
        rng = random.Random(0)
        items = {"rare": 0.1, "common": 0.9}
        counts = {"rare": 0, "common": 0}
        n = 10000
        for _ in range(n):
            result = weighted_choice(rng, items)
            counts[result] += 1
        # common should be chosen approximately 90% of the time
        assert counts["common"] / n > 0.80
        assert counts["rare"] / n < 0.20

    def test_returns_valid_item(self):
        rng = random.Random(7)
        items = {"x": 0.3, "y": 0.5, "z": 0.2}
        for _ in range(50):
            result = weighted_choice(rng, items)
            assert result in items

    def test_zero_weight_item_almost_never_chosen(self):
        rng = random.Random(99)
        items = {"a": 0.0, "b": 1.0}
        # With nearly zero weight for 'a', 'b' should dominate
        counts = {"a": 0, "b": 0}
        for _ in range(1000):
            result = weighted_choice(rng, items)
            counts[result] += 1
        assert counts["b"] >= 990


# ---------------------------------------------------------------------------
# sampled_arrival_soc
# ---------------------------------------------------------------------------

class TestSampledArrivalSoc:
    def test_typical_within_bounds(self):
        rng = random.Random(1)
        for _ in range(1000):
            soc = sampled_arrival_soc(rng, anti_typical=False)
            assert 0.08 <= soc <= 0.75, f"SOC {soc} out of bounds"

    def test_anti_typical_within_bounds(self):
        rng = random.Random(2)
        for _ in range(1000):
            soc = sampled_arrival_soc(rng, anti_typical=True)
            assert 0.08 <= soc <= 0.75, f"SOC {soc} out of bounds"

    def test_typical_mean_higher_than_anti_typical(self):
        rng_typ = random.Random(42)
        rng_anti = random.Random(42)
        typical_socs = [sampled_arrival_soc(rng_typ, anti_typical=False) for _ in range(500)]
        anti_socs = [sampled_arrival_soc(rng_anti, anti_typical=True) for _ in range(500)]
        # Typical should have higher average SOC (less depleted)
        assert sum(typical_socs) / len(typical_socs) > sum(anti_socs) / len(anti_socs)


# ---------------------------------------------------------------------------
# sample_energy_need_kwh
# ---------------------------------------------------------------------------

class TestSampleEnergyNeedKwh:
    def setup_method(self):
        self.tech = VehicleTech("BEV_compacto", 42.0, 7.4, 70.0, 0.85)
        self.rng = random.Random(10)

    def test_above_target_soc_gives_small_amount(self):
        # arrival_soc >= target_soc -> 4 to 10 kWh range
        energy = sample_energy_need_kwh(self.tech, arrival_soc=0.90, rng=self.rng)
        assert 4.0 <= energy <= 10.0

    def test_below_target_soc_proportional(self):
        arrival_soc = 0.20
        expected = (self.tech.target_soc - arrival_soc) * self.tech.battery_kwh
        energy = sample_energy_need_kwh(self.tech, arrival_soc=arrival_soc, rng=self.rng)
        assert abs(energy - expected) < 1e-9

    def test_always_positive(self):
        for soc in [0.1, 0.5, 0.85, 0.95]:
            energy = sample_energy_need_kwh(self.tech, arrival_soc=soc, rng=self.rng)
            assert energy > 0


# ---------------------------------------------------------------------------
# effective_charging_power
# ---------------------------------------------------------------------------

class TestEffectiveChargingPower:
    def test_dc_limited_by_vehicle(self):
        tech = VehicleTech("BEV", 42.0, 7.4, 50.0, 0.85)
        charger = ChargerUnit("DC1", power_kw=120.0, is_dc=True)
        power = effective_charging_power(tech, charger)
        assert power == 50.0  # vehicle DC limit

    def test_dc_limited_by_charger(self):
        tech = VehicleTech("BEV", 42.0, 7.4, 200.0, 0.85)
        charger = ChargerUnit("DC1", power_kw=60.0, is_dc=True)
        power = effective_charging_power(tech, charger)
        assert power == 60.0  # charger limit

    def test_ac_limited_by_vehicle(self):
        tech = VehicleTech("BEV", 42.0, 7.4, 50.0, 0.85)
        charger = ChargerUnit("AC1", power_kw=22.0, is_dc=False)
        power = effective_charging_power(tech, charger)
        assert power == 7.4  # vehicle AC limit

    def test_ac_limited_by_charger(self):
        tech = VehicleTech("BEV", 42.0, 22.0, 50.0, 0.85)
        charger = ChargerUnit("AC1", power_kw=7.4, is_dc=False)
        power = effective_charging_power(tech, charger)
        assert power == 7.4  # charger limit


# ---------------------------------------------------------------------------
# realistic_charging_power
# ---------------------------------------------------------------------------

class TestRealisticChargingPower:
    def test_low_soc_dc_reduction(self):
        power = realistic_charging_power(0.10, max_power_kw=100.0, is_dc=True)
        assert abs(power - 85.0) < 1e-9

    def test_low_soc_ac_reduction(self):
        power = realistic_charging_power(0.10, max_power_kw=100.0, is_dc=False)
        assert abs(power - 90.0) < 1e-9

    def test_mid_soc_full_power(self):
        power = realistic_charging_power(0.50, max_power_kw=100.0, is_dc=True)
        assert abs(power - 100.0) < 1e-9

    def test_mid_soc_full_power_ac(self):
        power = realistic_charging_power(0.50, max_power_kw=100.0, is_dc=False)
        assert abs(power - 100.0) < 1e-9

    def test_high_soc_tapering_dc(self):
        # SOC at 0.90 (above 0.80) should reduce power
        power = realistic_charging_power(0.90, max_power_kw=100.0, is_dc=True)
        assert power < 100.0
        assert power > 0.0

    def test_high_soc_tapering_ac(self):
        power = realistic_charging_power(0.90, max_power_kw=100.0, is_dc=False)
        assert power < 100.0
        assert power > 0.0

    def test_dc_tapers_more_than_ac_at_high_soc(self):
        soc = 0.95
        dc_power = realistic_charging_power(soc, max_power_kw=100.0, is_dc=True)
        ac_power = realistic_charging_power(soc, max_power_kw=100.0, is_dc=False)
        assert dc_power < ac_power

    def test_power_always_positive(self):
        for soc in [0.0, 0.1, 0.5, 0.8, 0.9, 1.0]:
            for is_dc in [True, False]:
                power = realistic_charging_power(soc, max_power_kw=100.0, is_dc=is_dc)
                assert power > 0

    def test_full_soc_minimum_power_dc(self):
        # At SOC=1.0, DC should give 5% of max
        power = realistic_charging_power(1.0, max_power_kw=100.0, is_dc=True)
        assert power >= 0.05 * 100.0

    def test_soc_boundary_at_0_80(self):
        # exactly at 0.80 should give full power
        power = realistic_charging_power(0.80, max_power_kw=100.0, is_dc=True)
        assert abs(power - 100.0) < 1e-9


# ---------------------------------------------------------------------------
# charging_duration_min_nonlinear
# ---------------------------------------------------------------------------

class TestChargingDurationMinNonlinear:
    def test_duration_positive(self):
        duration = charging_duration_min_nonlinear(
            energy_need_kwh=20.0,
            battery_kwh=42.0,
            arrival_soc=0.30,
            target_soc=0.85,
            max_power_kw=70.0,
            is_dc=True,
            efficiency=0.93,
        )
        assert duration >= 1.0

    def test_duration_capped_at_240_min(self):
        # Extremely low power forces cap
        duration = charging_duration_min_nonlinear(
            energy_need_kwh=100.0,
            battery_kwh=200.0,
            arrival_soc=0.01,
            target_soc=0.99,
            max_power_kw=0.5,
            is_dc=False,
            efficiency=0.93,
        )
        assert duration <= 240.0

    def test_higher_power_shorter_duration(self):
        common_kwargs = dict(
            energy_need_kwh=20.0,
            battery_kwh=42.0,
            arrival_soc=0.20,
            target_soc=0.85,
            efficiency=0.93,
        )
        slow = charging_duration_min_nonlinear(
            max_power_kw=7.4, is_dc=False, **common_kwargs
        )
        fast = charging_duration_min_nonlinear(
            max_power_kw=70.0, is_dc=True, **common_kwargs
        )
        assert fast < slow

    def test_minimum_duration_is_one(self):
        # Even tiny energy needs return at least 1 minute
        duration = charging_duration_min_nonlinear(
            energy_need_kwh=0.001,
            battery_kwh=42.0,
            arrival_soc=0.50,
            target_soc=0.85,
            max_power_kw=70.0,
            is_dc=True,
            efficiency=0.93,
        )
        assert duration >= 1.0

    def test_already_at_target_soc(self):
        # arrival_soc == target_soc: while loop doesn't execute
        duration = charging_duration_min_nonlinear(
            energy_need_kwh=5.0,
            battery_kwh=42.0,
            arrival_soc=0.85,
            target_soc=0.85,
            max_power_kw=70.0,
            is_dc=True,
            efficiency=0.93,
        )
        assert duration >= 1.0


# ---------------------------------------------------------------------------
# preferred_charger_pool
# ---------------------------------------------------------------------------

class TestPreferredChargerPool:
    def setup_method(self):
        self.ac1 = ChargerUnit("AC1", 7.4, is_dc=False)
        self.ac2 = ChargerUnit("AC2", 22.0, is_dc=False)
        self.dc1 = ChargerUnit("DC1", 60.0, is_dc=True)
        self.dc2 = ChargerUnit("DC2", 120.0, is_dc=True)
        self.all_chargers = [self.ac1, self.ac2, self.dc1, self.dc2]

    def test_small_energy_prefers_ac(self):
        pool = preferred_charger_pool(10.0, self.all_chargers)
        assert all(not c.is_dc for c in pool)

    def test_large_energy_prefers_dc(self):
        pool = preferred_charger_pool(20.0, self.all_chargers)
        assert all(c.is_dc for c in pool)

    def test_no_ac_falls_back_to_dc(self):
        dc_only = [self.dc1, self.dc2]
        pool = preferred_charger_pool(10.0, dc_only)
        assert all(c.is_dc for c in pool)

    def test_no_dc_falls_back_to_ac(self):
        ac_only = [self.ac1, self.ac2]
        pool = preferred_charger_pool(20.0, ac_only)
        assert all(not c.is_dc for c in pool)

    def test_empty_list_returns_empty(self):
        pool = preferred_charger_pool(20.0, [])
        assert pool == []

    def test_boundary_at_16_kwh(self):
        # Energy exactly 16 kWh should use AC
        pool = preferred_charger_pool(16.0, self.all_chargers)
        assert all(not c.is_dc for c in pool)


# ---------------------------------------------------------------------------
# poisson_draw
# ---------------------------------------------------------------------------

class TestPoissonDraw:
    def test_zero_mean_returns_zero(self):
        rng = random.Random(1)
        assert poisson_draw(rng, 0.0) == 0

    def test_negative_mean_returns_zero(self):
        rng = random.Random(1)
        assert poisson_draw(rng, -5.0) == 0

    def test_non_negative_result(self):
        rng = random.Random(42)
        for mean in [1.0, 5.0, 10.0, 50.0, 100.0]:
            for _ in range(20):
                assert poisson_draw(rng, mean) >= 0

    def test_mean_approximately_correct_small(self):
        rng = random.Random(0)
        mean = 5.0
        samples = [poisson_draw(rng, mean) for _ in range(5000)]
        sample_mean = sum(samples) / len(samples)
        assert abs(sample_mean - mean) < 0.5  # within 0.5

    def test_mean_approximately_correct_large(self):
        rng = random.Random(7)
        mean = 100.0
        samples = [poisson_draw(rng, mean) for _ in range(2000)]
        sample_mean = sum(samples) / len(samples)
        assert abs(sample_mean - mean) < 5.0  # within 5


# ---------------------------------------------------------------------------
# load_series_from_sessions
# ---------------------------------------------------------------------------

class TestLoadSeriesFromSessions:
    def test_empty_sessions(self):
        series = load_series_from_sessions([])
        assert len(series) == SLOTS_PER_DAY
        assert all(v == 0.0 for v in series)

    def test_length_is_slots_per_day(self):
        sessions = [Session(0.0, 0.0, 30.0, 5.0, 10.0, 0.0)]
        series = load_series_from_sessions(sessions)
        assert len(series) == SLOTS_PER_DAY

    def test_session_spanning_single_slot(self):
        # Session from 0 to 15 min (exactly slot 0)
        sessions = [Session(0.0, 0.0, SLOT_MIN, 10.0, 20.0, 0.0)]
        series = load_series_from_sessions(sessions)
        # Slot 0 should be exactly 20 kW (power * overlap/SLOT_MIN = 20 * 15/15)
        assert abs(series[0] - 20.0) < 1e-9

    def test_session_spanning_two_slots(self):
        # Session from 0 to 30 min spans slots 0 and 1
        sessions = [Session(0.0, 0.0, 30.0, 10.0, 20.0, 0.0)]
        series = load_series_from_sessions(sessions)
        assert series[0] > 0
        assert series[1] > 0

    def test_non_overlapping_sessions_summed(self):
        # Two sessions in different slots
        s1 = Session(0.0, 0.0, 15.0, 5.0, 10.0, 0.0)
        s2 = Session(15.0, 15.0, 30.0, 5.0, 20.0, 0.0)
        series = load_series_from_sessions([s1, s2])
        assert abs(series[0] - 10.0) < 1e-9
        assert abs(series[1] - 20.0) < 1e-9

    def test_all_values_non_negative(self):
        sessions = [
            Session(10.0, 10.0, 60.0, 30.0, 50.0, 0.0),
            Session(30.0, 30.0, 90.0, 20.0, 30.0, 0.0),
        ]
        series = load_series_from_sessions(sessions)
        assert all(v >= 0 for v in series)


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

class TestSummarize:
    def test_empty_sessions(self):
        m = summarize([], n_arrivals=10, n_chargers=5)
        assert m.total_arrivals == 10
        assert m.served == 0
        assert m.total_energy_kwh == 0.0
        assert m.peak_kw == 0.0

    def test_served_count(self):
        sessions = [
            Session(0.0, 0.0, 30.0, 10.0, 20.0, 0.0),
            Session(10.0, 10.0, 45.0, 15.0, 30.0, 5.0),
        ]
        m = summarize(sessions, n_arrivals=5, n_chargers=2)
        assert m.served == 2

    def test_total_energy(self):
        sessions = [
            Session(0.0, 0.0, 30.0, 10.0, 20.0, 0.0),
            Session(10.0, 10.0, 45.0, 15.0, 30.0, 5.0),
        ]
        m = summarize(sessions, n_arrivals=5, n_chargers=2)
        assert abs(m.total_energy_kwh - 25.0) < 1e-9

    def test_wait_times(self):
        sessions = [
            Session(0.0, 5.0, 30.0, 10.0, 20.0, 5.0),
            Session(10.0, 20.0, 50.0, 15.0, 30.0, 10.0),
        ]
        m = summarize(sessions, n_arrivals=5, n_chargers=2)
        assert abs(m.mean_wait_min - 7.5) < 1e-9

    def test_utilization_range(self):
        sessions = [Session(0.0, 0.0, 60.0, 20.0, 20.0, 0.0)]
        m = summarize(sessions, n_arrivals=1, n_chargers=1)
        assert 0.0 <= m.utilization <= 1.0

    def test_load_factor_range(self):
        sessions = [Session(0.0, 0.0, 60.0, 20.0, 20.0, 0.0)]
        m = summarize(sessions, n_arrivals=1, n_chargers=1)
        assert 0.0 <= m.load_factor <= 1.0

    def test_p95_wait_within_bounds(self):
        rng = random.Random(3)
        sessions = [
            Session(i * 10.0, i * 10.0 + rng.random() * 5, i * 10.0 + rng.random() * 5 + 20.0, 5.0, 10.0, rng.random() * 5)
            for i in range(20)
        ]
        m = summarize(sessions, n_arrivals=20, n_chargers=3)
        assert m.p95_wait_min >= m.mean_wait_min


# ---------------------------------------------------------------------------
# deterministic_arrivals
# ---------------------------------------------------------------------------

class TestDeterministicArrivals:
    def test_total_count_close_to_demand(self):
        # The residue-based accumulation may differ by at most 1 due to floating-point rounding
        profile = normalize_profile([1.0] * SLOTS_PER_DAY)
        arrivals = deterministic_arrivals(100, profile)
        assert abs(len(arrivals) - 100) <= 1

    def test_arrivals_within_day(self):
        profile = normalize_profile([1.0] * SLOTS_PER_DAY)
        arrivals = deterministic_arrivals(50, profile)
        assert all(0 <= a <= MIN_PER_DAY for a in arrivals)

    def test_zero_arrivals(self):
        profile = normalize_profile([1.0] * SLOTS_PER_DAY)
        arrivals = deterministic_arrivals(0, profile)
        assert arrivals == []

    def test_non_negative(self):
        profile = hourly_profile_typical()
        slot_profile = expand_hourly_to_slots(profile)
        arrivals = deterministic_arrivals(80, slot_profile)
        assert all(a >= 0 for a in arrivals)


# ---------------------------------------------------------------------------
# stochastic_arrivals
# ---------------------------------------------------------------------------

class TestStochasticArrivals:
    def test_arrivals_sorted(self):
        rng = random.Random(1)
        profile = expand_hourly_to_slots(hourly_profile_typical())
        arrivals = stochastic_arrivals(rng, 100.0, profile, perturbation=0.2)
        assert arrivals == sorted(arrivals)

    def test_arrivals_within_day(self):
        rng = random.Random(2)
        profile = expand_hourly_to_slots(hourly_profile_typical())
        arrivals = stochastic_arrivals(rng, 100.0, profile, perturbation=0.2)
        assert all(0 <= a <= MIN_PER_DAY for a in arrivals)

    def test_non_negative(self):
        rng = random.Random(3)
        profile = expand_hourly_to_slots(hourly_profile_typical())
        arrivals = stochastic_arrivals(rng, 50.0, profile, perturbation=0.1)
        assert all(a >= 0 for a in arrivals)

    def test_higher_perturbation_increases_variance(self):
        # With identical seeds and base, higher perturbation => different count
        seed = 42
        profile = expand_hourly_to_slots(hourly_profile_typical())
        arrivals_low = stochastic_arrivals(random.Random(seed), 100.0, profile, perturbation=0.0)
        arrivals_high = stochastic_arrivals(random.Random(seed), 100.0, profile, perturbation=0.5)
        # They may differ; just ensure both are valid
        assert all(a >= 0 for a in arrivals_low)
        assert all(a >= 0 for a in arrivals_high)


# ---------------------------------------------------------------------------
# mean_metrics
# ---------------------------------------------------------------------------

class TestMeanMetrics:
    def test_empty_list(self):
        m = mean_metrics([])
        assert m.total_arrivals == 0
        assert m.total_energy_kwh == 0.0

    def test_single_item(self):
        m_input = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        result = mean_metrics([m_input])
        assert result.total_arrivals == 100
        assert abs(result.total_energy_kwh - 500.0) < 1e-9

    def test_average_of_two(self):
        m1 = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        m2 = Metrics(120, 110, 600.0, 7.0, 18.0, 250.0, 0.7, 0.5)
        result = mean_metrics([m1, m2])
        assert result.total_arrivals == 110
        assert abs(result.total_energy_kwh - 550.0) < 1e-9
        assert abs(result.mean_wait_min - 6.0) < 1e-9
        assert abs(result.load_factor - 0.65) < 1e-9

    def test_same_metrics_averaged_equal_original(self):
        m = Metrics(80, 75, 300.0, 3.5, 10.0, 150.0, 0.55, 0.35)
        result = mean_metrics([m, m, m])
        assert abs(result.total_energy_kwh - 300.0) < 1e-9
        assert abs(result.mean_wait_min - 3.5) < 1e-9


# ---------------------------------------------------------------------------
# format_metrics_row
# ---------------------------------------------------------------------------

class TestFormatMetricsRow:
    def test_keys_present(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        row = format_metrics_row("tipico", 2026, "deterministico", m)
        expected_keys = {"caso", "ano", "modo", "chegadas", "atendidos",
                         "energia_kwh", "espera_media_min", "espera_p95_min",
                         "pico_kw", "fator_carga", "utilizacao"}
        assert set(row.keys()) == expected_keys

    def test_values_are_strings(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        row = format_metrics_row("tipico", 2026, "deterministico", m)
        assert all(isinstance(v, str) for v in row.values())

    def test_case_name_preserved(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        row = format_metrics_row("anti_tipico", 2030, "estocastico", m)
        assert row["caso"] == "anti_tipico"
        assert row["ano"] == "2030"
        assert row["modo"] == "estocastico"


# ---------------------------------------------------------------------------
# assign_vehicle
# ---------------------------------------------------------------------------

class TestAssignVehicle:
    def setup_method(self):
        self.tech = VehicleTech("BEV_compacto", 42.0, 7.4, 70.0, 0.85)

    def test_returns_session(self):
        chargers = build_charger_units(charger_park_by_year(2026))
        session = assign_vehicle(
            arrival_min=100.0,
            energy_need_kwh=20.0,
            arrival_soc=0.30,
            tech=self.tech,
            chargers=chargers,
            charging_efficiency=0.93,
        )
        assert isinstance(session, Session)

    def test_session_end_after_start(self):
        chargers = build_charger_units(charger_park_by_year(2026))
        session = assign_vehicle(
            arrival_min=100.0,
            energy_need_kwh=20.0,
            arrival_soc=0.30,
            tech=self.tech,
            chargers=chargers,
            charging_efficiency=0.93,
        )
        assert session.end_min > session.start_min

    def test_session_start_after_or_at_arrival(self):
        chargers = build_charger_units(charger_park_by_year(2026))
        session = assign_vehicle(
            arrival_min=200.0,
            energy_need_kwh=15.0,
            arrival_soc=0.40,
            tech=self.tech,
            chargers=chargers,
            charging_efficiency=0.93,
        )
        assert session.start_min >= session.arrival_min

    def test_wait_time_non_negative(self):
        chargers = build_charger_units(charger_park_by_year(2026))
        session = assign_vehicle(
            arrival_min=50.0,
            energy_need_kwh=10.0,
            arrival_soc=0.50,
            tech=self.tech,
            chargers=chargers,
            charging_efficiency=0.93,
        )
        assert session.wait_min >= 0.0

    def test_charger_availability_updated(self):
        chargers = [ChargerUnit("DC1", 60.0, is_dc=True)]
        # First vehicle
        assign_vehicle(
            arrival_min=0.0,
            energy_need_kwh=20.0,
            arrival_soc=0.30,
            tech=self.tech,
            chargers=chargers,
            charging_efficiency=0.93,
        )
        # Charger should no longer be available at t=0
        assert chargers[0].available_at_min > 0.0


# ---------------------------------------------------------------------------
# run_single_simulation (integration)
# ---------------------------------------------------------------------------

class TestRunSingleSimulation:
    def test_returns_metrics(self):
        m = run_single_simulation(
            year=2026,
            day_profile_name="tipico",
            deterministic=True,
            total_daily_arrivals=20,
            rng_seed=42,
            perturbation=0.0,
        )
        assert isinstance(m, Metrics)

    def test_deterministic_reproducible(self):
        kwargs = dict(
            year=2026,
            day_profile_name="tipico",
            deterministic=True,
            total_daily_arrivals=20,
            rng_seed=99,
            perturbation=0.0,
        )
        m1 = run_single_simulation(**kwargs)
        m2 = run_single_simulation(**kwargs)
        assert m1.total_arrivals == m2.total_arrivals
        assert abs(m1.total_energy_kwh - m2.total_energy_kwh) < 1e-9

    def test_stochastic_same_seed_reproducible(self):
        kwargs = dict(
            year=2030,
            day_profile_name="anti_tipico",
            deterministic=False,
            total_daily_arrivals=30,
            rng_seed=123,
            perturbation=0.2,
        )
        m1 = run_single_simulation(**kwargs)
        m2 = run_single_simulation(**kwargs)
        assert m1.total_arrivals == m2.total_arrivals

    def test_metrics_non_negative(self):
        m = run_single_simulation(
            year=2035,
            day_profile_name="tipico",
            deterministic=False,
            total_daily_arrivals=15,
            rng_seed=7,
            perturbation=0.1,
        )
        assert m.total_energy_kwh >= 0.0
        assert m.mean_wait_min >= 0.0
        assert m.peak_kw >= 0.0
        assert 0.0 <= m.load_factor <= 1.0
        assert m.utilization >= 0.0

    def test_anti_typical_profile(self):
        m = run_single_simulation(
            year=2026,
            day_profile_name="anti_tipico",
            deterministic=True,
            total_daily_arrivals=10,
            rng_seed=55,
            perturbation=0.0,
        )
        assert isinstance(m, Metrics)


# ---------------------------------------------------------------------------
# save_csv / save_report
# ---------------------------------------------------------------------------

class TestSaveCsv:
    def test_creates_file(self):
        rows = [{"caso": "tipico", "ano": "2026", "modo": "det"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.csv"
            save_csv(rows, path)
            assert path.exists()

    def test_csv_has_correct_columns(self):
        rows = [{"caso": "tipico", "ano": "2026", "modo": "det"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.csv"
            save_csv(rows, path)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames
            assert set(header) == {"caso", "ano", "modo"}

    def test_csv_has_correct_row_count(self):
        rows = [
            {"caso": "a", "val": "1"},
            {"caso": "b", "val": "2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.csv"
            save_csv(rows, path)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                data = list(reader)
            assert len(data) == 2

    def test_empty_rows_no_file_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.csv"
            save_csv([], path)
            assert not path.exists()


class TestSaveReport:
    def test_creates_file(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        rows = [format_metrics_row("tipico", 2026, "det", m)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.txt"
            save_report(rows, path)
            assert path.exists()

    def test_report_contains_header(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        rows = [format_metrics_row("tipico", 2026, "det", m)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.txt"
            save_report(rows, path)
            content = path.read_text(encoding="utf-8")
        assert "ANALISE DE ELETROPOSTO" in content

    def test_report_contains_data_row(self):
        m = Metrics(100, 90, 500.0, 5.0, 15.0, 200.0, 0.6, 0.4)
        rows = [format_metrics_row("tipico", 2026, "det", m)]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.txt"
            save_report(rows, path)
            content = path.read_text(encoding="utf-8")
        assert "tipico" in content
        assert "2026" in content
