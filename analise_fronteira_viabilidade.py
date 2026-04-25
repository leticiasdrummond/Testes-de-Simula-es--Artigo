from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

from pyomo.environ import SolverFactory, value
from pyomo.opt import SolverStatus, TerminationCondition

from main import build_model


SCALAR_PARAM_PATTERN = re.compile(r"^\s*param\s+(\w+)\s*:=\s*([^;\s]+)\s*;", re.MULTILINE)

# Parametros principais para sensibilidade no espirito da Secao 5.4 do artigo.
DEFAULT_ANALYSIS_PARAMS = [
    "tariff_ev",
    "export_price_factor",
    "allow_grid_export",
    "capex_pv_kw",
    "capex_bess_kwh",
    "capex_trafo_kw",
    "crf_pv",
    "crf_bess",
    "crf_trafo",
    "om_pv_kw_year",
    "om_bess_kwh_year",
    "om_trafo_kw_year",
    "eta_charge",
    "eta_discharge",
    "soc_min_frac",
    "soc_max_frac",
    "soc_initial_frac",
    "c_rate_charge",
    "c_rate_discharge",
    "operational_days_equivalent",
    "E_bess_cap_max",
    "P_pv_cap_max",
    "P_trafo_cap_max",
]

# Parametros com faixa natural em [0, 1].
UNIT_INTERVAL_PARAMS = {
    "use_article_like_objective",
    "allow_grid_export",
    "export_price_factor",
    "eta_charge",
    "eta_discharge",
    "soc_min_frac",
    "soc_max_frac",
    "soc_initial_frac",
}

# Faixas superiores praticas para evitar exploracao infinita em parametros sem limite modelado.
PRACTICAL_UPPER_BOUNDS = {
    "tariff_ev": 10.0,
    "operational_days_equivalent": 3650.0,
    "c_rate_charge": 10.0,
    "c_rate_discharge": 10.0,
    "capex_pv_kw": 50000.0,
    "capex_bess_kwh": 50000.0,
    "capex_trafo_kw": 50000.0,
    "om_pv_kw_year": 5000.0,
    "om_bess_kwh_year": 5000.0,
    "om_trafo_kw_year": 5000.0,
    "crf_pv": 1.0,
    "crf_bess": 1.0,
    "crf_trafo": 1.0,
}


@dataclass
class FrontierResult:
    param: str
    base_value: float
    feasible_min: float
    feasible_max: float
    min_open: bool
    max_open: bool
    min_status: str
    max_status: str


@dataclass
class SolveResult:
    feasible: bool
    status: str
    metrics: dict[str, float] | None


def parse_scalar_params(dat_text: str) -> dict[str, float]:
    params: dict[str, float] = {}
    for name, raw_value in SCALAR_PARAM_PATTERN.findall(dat_text):
        try:
            params[name] = float(raw_value)
        except ValueError:
            continue
    return params


def format_float(x: float) -> str:
    if abs(x) >= 1e4 or (0 < abs(x) < 1e-3):
        return f"{x:.8e}"
    return f"{x:.10f}".rstrip("0").rstrip(".")


