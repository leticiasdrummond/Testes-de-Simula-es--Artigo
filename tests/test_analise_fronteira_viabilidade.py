"""
Testes unitarios para funcoes puras de analise_fronteira_viabilidade.py.

Nao testamos funcoes que dependem do solver Gurobi (solve_model, find_feasible_frontier,
choose_solver) para manter os testes executaveis sem licenca de solver.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analise_fronteira_viabilidade import (
    PRACTICAL_UPPER_BOUNDS,
    UNIT_INTERVAL_PARAMS,
    apply_scalar_overrides,
    bisect_boundary,
    format_float,
    generate_samples,
    param_lower_bound,
    param_upper_bound,
    parse_scalar_params,
)


# ---------------------------------------------------------------------------
# parse_scalar_params
# ---------------------------------------------------------------------------

class TestParseScalarParams:
    def test_single_param(self):
        dat = "param tariff_ev := 1.5;"
        result = parse_scalar_params(dat)
        assert "tariff_ev" in result
        assert abs(result["tariff_ev"] - 1.5) < 1e-9

    def test_multiple_params(self):
        dat = "param tariff_ev := 1.5;\nparam eta_charge := 0.95;"
        result = parse_scalar_params(dat)
        assert abs(result["tariff_ev"] - 1.5) < 1e-9
        assert abs(result["eta_charge"] - 0.95) < 1e-9

    def test_empty_string(self):
        result = parse_scalar_params("")
        assert result == {}

    def test_no_matching_params(self):
        dat = "# just a comment\nset T := 1..24;"
        result = parse_scalar_params(dat)
        assert result == {}

    def test_integer_value(self):
        dat = "param operational_days_equivalent := 365;"
        result = parse_scalar_params(dat)
        assert abs(result["operational_days_equivalent"] - 365.0) < 1e-9

    def test_scientific_notation(self):
        dat = "param some_param := 1.5e-3;"
        result = parse_scalar_params(dat)
        assert abs(result["some_param"] - 0.0015) < 1e-12

    def test_non_numeric_value_skipped(self):
        dat = "param name := text_value;"
        result = parse_scalar_params(dat)
        assert "name" not in result

    def test_ignores_indexed_params(self):
        # Indexed param with '[' should not match scalar pattern
        dat = "param grid_price[1] := 0.5;\nparam tariff_ev := 2.0;"
        result = parse_scalar_params(dat)
        assert "tariff_ev" in result
        # grid_price[1] uses indexed form and should not match
        assert "grid_price[1]" not in result

    def test_leading_trailing_whitespace(self):
        dat = "   param tariff_ev := 3.0;   "
        result = parse_scalar_params(dat)
        assert "tariff_ev" in result

    def test_negative_value(self):
        dat = "param some_val := -2.5;"
        result = parse_scalar_params(dat)
        assert abs(result["some_val"] - (-2.5)) < 1e-9


# ---------------------------------------------------------------------------
# format_float
# ---------------------------------------------------------------------------

class TestFormatFloat:
    def test_normal_value(self):
        result = format_float(1.5)
        assert "1.5" in result or "1.50" in result

    def test_large_value_uses_scientific(self):
        result = format_float(1e5)
        assert "e" in result.lower()

    def test_small_value_uses_scientific(self):
        result = format_float(1e-4)
        assert "e" in result.lower()

    def test_zero(self):
        result = format_float(0.0)
        assert "0" in result

    def test_value_at_boundary_10000(self):
        # abs(x) >= 1e4 uses scientific
        result = format_float(10000.0)
        assert "e" in result.lower()

    def test_value_below_boundary(self):
        # abs(x) < 1e4 and >= 1e-3 uses decimal
        result = format_float(9999.0)
        assert "e" not in result.lower()

    def test_negative_value(self):
        result = format_float(-5.0)
        assert "-" in result

    def test_trailing_zeros_stripped(self):
        result = format_float(2.0)
        # Should not end in '0' or '.' after rstrip
        assert not result.endswith(".")
        # The value is recoverable
        assert abs(float(result) - 2.0) < 1e-6

    def test_round_trip_precision(self):
        for val in [0.1, 1.23456789, 0.000123, 12345.678]:
            result = format_float(val)
            recovered = float(result)
            assert abs(recovered - val) / max(abs(val), 1e-15) < 1e-6


# ---------------------------------------------------------------------------
# apply_scalar_overrides
# ---------------------------------------------------------------------------

class TestApplyScalarOverrides:
    def test_replaces_single_param(self):
        dat = "param tariff_ev := 1.5;\nparam eta_charge := 0.95;"
        result = apply_scalar_overrides(dat, {"tariff_ev": 2.0})
        assert "param tariff_ev := 2.0" in result or "param tariff_ev :=" in result
        # Verify the old value is replaced
        new_params = parse_scalar_params(result)
        assert abs(new_params["tariff_ev"] - 2.0) < 1e-9

    def test_non_matching_param_unchanged(self):
        dat = "param tariff_ev := 1.5;"
        result = apply_scalar_overrides(dat, {"non_existent": 99.0})
        assert result == dat

    def test_multiple_overrides(self):
        dat = "param tariff_ev := 1.5;\nparam eta_charge := 0.95;"
        result = apply_scalar_overrides(dat, {"tariff_ev": 3.0, "eta_charge": 0.90})
        new_params = parse_scalar_params(result)
        assert abs(new_params["tariff_ev"] - 3.0) < 1e-9
        assert abs(new_params["eta_charge"] - 0.90) < 1e-9

    def test_other_params_unchanged(self):
        dat = "param tariff_ev := 1.5;\nparam eta_charge := 0.95;\nparam capex_pv_kw := 5000.0;"
        result = apply_scalar_overrides(dat, {"tariff_ev": 2.0})
        new_params = parse_scalar_params(result)
        assert abs(new_params["eta_charge"] - 0.95) < 1e-9
        assert abs(new_params["capex_pv_kw"] - 5000.0) < 1e-9

    def test_empty_overrides_unchanged(self):
        dat = "param tariff_ev := 1.5;"
        result = apply_scalar_overrides(dat, {})
        assert result == dat

    def test_override_to_zero(self):
        dat = "param export_price_factor := 0.7;"
        result = apply_scalar_overrides(dat, {"export_price_factor": 0.0})
        new_params = parse_scalar_params(result)
        assert abs(new_params["export_price_factor"]) < 1e-9

    def test_override_preserves_non_param_content(self):
        dat = "# my comment\nparam tariff_ev := 1.5;\nset T := 1..24;"
        result = apply_scalar_overrides(dat, {"tariff_ev": 2.0})
        assert "# my comment" in result
        assert "set T := 1..24;" in result


# ---------------------------------------------------------------------------
# param_lower_bound
# ---------------------------------------------------------------------------

class TestParamLowerBound:
    def test_unit_interval_param_lower_bound_zero(self):
        for name in UNIT_INTERVAL_PARAMS:
            if name != "eta_discharge":
                lb = param_lower_bound(name)
                assert lb == 0.0, f"Expected 0.0 for {name}, got {lb}"

    def test_eta_discharge_small_positive(self):
        lb = param_lower_bound("eta_discharge")
        assert lb > 0.0
        assert lb < 0.01

    def test_general_param_lower_bound_zero(self):
        lb = param_lower_bound("tariff_ev")
        assert lb == 0.0

    def test_capex_lower_bound_zero(self):
        for name in ["capex_pv_kw", "capex_bess_kwh", "capex_trafo_kw"]:
            lb = param_lower_bound(name)
            assert lb == 0.0


# ---------------------------------------------------------------------------
# param_upper_bound
# ---------------------------------------------------------------------------

class TestParamUpperBound:
    def test_unit_interval_param_upper_bound_one(self):
        for name in UNIT_INTERVAL_PARAMS:
            ub = param_upper_bound(name, 0.5)
            assert ub == 1.0, f"Expected 1.0 for {name}, got {ub}"

    def test_practical_upper_bound_used(self):
        for name, expected_ub in PRACTICAL_UPPER_BOUNDS.items():
            if name not in UNIT_INTERVAL_PARAMS:
                ub = param_upper_bound(name, 1.0)
                assert ub == expected_ub, f"Expected {expected_ub} for {name}, got {ub}"

    def test_general_param_large_base(self):
        ub = param_upper_bound("some_param", 100.0)
        assert ub >= 100.0 * 100  # at least 100x the base

    def test_zero_base_general_param(self):
        ub = param_upper_bound("some_param", 0.0)
        assert ub == 1000.0

    def test_upper_bound_exceeds_base(self):
        base = 50.0
        ub = param_upper_bound("some_param", base)
        assert ub > base


# ---------------------------------------------------------------------------
# bisect_boundary
# ---------------------------------------------------------------------------

class TestBisectBoundary:
    def test_find_min_feasible(self):
        # feasible when x >= 5.0
        def check(v):
            return v >= 5.0

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=True, iterations=50)
        assert abs(result - 5.0) < 1e-6

    def test_find_max_feasible(self):
        # feasible when x <= 7.0
        def check(v):
            return v <= 7.0

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=False, iterations=50)
        assert abs(result - 7.0) < 1e-6

    def test_always_feasible_find_min(self):
        def check(v):
            return True

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=True, iterations=20)
        # Should converge near 0 (the low end)
        assert result <= 0.1

    def test_never_feasible_find_max(self):
        def check(v):
            return False

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=False, iterations=20)
        # Should converge near 0 (low end, as no feasible point found)
        assert result <= 1.0

    def test_single_iteration(self):
        def check(v):
            return v >= 5.0

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=True, iterations=1)
        # After one iteration: mid=5.0, feasible -> high=5.0
        assert abs(result - 5.0) < 1e-9

    def test_result_within_bounds(self):
        def check(v):
            return v >= 3.0

        result = bisect_boundary(check, 0.0, 10.0, find_min_feasible=True, iterations=30)
        assert 0.0 <= result <= 10.0


# ---------------------------------------------------------------------------
# generate_samples
# ---------------------------------------------------------------------------

class TestGenerateSamples:
    def test_includes_base_value(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=5)
        assert 5.0 in samples

    def test_sorted_output(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=7)
        assert samples == sorted(samples)

    def test_correct_count(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=5)
        # At least 5 points (may be more if base adds an extra)
        assert len(samples) >= 5

    def test_includes_endpoints(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=5)
        assert samples[0] == pytest.approx(0.0)
        assert samples[-1] == pytest.approx(10.0)

    def test_non_finite_range_returns_base(self):
        samples = generate_samples(base=5.0, lo=float("nan"), hi=10.0, n_points=5)
        assert samples == [5.0]

    def test_non_finite_hi_returns_base(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=float("inf"), n_points=5)
        assert samples == [5.0]

    def test_degenerate_range_returns_lo(self):
        samples = generate_samples(base=5.0, lo=5.0, hi=5.0, n_points=5)
        assert len(samples) == 1
        assert samples[0] == pytest.approx(5.0)

    def test_minimum_two_points(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=1)
        # n_points is clamped to at least 2
        assert len(samples) >= 2

    def test_all_samples_within_range(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=11)
        assert all(0.0 <= s <= 10.0 for s in samples)

    def test_zero_n_points_clamped(self):
        samples = generate_samples(base=5.0, lo=0.0, hi=10.0, n_points=0)
        assert len(samples) >= 2
