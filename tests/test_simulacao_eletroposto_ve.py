import math
import random

import pytest

import simulacao_eletroposto_ve as sim


def _make_charger(power_kw: float, is_dc: bool, available_at_min: float = 0.0) -> sim.ChargerUnit:
    return sim.ChargerUnit(
        id_name=f"{'DC' if is_dc else 'AC'}_{power_kw}",
        power_kw=power_kw,
        is_dc=is_dc,
        available_at_min=available_at_min,
    )


def test_normalize_profile_handles_negative_and_zero_sum():
    assert sim.normalize_profile([2, -1, 1]) == [2 / 3, 0.0, 1 / 3]
    assert sim.normalize_profile([0, 0, -5]) == [1 / 3, 1 / 3, 1 / 3]


def test_base_vehicle_mix_and_charger_park_year_buckets():
    early = sim.base_vehicle_mix_brasil(2026)
    mid = sim.base_vehicle_mix_brasil(2030)
    late = sim.base_vehicle_mix_brasil(2035)
    assert math.isclose(sum(early.values()), 1.0)
    assert math.isclose(sum(mid.values()), 1.0)
    assert math.isclose(sum(late.values()), 1.0)
    assert early != mid != late

    park_early = sim.charger_park_by_year(2026)
    park_mid = sim.charger_park_by_year(2030)
    park_late = sim.charger_park_by_year(2035)
    assert sum(park_early.values()) == 12
    assert sum(park_mid.values()) == 15
    assert sum(park_late.values()) == 17


def test_hourly_profiles_are_normalized_and_distinct():
    typical = sim.hourly_profile_typical()
    anti = sim.hourly_profile_anti_typical()
    assert len(typical) == 24
    assert len(anti) == 24
    assert math.isclose(sum(typical), 1.0)
    assert math.isclose(sum(anti), 1.0)
    assert typical != anti


def test_expand_hourly_to_slots_expands_and_normalizes():
    hourly = [1.0] * 24
    slots = sim.expand_hourly_to_slots(hourly)
    assert len(slots) == sim.SLOTS_PER_DAY
    assert math.isclose(sum(slots), 1.0, rel_tol=0, abs_tol=1e-12)
    assert len(set(slots)) == 1


def test_weighted_choice_falls_back_to_last_item_when_needed():
    items = {"a": 0.2, "b": 0.3, "c": 0.1}
    rng = random.Random(2)
    assert rng.random() > 0.6
    rng = random.Random(2)
    assert sim.weighted_choice(rng, items) == "c"


def test_build_charger_units_and_weighted_choice_standard_selection():
    ac = sim.ChargerTech("ac", 7.4, False)
    dc = sim.ChargerTech("dc", 60.0, True)
    units = sim.build_charger_units({ac: 2, dc: 1})
    assert [u.id_name for u in units] == ["ac_1", "ac_2", "dc_1"]
    rng = random.Random(1)
    assert sim.weighted_choice(rng, {"x": 0.9, "y": 0.1}) == "x"


def test_sampled_arrival_soc_is_bounded_for_both_profiles():
    rng = random.Random(123)
    for anti in (True, False):
        for _ in range(200):
            soc = sim.sampled_arrival_soc(rng, anti_typical=anti)
            assert 0.08 <= soc <= 0.75


def test_sample_energy_need_kwh_respects_target_soc():
    tech = sim.VehicleTech("car", battery_kwh=50.0, ac_limit_kw=7.0, dc_limit_kw=60.0, target_soc=0.85)
    rng = random.Random(5)
    assert sim.sample_energy_need_kwh(tech, arrival_soc=0.95, rng=rng) >= 4.0
    assert sim.sample_energy_need_kwh(tech, arrival_soc=0.50, rng=rng) == (0.85 - 0.50) * 50.0


def test_effective_and_realistic_charging_power_behaviors():
    tech = sim.VehicleTech("car", battery_kwh=50.0, ac_limit_kw=7.4, dc_limit_kw=70.0, target_soc=0.85)
    ac = _make_charger(22.0, is_dc=False)
    dc = _make_charger(120.0, is_dc=True)

    assert sim.effective_charging_power(tech, ac) == 7.4
    assert sim.effective_charging_power(tech, dc) == 70.0
    assert sim.realistic_charging_power(0.10, 100.0, True) == 85.0
    assert sim.realistic_charging_power(0.50, 100.0, True) == 100.0
    assert sim.realistic_charging_power(0.99, 100.0, True) >= 5.0


def test_charging_duration_has_minimum_and_cap():
    short = sim.charging_duration_min_nonlinear(
        energy_need_kwh=0.0,
        battery_kwh=60.0,
        arrival_soc=0.5,
        target_soc=0.8,
        max_power_kw=50.0,
        is_dc=True,
        efficiency=0.9,
    )
    long = sim.charging_duration_min_nonlinear(
        energy_need_kwh=500.0,
        battery_kwh=60.0,
        arrival_soc=0.1,
        target_soc=1.0,
        max_power_kw=10.0,
        is_dc=False,
        efficiency=0.9,
    )
    assert short == 1.0
    assert long == 240.0


def test_preferred_charger_pool_prefers_ac_for_small_energy():
    chargers = [_make_charger(7.4, False), _make_charger(60.0, True)]
    small = sim.preferred_charger_pool(10.0, chargers)
    large = sim.preferred_charger_pool(30.0, chargers)
    assert all(not c.is_dc for c in small)
    assert all(c.is_dc for c in large)


def test_preferred_charger_pool_fallback_without_dc():
    chargers = [_make_charger(7.4, False)]
    assert sim.preferred_charger_pool(40.0, chargers) == chargers