def apply_scalar_overrides(dat_text: str, overrides: dict[str, float]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in overrides:
            return f"param {name} := {format_float(overrides[name])};"
        return match.group(0)

    return SCALAR_PARAM_PATTERN.sub(replace, dat_text)


def choose_solver(preferred: str = "gurobi"):
    for solver_name in [preferred, "gurobi", "gurobi_direct"]:
        solver = SolverFactory(solver_name)
        if solver is not None and solver.available(False):
            return solver, solver_name
    raise RuntimeError(
        "Nenhum solver Gurobi disponivel (gurobi/gurobi_direct). Verifique instalacao/licenca."
    )


def solve_model(dat_text: str, solver) -> SolveResult:
    with NamedTemporaryFile("w", suffix=".dat", delete=False, encoding="utf-8") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(dat_text)

    try:
        model = build_model()
        instance = model.create_instance(str(tmp_path))
        results = solver.solve(instance, tee=False)

        term_ok = results.solver.termination_condition in {
            TerminationCondition.optimal,
            TerminationCondition.locallyOptimal,
            TerminationCondition.feasible,
        }
        status_ok = results.solver.status in {
            SolverStatus.ok,
            SolverStatus.warning,
        }

        if not (status_ok and term_ok):
            return SolveResult(
                feasible=False,
                status=f"status={results.solver.status}; term={results.solver.termination_condition}",
                metrics=None,
            )

        dt = value(instance.delta_t)
        days = value(instance.operational_days_equivalent)

        annual_revenue_ev = sum(
            value(instance.tariff_ev) * value(instance.P_EV_load[t]) * dt for t in instance.T
        ) * days
        annual_revenue_export = sum(
            value(instance.export_price_factor)
            * value(instance.grid_price[t])
            * value(instance.P_grid_export[t])
            * dt
            for t in instance.T
        ) * days
        annual_cost_import = sum(
            value(instance.grid_price[t]) * value(instance.P_grid_import[t]) * dt for t in instance.T
        ) * days

        annual_ev_energy = sum(value(instance.P_EV_load[t]) * dt for t in instance.T) * days
        annual_grid_import = sum(value(instance.P_grid_import[t]) * dt for t in instance.T) * days
        annual_grid_export = sum(value(instance.P_grid_export[t]) * dt for t in instance.T) * days
        annual_pv_gen = sum(value(instance.P_pv_gen[t]) * dt for t in instance.T) * days
        annual_pv_avail = (
            sum(value(instance.irradiance_cf[t]) * dt for t in instance.T) * value(instance.P_pv_cap) * days
        )
        annual_pv_curtail = max(annual_pv_avail - annual_pv_gen, 0.0)

        energy_eff = 0.0
        denom_eff = annual_pv_gen + annual_grid_import
        if denom_eff > 1e-9:
            energy_eff = 100.0 * (annual_ev_energy + annual_grid_export) / denom_eff

        pv_loss_rate = 0.0
        if annual_pv_avail > 1e-9:
            pv_loss_rate = 100.0 * annual_pv_curtail / annual_pv_avail

        co2_reduction_proxy = 0.0
        if annual_ev_energy > 1e-9:
            # Proxy simples alinhado ao cap. 5: menor dependencia de rede implica menor emissao.
            co2_reduction_proxy = 100.0 * (1.0 - annual_grid_import / annual_ev_energy)

        metrics = {
            "objective": float(value(instance.Obj)),
            "annual_operational_profit": float(annual_revenue_ev + annual_revenue_export - annual_cost_import),
            "annual_revenue_ev": float(annual_revenue_ev),
            "annual_revenue_export": float(annual_revenue_export),
            "annual_cost_import": float(annual_cost_import),
            "pv_capacity_kw": float(value(instance.P_pv_cap)),
            "bess_capacity_kwh": float(value(instance.E_bess_cap)),
            "trafo_capacity_kw": float(value(instance.P_trafo_cap)),
            "annual_grid_import_kwh": float(annual_grid_import),
            "annual_grid_export_kwh": float(annual_grid_export),
            "annual_pv_gen_kwh": float(annual_pv_gen),
            "annual_pv_curtail_kwh": float(annual_pv_curtail),
            "pv_loss_rate_pct": float(pv_loss_rate),
            "energy_eff_pct": float(energy_eff),
            "co2_reduction_proxy_pct": float(co2_reduction_proxy),
        }

        return SolveResult(feasible=True, status="optimal/feasible", metrics=metrics)
    except Exception as exc:  # noqa: BLE001
        return SolveResult(feasible=False, status=f"exception={exc}", metrics=None)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def param_lower_bound(name: str) -> float:
    if name in UNIT_INTERVAL_PARAMS:
        if name == "eta_discharge":
            return 1e-4
        return 0.0
    if name == "eta_discharge":
        return 1e-4
    return 0.0


def param_upper_bound(name: str, base_value: float) -> float:
    if name in UNIT_INTERVAL_PARAMS:
        return 1.0
    if name in PRACTICAL_UPPER_BOUNDS:
        return PRACTICAL_UPPER_BOUNDS[name]
    if base_value <= 0:
        return 1000.0
    return max(100.0 * base_value, base_value + 1000.0)


def bisect_boundary(
    feasibility_check: Callable[[float], bool],
    low: float,
    high: float,
    *,
    find_min_feasible: bool,
    iterations: int = 50,
) -> float:
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        ok = feasibility_check(mid)
        if find_min_feasible:
            if ok:
                high = mid
            else:
                low = mid
        else:
            if ok:
                low = mid
            else:
                high = mid
    return high if find_min_feasible else low


def find_feasible_frontier(
    param_name: str,
    base_value: float,
    dat_text: str,
    solver,
    *,
    max_expand_steps: int,
) -> FrontierResult:
    lower_limit = param_lower_bound(param_name)
    upper_limit = param_upper_bound(param_name, base_value)

    def is_feasible(v: float) -> bool:
        v_clamped = min(max(v, lower_limit), upper_limit)
        modified = apply_scalar_overrides(dat_text, {param_name: v_clamped})
        result = solve_model(modified, solver)
        return result.feasible

    base_ok = is_feasible(base_value)
    if not base_ok:
        return FrontierResult(
            param=param_name,
            base_value=base_value,
            feasible_min=float("nan"),
            feasible_max=float("nan"),
            min_open=False,
            max_open=False,
            min_status="base_infeasible",
            max_status="base_infeasible",
        )

    # Fronteira inferior.
    if base_value <= lower_limit + 1e-12:
        feasible_min = lower_limit
        min_open = True
        min_status = "atingiu_limite_inferior"
    else:
        hi = base_value
        lo = base_value
        found_infeasible = False

        for _ in range(max_expand_steps):
            candidate = max(lower_limit, lo / 2.0)
            if candidate == lo:
                break
            lo = candidate
            if not is_feasible(lo):
                found_infeasible = True
                break
            if lo <= lower_limit + 1e-12:
                break

        if found_infeasible:
            feasible_min = bisect_boundary(is_feasible, lo, hi, find_min_feasible=True)
            min_open = False
            min_status = "fronteira_identificada"
        else:
            feasible_min = lower_limit
            min_open = True
            min_status = "atingiu_limite_inferior"

    # Fronteira superior.
    hi = base_value
    lo = base_value
    found_infeasible = False

    for _ in range(max_expand_steps):
        if hi <= 0:
            candidate = hi + 1.0
        else:
            candidate = hi * 2.0
        candidate = min(candidate, upper_limit)
        if candidate == hi:
            break
        hi = candidate
        if not is_feasible(hi):
            found_infeasible = True
            break
        lo = hi
        if hi >= upper_limit - 1e-12:
            break

    if found_infeasible:
        feasible_max = bisect_boundary(is_feasible, lo, hi, find_min_feasible=False)
        max_open = False
        max_status = "fronteira_identificada"
    else:
        feasible_max = upper_limit
        max_open = True
        max_status = "atingiu_limite_superior"

    return FrontierResult(
        param=param_name,
        base_value=base_value,
        feasible_min=float(feasible_min),
        feasible_max=float(feasible_max),
        min_open=min_open,
        max_open=max_open,
        min_status=min_status,
        max_status=max_status,
    )


def generate_samples(base: float, lo: float, hi: float, n_points: int) -> list[float]:
    if not math.isfinite(lo) or not math.isfinite(hi):
        return [base]
    if abs(hi - lo) <= 1e-12:
        return [float(lo)]

    n_points = max(2, int(n_points))
    step = (hi - lo) / (n_points - 1)
    values = set(float(lo + i * step) for i in range(n_points))
    values.add(float(base))
    return sorted(values)


def build_graphics_html(
    frontier_rows: list[dict[str, float | str | bool]],
    sensitivity_rows: list[dict[str, float | str | int]],
    output_dir: Path,
) -> None:
    plots_dir = output_dir / "graficos"
    plots_dir.mkdir(parents=True, exist_ok=True)

    html_path = plots_dir / "analise_grafica.html"
    html = f"""<!doctype html>
<html lang=\"pt-br\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Analise Grafica - Fronteira e Sensibilidade</title>
    <script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
    <style>
        :root {{
            --bg: #f6f8f9;
            --card: #ffffff;
            --ink: #1f2933;
            --accent: #0f766e;
            --accent2: #c2410c;
            --line: #d9e2ec;
        }}
        body {{
            margin: 0;
            background: radial-gradient(circle at top right, #e4f5f2 0%, var(--bg) 45%);
            color: var(--ink);
            font-family: "Segoe UI", Tahoma, sans-serif;
        }}
        .wrap {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; margin-bottom: 16px; padding: 12px; }}
        h1 {{ margin: 0 0 12px; font-size: 1.4rem; }}
        .controls {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }}
        select {{ padding: 6px; border-radius: 8px; border: 1px solid var(--line); }}
        .grid {{ display: grid; gap: 14px; grid-template-columns: 1fr; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"card\">
            <h1>Fronteira de Viabilidade e Sensibilidade</h1>
            <div>Relatorio grafico interativo alinhado ao Cap. 5 (resultado + sensibilidade).</div>
        </div>
        <div class=\"card\"><div id=\"frontier\" style=\"height: 520px;\"></div></div>
        <div class=\"card\">
            <div class=\"controls\">
                <label for=\"param\">Parametro:</label>
                <select id=\"param\"></select>
            </div>
            <div class=\"grid\">
                <div id=\"sens_obj\" style=\"height: 360px;\"></div>
                <div id=\"sens_cap\" style=\"height: 360px;\"></div>
            </div>
        </div>
    </div>
    <script>
        const frontierData = {json.dumps(frontier_rows, ensure_ascii=False)};
        const sensData = {json.dumps(sensitivity_rows, ensure_ascii=False)};

        const y = frontierData.map(r => r.param);
        const xMin = frontierData.map(r => Number(r.feasible_min));
        const xMax = frontierData.map(r => Number(r.feasible_max));
        const xBase = frontierData.map(r => Number(r.base_value));
        const xWidth = xMax.map((v, i) => v - xMin[i]);

        Plotly.newPlot('frontier', [
            {{
                type: 'bar',
                orientation: 'h',
                y: y,
                x: xWidth,
                base: xMin,
                marker: {{ color: 'rgba(15,118,110,0.65)' }},
                name: 'intervalo viavel'
            }},
            {{
                type: 'scatter',
                mode: 'markers',
                y: y,
                x: xBase,
                marker: {{ color: '#c2410c', size: 8 }},
                name: 'valor base'
            }}
        ], {{
            title: 'Fronteira de viabilidade por parametro',
            barmode: 'overlay',
            xaxis: {{ title: 'valor do parametro' }},
            yaxis: {{ automargin: true }},
            margin: {{ l: 170, r: 30, t: 60, b: 50 }}
        }}, {{responsive: true}});

        const params = [...new Set(sensData.map(r => r.param))];
        const sel = document.getElementById('param');
        params.forEach(p => {{
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            sel.appendChild(opt);
        }});

        function renderParam(param) {{
            const rows = sensData
                .filter(r => r.param === param && Number(r.feasible) === 1)
                .sort((a, b) => Number(a.value) - Number(b.value));

            const x = rows.map(r => Number(r.value));

            Plotly.newPlot('sens_obj', [
                {{ x: x, y: rows.map(r => Number(r.objective)), mode: 'lines+markers', name: 'Objetivo', line: {{color: '#1d3557'}} }},
                {{ x: x, y: rows.map(r => Number(r.annual_operational_profit)), mode: 'lines+markers', name: 'Lucro operacional anual', line: {{color: '#457b9d'}} }}
            ], {{
                title: `Desempenho economico vs ${{param}}`,
                xaxis: {{ title: param }},
                yaxis: {{ title: 'BRL' }},
                margin: {{ l: 70, r: 20, t: 50, b: 60 }}
            }}, {{responsive: true}});

            Plotly.newPlot('sens_cap', [
                {{ x: x, y: rows.map(r => Number(r.pv_capacity_kw)), mode: 'lines+markers', name: 'PV (kW)', line: {{color: '#2a9d8f'}} }},
                {{ x: x, y: rows.map(r => Number(r.bess_capacity_kwh)), mode: 'lines+markers', name: 'BESS (kWh)', line: {{color: '#f4a261'}} }},
                {{ x: x, y: rows.map(r => Number(r.trafo_capacity_kw)), mode: 'lines+markers', name: 'Trafo (kW)', line: {{color: '#264653'}} }}
            ], {{
                title: `Capacidades otimizadas vs ${{param}}`,
                xaxis: {{ title: param }},
                yaxis: {{ title: 'capacidade' }},
                margin: {{ l: 70, r: 20, t: 50, b: 60 }}
            }}, {{responsive: true}});
        }}

        sel.addEventListener('change', () => renderParam(sel.value));
        if (params.length > 0) {{
            sel.value = params[0];
            renderParam(params[0]);
        }}
    </script>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def group_by_param(rows: list[dict[str, float | str | int]]) -> dict[str, list[dict[str, float | str | int]]]:
    grouped: dict[str, list[dict[str, float | str | int]]] = {}
    for row in rows:
        p = str(row["param"])
        grouped.setdefault(p, []).append(row)
    for p in grouped:
        grouped[p].sort(key=lambda r: float(r["value"]))
    return grouped


def relative_impact(base: float, low: float, high: float) -> float:
    if abs(base) <= 1e-12:
        return 0.0
    return max(abs((high - base) / base), abs((low - base) / base)) * 100.0


def write_report(
    output_dir: Path,
    solver_name: str,
    base_metrics: dict[str, float],
    frontier_rows: list[dict[str, float | str | bool]],
    sensitivity_rows: list[dict[str, float | str | int]],
) -> None:
    report_path = output_dir / "relatorio_fronteira_sensibilidade.txt"

    lines: list[str] = []
    lines.append("RELATORIO - FRONTEIRA DE VIABILIDADE E ANALISE DE SENSIBILIDADE")
    lines.append("")
    lines.append("Base metodologica: Secao 5 do artigo (Results and discussion), com foco em:")
    lines.append("- Analise de resultado de otimizacao (capacidade, desempenho economico e tecnico)")
    lines.append("- Sensibilidade de parametros-chave")
    lines.append("- Diretrizes de projeto a partir dos limites de viabilidade")
    lines.append("")
    lines.append(f"Solver utilizado: {solver_name}")
    lines.append("")
    lines.append("1) RESULTADO BASE DA OTIMIZACAO")
    lines.append(f"- Funcao objetivo: {base_metrics['objective']:,.2f}")
    lines.append(f"- Lucro operacional anual: {base_metrics['annual_operational_profit']:,.2f}")
    lines.append(f"- PV otimizado (kW): {base_metrics['pv_capacity_kw']:.3f}")
    lines.append(f"- BESS otimizado (kWh): {base_metrics['bess_capacity_kwh']:.3f}")
    lines.append(f"- Transformador otimizado (kW): {base_metrics['trafo_capacity_kw']:.3f}")
    lines.append(f"- Taxa de perda PV (% proxy): {base_metrics['pv_loss_rate_pct']:.2f}")
    lines.append(f"- Eficiencia energetica (%): {base_metrics['energy_eff_pct']:.2f}")
    lines.append(f"- Reducao de CO2 (% proxy): {base_metrics['co2_reduction_proxy_pct']:.2f}")
    lines.append("")

    lines.append("2) FRONTEIRA DE VIABILIDADE (MIN-MAX)")
    for row in frontier_rows:
        lo_note = "(aberto)" if bool(row["min_open"]) else ""
        hi_note = "(aberto)" if bool(row["max_open"]) else ""
        lines.append(
            f"- {row['param']}: min={float(row['feasible_min']):.6g} {lo_note} | "
            f"base={float(row['base_value']):.6g} | max={float(row['feasible_max']):.6g} {hi_note}"
        )
    lines.append("")

    lines.append("3) SENSIBILIDADE - SINTese ORIENTADA AO CAP. 5")
    if not sensitivity_rows:
        lines.append("- Nenhum ponto de sensibilidade foi resolvido.")
    else:
        feasible_only = [r for r in sensitivity_rows if int(r["feasible"]) == 1]
        impact_rows = []
        grouped = group_by_param(feasible_only)

        for param, grp in grouped.items():
            if not grp:
                continue
            base_candidates = [r for r in grp if int(r["is_base"]) == 1]
            base_row = base_candidates[0] if base_candidates else grp[len(grp) // 2]
            low_row = grp[0]
            high_row = grp[-1]
            impact_rows.append(
                {
                    "param": param,
                    "impact_obj_pct": relative_impact(
                        float(base_row.get("objective", 0.0)),
                        float(low_row.get("objective", 0.0)),
                        float(high_row.get("objective", 0.0)),
                    ),
                    "impact_pv_pct": relative_impact(
                        float(base_row.get("pv_capacity_kw", 0.0)),
                        float(low_row.get("pv_capacity_kw", 0.0)),
                        float(high_row.get("pv_capacity_kw", 0.0)),
                    ),
                    "impact_bess_pct": relative_impact(
                        float(base_row.get("bess_capacity_kwh", 0.0)),
                        float(low_row.get("bess_capacity_kwh", 0.0)),
                        float(high_row.get("bess_capacity_kwh", 0.0)),
                    ),
                    "impact_grid_pct": relative_impact(
                        float(base_row.get("annual_grid_import_kwh", 0.0)),
                        float(low_row.get("annual_grid_import_kwh", 0.0)),
                        float(high_row.get("annual_grid_import_kwh", 0.0)),
                    ),
                }
            )

        impact_rows.sort(key=lambda r: float(r["impact_obj_pct"]), reverse=True)
        lines.append("- Ranking por impacto na funcao objetivo (variacao relativa maxima):")
        for row in impact_rows[:10]:
            lines.append(
                f"  * {row['param']}: Obj={float(row['impact_obj_pct']):.2f}% | "
                f"PV={float(row['impact_pv_pct']):.2f}% | "
                f"BESS={float(row['impact_bess_pct']):.2f}% | "
                f"Rede={float(row['impact_grid_pct']):.2f}%"
            )

        lines.append("")
        lines.append("- Leitura tecnica e economica:")
        lines.append("  * Parametros tarifarios e de custo tendem a alterar fortemente a funcao objetivo.")
        lines.append("  * Limites fisicos (P_trafo_cap_max, P_pv_cap_max, E_bess_cap_max) governam viabilidade operacional.")
        lines.append("  * Parametros de eficiencia e SOC afetam arbitragem temporal e uso da bateria.")

    lines.append("")
    lines.append("4) ARQUIVOS GERADOS")
    lines.append("- fronteira_viabilidade.csv")
    lines.append("- sensibilidade_resultados.csv")
    lines.append("- graficos/analise_grafica.html")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analise automatica da fronteira de viabilidade e sensibilidade do modelo Pyomo."
    )
    parser.add_argument("--data-file", default="dados_exemplo.dat", help="Arquivo .dat base")
    parser.add_argument(
        "--output-dir",
        default="saida_fronteira_viabilidade",
        help="Pasta de saida para csv, graficos e relatorio",
    )
    parser.add_argument("--solver", default="gurobi", help="Solver preferido")
    parser.add_argument("--samples", type=int, default=9, help="Numero de amostras por parametro")
    parser.add_argument(
        "--max-expand-steps",
        type=int,
        default=16,
        help="Passos de expansao para achar fronteiras",
    )
    parser.add_argument(
        "--params",
        default="",
        help="Lista separada por virgula de parametros a analisar. Vazio usa lista padrao.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Executa versao curta (menos parametros) para validacao rapida.",
    )

    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    data_path = (base_dir / args.data_file).resolve()
    output_dir = (base_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dat_text = data_path.read_text(encoding="utf-8")
    scalar_params = parse_scalar_params(dat_text)

    if args.params.strip():
        requested = [p.strip() for p in args.params.split(",") if p.strip()]
        params = [p for p in requested if p in scalar_params]
    else:
        params = [p for p in DEFAULT_ANALYSIS_PARAMS if p in scalar_params]

    if args.quick:
        params = [p for p in params if p in {"tariff_ev", "P_trafo_cap_max", "eta_discharge", "capex_bess_kwh"}]

    if not params:
        raise RuntimeError("Nenhum parametro valido para analise foi selecionado.")

    solver, solver_name = choose_solver(args.solver)

    base_solve = solve_model(dat_text, solver)
    if not base_solve.feasible or base_solve.metrics is None:
        raise RuntimeError(f"Cenario base nao resolveu: {base_solve.status}")

    print(f"Solver ativo: {solver_name}")
    print(f"Parametros em analise: {len(params)}")

    frontier_rows: list[dict[str, float | str | bool]] = []
    sensitivity_rows: list[dict[str, float | str | int]] = []

    for idx, param_name in enumerate(params, start=1):
        base_value = scalar_params[param_name]
        print(f"[{idx}/{len(params)}] Fronteira de viabilidade -> {param_name}")

        frontier = find_feasible_frontier(
            param_name,
            base_value,
            dat_text,
            solver,
            max_expand_steps=args.max_expand_steps,
        )

        frontier_rows.append(
            {
                "param": frontier.param,
                "base_value": frontier.base_value,
                "feasible_min": frontier.feasible_min,
                "feasible_max": frontier.feasible_max,
                "min_open": frontier.min_open,
                "max_open": frontier.max_open,
                "min_status": frontier.min_status,
                "max_status": frontier.max_status,
            }
        )

        sample_values = generate_samples(
            base=frontier.base_value,
            lo=frontier.feasible_min,
            hi=frontier.feasible_max,
            n_points=args.samples,
        )

        for v in sample_values:
            modified = apply_scalar_overrides(dat_text, {param_name: v})
            solve = solve_model(modified, solver)

            row: dict[str, float | str | int] = {
                "param": param_name,
                "value": float(v),
                "base_value": float(base_value),
                "is_base": 1 if abs(v - base_value) <= 1e-9 else 0,
                "feasible": 1 if solve.feasible else 0,
                "status": solve.status,
            }

            if solve.feasible and solve.metrics is not None:
                row.update(solve.metrics)
            else:
                row.update(
                    {
                        "objective": "",
                        "annual_operational_profit": "",
                        "pv_capacity_kw": "",
                        "bess_capacity_kwh": "",
                        "trafo_capacity_kw": "",
                        "annual_grid_import_kwh": "",
                        "annual_grid_export_kwh": "",
                        "annual_pv_gen_kwh": "",
                        "annual_pv_curtail_kwh": "",
                        "pv_loss_rate_pct": "",
                        "energy_eff_pct": "",
                        "co2_reduction_proxy_pct": "",
                        "annual_revenue_ev": "",
                        "annual_revenue_export": "",
                        "annual_cost_import": "",
                    }
                )

            sensitivity_rows.append(row)

    frontier_rows.sort(key=lambda r: str(r["param"]))
    sensitivity_rows.sort(key=lambda r: (str(r["param"]), float(r["value"])))

    frontier_path = output_dir / "fronteira_viabilidade.csv"
    sensitivity_path = output_dir / "sensibilidade_resultados.csv"

    write_csv(frontier_path, frontier_rows)
    write_csv(sensitivity_path, sensitivity_rows)

    build_graphics_html(frontier_rows, sensitivity_rows, output_dir)
    write_report(output_dir, solver_name, base_solve.metrics, frontier_rows, sensitivity_rows)

    print(f"Relatorio: {output_dir / 'relatorio_fronteira_sensibilidade.txt'}")
    print(f"CSV fronteira: {frontier_path}")
    print(f"CSV sensibilidade: {sensitivity_path}")
    print(f"Graficos: {output_dir / 'graficos' / 'analise_grafica.html'}")


if __name__ == "__main__":
    main()