def test_assign_vehicle_uses_best_available_preferred_charger():
    tech = sim.VehicleTech("car", battery_kwh=50.0, ac_limit_kw=7.4, dc_limit_kw=120.0, target_soc=0.85)
    chargers = [_make_charger(7.4, False, available_at_min=20.0), _make_charger(22.0, False, available_at_min=0.0)]

    session = sim.assign_vehicle(
        arrival_min=10.0,
        energy_need_kwh=5.0,
        arrival_soc=0.4,
        tech=tech,
        chargers=chargers,
        charging_efficiency=0.93,
    )
    assert session.start_min == 10.0
    assert session.wait_min == 0.0
    assert session.charger_power_kw == 7.4
    assert chargers[1].available_at_min == session.end_min


def test_assign_vehicle_hits_fallback_branch_when_power_limits_are_zero():
    tech = sim.VehicleTech("weak", battery_kwh=20.0, ac_limit_kw=0.0, dc_limit_kw=0.0, target_soc=0.8)
    chargers = [_make_charger(7.4, False, available_at_min=0.0)]
    session = sim.assign_vehicle(
        arrival_min=0.0,
        energy_need_kwh=1.0,
        arrival_soc=0.2,
        tech=tech,
        chargers=chargers,
        charging_efficiency=0.9,
    )
    assert session.charger_power_kw == 0.1
    assert session.end_min >= 1.0


def test_poisson_draw_edge_cases():
    rng = random.Random(42)
    assert sim.poisson_draw(rng, 0.0) == 0
    assert sim.poisson_draw(rng, -1.0) == 0
    assert sim.poisson_draw(rng, 100.0) >= 0


def test_load_series_and_summarize_metrics():
    sessions = [
        sim.Session(arrival_min=0, start_min=0, end_min=30, energy_kwh=10, charger_power_kw=20, wait_min=0),
        sim.Session(arrival_min=5, start_min=15, end_min=45, energy_kwh=8, charger_power_kw=10, wait_min=10),
    ]
    load = sim.load_series_from_sessions(sessions)
    assert len(load) == sim.SLOTS_PER_DAY
    assert load[0] == 20.0
    assert load[1] == 30.0
    assert load[2] == 10.0
    metrics = sim.summarize(sessions, n_arrivals=2, n_chargers=2)
    assert metrics.served == 2
    assert metrics.total_energy_kwh == 18
    assert metrics.p95_wait_min == 0
    assert metrics.peak_kw == 30.0
    assert metrics.utilization > 0


def test_summarize_empty_returns_zero_metrics():
    m = sim.summarize([], n_arrivals=3, n_chargers=2)
    assert m.total_arrivals == 3
    assert m.served == 0
    assert m.total_energy_kwh == 0.0


def test_run_single_simulation_and_mean_metrics_empty():
    det = sim.run_single_simulation(
        year=2026,
        day_profile_name="tipico",
        deterministic=True,
        total_daily_arrivals=8,
        rng_seed=1234,
        perturbation=0.0,
    )
    stoch = sim.run_single_simulation(
        year=2026,
        day_profile_name="anti_tipico",
        deterministic=False,
        total_daily_arrivals=8,
        rng_seed=1235,
        perturbation=0.2,
    )
    assert det.total_arrivals >= det.served
    assert stoch.total_arrivals >= stoch.served
    assert sim.mean_metrics([]) == sim.Metrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_arrival_generators_and_aggregation_helpers():
    slot_profile = [1 / sim.SLOTS_PER_DAY] * sim.SLOTS_PER_DAY
    det = sim.deterministic_arrivals(96, slot_profile)
    assert len(det) == 96
    assert det[0] == sim.SLOT_MIN / 2

    rng = random.Random(7)
    stoch = sim.stochastic_arrivals(rng, 80.0, slot_profile, perturbation=0.2)
    assert stoch == sorted(stoch)
    assert all(0.0 <= x < sim.MIN_PER_DAY for x in stoch)

    avg = sim.mean_metrics(
        [
            sim.Metrics(10, 8, 40.0, 5.0, 9.0, 30.0, 0.5, 0.4),
            sim.Metrics(12, 10, 44.0, 7.0, 12.0, 34.0, 0.6, 0.5),
        ]
    )
    assert avg.total_arrivals == 11
    assert avg.served == 9
    assert avg.total_energy_kwh == 42.0

    row = sim.format_metrics_row("tipico", 2026, "det", avg)
    assert row["caso"] == "tipico"
    assert row["ano"] == "2026"
    assert row["modo"] == "det"


def test_save_csv_save_report_and_main(tmp_path, monkeypatch, capsys):
    rows = [{"caso": "c1", "ano": "2026", "modo": "det", "chegadas": "1", "atendidos": "1", "energia_kwh": "1.00",
             "espera_media_min": "0.00", "espera_p95_min": "0.00", "pico_kw": "1.00", "fator_carga": "1.0000", "utilizacao": "0.1000"}]
    csv_path = tmp_path / "out.csv"
    report_path = tmp_path / "out.txt"
    sim.save_csv(rows, csv_path)
    sim.save_report(rows, report_path)
    assert csv_path.exists()
    assert report_path.exists()
    assert "ANALISE DE ELETROPOSTO" in report_path.read_text(encoding="utf-8")

    monkeypatch.setattr(sim, "run_study", lambda: rows)
    monkeypatch.setattr(sim, "save_csv", lambda _rows, _path: None)
    monkeypatch.setattr(sim, "save_report", lambda _rows, _path: None)
    sim.main()
    out = capsys.readouterr().out
    assert "Analise concluida." in out
