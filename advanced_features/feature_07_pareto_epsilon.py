"""
Feature 7 — Otimização Multi-objetivo com Fronteira de Pareto (ε-constraint)
=============================================================================

Objetivo
--------
Substituir a função objetivo escalarizada com pesos ad-hoc (w_ens, w_grid_import)
por uma análise de Pareto explícita usando o método ε-constraint, eliminando a
subjetividade na escolha dos pesos e fornecendo uma visão completa dos trade-offs.

Método ε-constraint
-------------------
Dado o problema bi-objetivo:
    min  f1(x) = CAPEX_anualizado + O&M_anual
    min  f2(x) = EENS_esperado  (Energy Not Served)

O método ε-constraint transforma em:
    Para cada ε ∈ {ε_1, ..., ε_K}:
        min  f1(x)
        s.a. f2(x) ≤ ε
             restrições originais do sistema

Varredura:
    ε varia de ε_max (sem restrição de EENS — mínimo CAPEX) a ε_min = 0
    (zero shed — máxima confiabilidade, CAPEX máximo).

Resultado:
    Conjunto de K pontos (f1*, f2*) na fronteira de Pareto.
    Cada ponto corresponde a um dimensionamento (P_pv, E_bess, P_trafo) distinto.

Fronteiras adicionais
---------------------
Além de CAPEX × EENS, o módulo calcula:
    - CAPEX × Autossuficiência
    - EENS × Custo de demanda ANEEL (se aplicável)

Referências
-----------
- Haimes et al. (1971) "On a Bicriterion Formulation of the Problems of Integrated
  System Identification and System Optimization." IEEE Trans. SMC.
- Mavrotas (2009) "Effective implementation of the ε-constraint method in
  Multi-Objective Mathematical Programming problems." Applied Mathematics.
- Laumanns et al. (2006) "An efficient, adaptive parameter variation scheme for
  metaheuristics based on the epsilon-constraint method." EJOR.

Uso
---
    from advanced_features.feature_07_pareto_epsilon import (
        EpsilonConstraintSolver, run_pareto_analysis
    )

    result = run_pareto_analysis(
        dat_file="dados_exemplo.dat",
        n_epsilon_points=15,
        solver_name="cbc",
    )
    result.print_summary()
    result.plot()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    SolverFactory,
    Var,
    minimize,
    maximize,
    value,
)
from pyomo.opt import SolverStatus, TerminationCondition


# ---------------------------------------------------------------------------
# Estrutura de resultado de um ponto Pareto
# ---------------------------------------------------------------------------

@dataclass
class ParetoPoint:
    """Um ponto na fronteira de Pareto CAPEX × EENS."""

    epsilon: float                    # restrição ε usada [kWh/dia]
    status: str                       # "optimal", "infeasible", "timeout"
    f1_capex_anual_brl: float         # CAPEX anualizado + O&M [BRL/ano]
    f2_eens_kwh_dia: float            # EENS realizada [kWh/dia]
    f2_eens_kwh_ano: float            # EENS anualizada [kWh/ano]
    P_pv_cap: float                   # capacidade PV ótima [kW]
    E_bess_cap: float                 # capacidade BESS ótima [kWh]
    P_trafo_cap: float                # capacidade trafo ótima [kW]
    self_sufficiency: float           # autossuficiência [-]
    annual_profit_brl: float          # lucro operacional anual [BRL/ano]


@dataclass
class ParetoResult:
    """Resultado completo da análise de fronteira de Pareto."""

    points: List[ParetoPoint]
    n_optimal: int
    n_infeasible: int
    epsilon_values: List[float]
    eens_max_kwh_dia: float           # EENS sem restrição (mínimo CAPEX)
    eens_min_kwh_dia: float           # EENS com restrição rígida (zero shed)

    def optimal_points(self) -> List[ParetoPoint]:
        return [p for p in self.points if p.status == "optimal"]

    def print_summary(self) -> None:
        print("\n" + "=" * 80)
        print("FRONTEIRA DE PARETO — CAPEX Anualizado × EENS")
        print("=" * 80)
        print(f"\n{'ε [kWh/dia]':>12} | {'CAPEX [kBRL/ano]':>17} | {'EENS [kWh/ano]':>16} | "
              f"{'PV [kW]':>8} | {'BESS [kWh]':>10} | {'AutoSuf%':>9} | {'Status'}")
        print("-" * 90)
        for p in self.points:
            capex_k = p.f1_capex_anual_brl / 1000
            eens_a = p.f2_eens_kwh_ano
            print(
                f"{p.epsilon:>12.3f} | {capex_k:>17.1f} | {eens_a:>16.1f} | "
                f"{p.P_pv_cap:>8.1f} | {p.E_bess_cap:>10.1f} | "
                f"{p.self_sufficiency*100:>9.1f} | {p.status}"
            )
        print(f"\n✓ Ótimos: {self.n_optimal} | ✗ Inviáveis: {self.n_infeasible}")

    def plot(self, save_path: Optional[str] = None) -> None:
        """Plota a fronteira de Pareto."""
        from advanced_features.feature_05_reliability_metrics import plot_pareto_capex_eens
        from advanced_features.feature_05_reliability_metrics import ParetoPoint as PP5
        pp5_list = [
            PP5(
                epsilon=p.epsilon,
                capex_anual_brl=p.f1_capex_anual_brl,
                eens_kwh_ano=p.f2_eens_kwh_ano,
                P_pv_cap=p.P_pv_cap,
                E_bess_cap=p.E_bess_cap,
                P_trafo_cap=p.P_trafo_cap,
                self_sufficiency=p.self_sufficiency,
                status=p.status,
            )
            for p in self.optimal_points()
        ]
        plot_pareto_capex_eens(pp5_list, save_path=save_path)


# ---------------------------------------------------------------------------
# Modelo base para ε-constraint
# ---------------------------------------------------------------------------

def _build_epsilon_model(
    epsilon_kwh_dia: float,
    *,
    capex_pv_kw: float = 1200.0,
    capex_bess_kwh: float = 700.0,
    capex_trafo_kw: float = 1000.0,
    crf_pv: float = 0.10,
    crf_bess: float = 0.12,
    crf_trafo: float = 0.08,
    om_pv_kw_year: float = 30.0,
    om_bess_kwh_year: float = 25.0,
    om_trafo_kw_year: float = 20.0,
    tariff_ev: float = 1.60,
    operational_days: float = 365.0,
    eta_charge: float = 0.91,
    eta_discharge: float = 0.91,
    soc_min_frac: float = 0.05,
    soc_max_frac: float = 0.95,
    soc_initial_frac: float = 0.50,
    c_rate_charge: float = 1.0,
    c_rate_discharge: float = 1.0,
    E_bess_cap_max: float = 2000.0,
    P_pv_cap_max: float = 1000.0,
    P_trafo_cap_max: float = 500.0,
    irradiance_cf: Optional[Dict[int, float]] = None,
    grid_price: Optional[Dict[int, float]] = None,
    P_EV_load: Optional[Dict[int, float]] = None,
) -> AbstractModel:
    """
    Constrói o modelo ε-constraint: minimiza CAPEX s.a. EENS ≤ ε.

    Função objetivo: minimizar custo anualizado de investimento.
    Restrição ε: Σ_t LoadShedding[t] * delta_t ≤ epsilon_kwh_dia

    Args:
        epsilon_kwh_dia: limite máximo de EENS [kWh/dia].
        Demais: parâmetros técnico-econômicos do sistema.
    """
    m = AbstractModel()
    m.T = RangeSet(1, 24)

    # Parâmetros escalares
    m.capex_pv_kw = Param(initialize=capex_pv_kw, within=NonNegativeReals)
    m.capex_bess_kwh = Param(initialize=capex_bess_kwh, within=NonNegativeReals)
    m.capex_trafo_kw = Param(initialize=capex_trafo_kw, within=NonNegativeReals)
    m.crf_pv = Param(initialize=crf_pv, within=NonNegativeReals)
    m.crf_bess = Param(initialize=crf_bess, within=NonNegativeReals)
    m.crf_trafo = Param(initialize=crf_trafo, within=NonNegativeReals)
    m.om_pv_kw_year = Param(initialize=om_pv_kw_year, within=NonNegativeReals)
    m.om_bess_kwh_year = Param(initialize=om_bess_kwh_year, within=NonNegativeReals)
    m.om_trafo_kw_year = Param(initialize=om_trafo_kw_year, within=NonNegativeReals)
    m.tariff_ev = Param(initialize=tariff_ev, within=NonNegativeReals)
    m.operational_days = Param(initialize=operational_days, within=NonNegativeReals)
    m.epsilon = Param(initialize=epsilon_kwh_dia, within=NonNegativeReals)
    m.eta_charge = Param(initialize=eta_charge, within=NonNegativeReals)
    m.eta_discharge = Param(initialize=eta_discharge, within=NonNegativeReals)
    m.soc_min_frac = Param(initialize=soc_min_frac, within=NonNegativeReals)
    m.soc_max_frac = Param(initialize=soc_max_frac, within=NonNegativeReals)
    m.soc_initial_frac = Param(initialize=soc_initial_frac, within=NonNegativeReals)
    m.c_rate_charge = Param(initialize=c_rate_charge, within=NonNegativeReals)
    m.c_rate_discharge = Param(initialize=c_rate_discharge, within=NonNegativeReals)
    m.E_bess_cap_max = Param(initialize=E_bess_cap_max, within=NonNegativeReals)
    m.P_pv_cap_max = Param(initialize=P_pv_cap_max, within=NonNegativeReals)
    m.P_trafo_cap_max = Param(initialize=P_trafo_cap_max, within=NonNegativeReals)

    # Séries temporais
    if irradiance_cf:
        m.irradiance_cf = Param(m.T, initialize=irradiance_cf, within=NonNegativeReals)
    else:
        m.irradiance_cf = Param(m.T, within=NonNegativeReals)

    if grid_price:
        m.grid_price = Param(m.T, initialize=grid_price, within=NonNegativeReals)
    else:
        m.grid_price = Param(m.T, within=NonNegativeReals)

    if P_EV_load:
        m.P_EV_load = Param(m.T, initialize=P_EV_load, within=NonNegativeReals)
    else:
        m.P_EV_load = Param(m.T, within=NonNegativeReals)

    # Variáveis de investimento
    m.P_pv_cap = Var(within=NonNegativeReals, bounds=(0, P_pv_cap_max))
    m.E_bess_cap = Var(within=NonNegativeReals, bounds=(0, E_bess_cap_max))
    m.P_trafo_cap = Var(within=NonNegativeReals, bounds=(0, P_trafo_cap_max))

    # Variáveis operacionais
    m.P_pv_gen = Var(m.T, within=NonNegativeReals)
    m.P_grid_import = Var(m.T, within=NonNegativeReals)
    m.P_grid_export = Var(m.T, within=NonNegativeReals)
    m.P_bess_charge = Var(m.T, within=NonNegativeReals)
    m.P_bess_discharge = Var(m.T, within=NonNegativeReals)
    m.SOC = Var(m.T, within=NonNegativeReals)
    m.LoadShedding = Var(m.T, within=NonNegativeReals)
    m.y_bess = Var(m.T, within=Binary)

    # Restrições do sistema
    def pv_limit(model, t):
        return model.P_pv_gen[t] <= model.P_pv_cap * model.irradiance_cf[t]
    m.PVLimit = Constraint(m.T, rule=pv_limit)

    def import_limit(model, t):
        return model.P_grid_import[t] <= model.P_trafo_cap
    m.ImportLimit = Constraint(m.T, rule=import_limit)

    def charge_power(model, t):
        return model.P_bess_charge[t] <= model.c_rate_charge * model.E_bess_cap
    m.ChargePower = Constraint(m.T, rule=charge_power)

    def discharge_power(model, t):
        return model.P_bess_discharge[t] <= model.c_rate_discharge * model.E_bess_cap
    m.DischargePower = Constraint(m.T, rule=discharge_power)

    def charge_mode(model, t):
        return model.P_bess_charge[t] <= model.c_rate_charge * model.E_bess_cap_max * model.y_bess[t]
    m.ChargeMode = Constraint(m.T, rule=charge_mode)

    def discharge_mode(model, t):
        return model.P_bess_discharge[t] <= model.c_rate_discharge * model.E_bess_cap_max * (1 - model.y_bess[t])
    m.DischargeMode = Constraint(m.T, rule=discharge_mode)

    def soc_min_b(model, t):
        return model.SOC[t] >= model.soc_min_frac * model.E_bess_cap
    m.SOCMinBound = Constraint(m.T, rule=soc_min_b)

    def soc_max_b(model, t):
        return model.SOC[t] <= model.soc_max_frac * model.E_bess_cap
    m.SOCMaxBound = Constraint(m.T, rule=soc_max_b)

    def soc_balance(model, t):
        cn = model.eta_charge * model.P_bess_charge[t] - model.P_bess_discharge[t] / model.eta_discharge
        if t == model.T.first():
            return model.SOC[t] == model.soc_initial_frac * model.E_bess_cap + cn
        return model.SOC[t] == model.SOC[model.T.prev(t)] + cn
    m.SOCBalance = Constraint(m.T, rule=soc_balance)

    def terminal_soc(model):
        return model.SOC[model.T.last()] == model.soc_initial_frac * model.E_bess_cap
    m.TerminalSOC = Constraint(rule=terminal_soc)

    def energy_balance(model, t):
        return (
            model.P_pv_gen[t] + model.P_grid_import[t] + model.P_bess_discharge[t]
            == model.P_EV_load[t] - model.LoadShedding[t] + model.P_bess_charge[t] + model.P_grid_export[t]
        )
    m.EnergyBalance = Constraint(m.T, rule=energy_balance)

    # Restrição ε-constraint: EENS ≤ ε
    def epsilon_constraint(model):
        return sum(model.LoadShedding[t] for t in model.T) <= model.epsilon
    m.EpsilonConstraint = Constraint(rule=epsilon_constraint)

    # Função objetivo: minimizar custo anualizado de investimento
    def objective_rule(model):
        daily_rev = sum(
            model.tariff_ev * model.P_EV_load[t]
            - model.grid_price[t] * model.P_grid_import[t]
            for t in model.T
        )
        annual_op = model.operational_days * daily_rev
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )
        # Maximizar lucro líquido = minimizar custo líquido
        return annual_investment - annual_op

    m.Obj = Objective(rule=objective_rule, sense=minimize)
    return m


# ---------------------------------------------------------------------------
# Solver ε-constraint iterativo
# ---------------------------------------------------------------------------

class EpsilonConstraintSolver:
    """
    Resolve o problema ε-constraint para uma grade de valores ε, gerando
    a fronteira de Pareto entre CAPEX anualizado e EENS.

    Algoritmo:
    1. Resolver o problema sem restrição ε → obter EENS_max (ponto mínimo custo).
    2. Resolver com ε = 0 → obter EENS_min (ponto zero shed, se viável).
    3. Varrer ε de EENS_max a EENS_min em n_points passos uniformes.
    4. Para cada ε, resolver o MILP e registrar o ponto Pareto.
    """

    def __init__(
        self,
        solver_name: str = "cbc",
        n_epsilon_points: int = 10,
        time_limit: Optional[int] = 300,
        verbose: bool = False,
        **model_params,
    ) -> None:
        self.solver_name = solver_name
        self.n_epsilon_points = n_epsilon_points
        self.time_limit = time_limit
        self.verbose = verbose
        self.model_params = model_params

    def _solve_instance(self, epsilon: float) -> ParetoPoint:
        """Resolve para um único ε e retorna o ponto Pareto."""
        model = _build_epsilon_model(epsilon, **self.model_params)
        instance = model.create_instance()

        solver = SolverFactory(self.solver_name)
        if self.time_limit and hasattr(solver.options, "__setitem__"):
            if self.solver_name in ("gurobi", "cplex"):
                solver.options["TimeLimit"] = self.time_limit
            elif self.solver_name == "cbc":
                solver.options["sec"] = self.time_limit

        results = solver.solve(instance, tee=False)
        status = results.solver.status
        term = results.solver.termination_condition

        is_optimal = (
            status == SolverStatus.ok and
            term in (TerminationCondition.optimal, TerminationCondition.locallyOptimal)
        )

        if is_optimal:
            pv = value(instance.P_pv_cap)
            bess = value(instance.E_bess_cap)
            trafo = value(instance.P_trafo_cap)
            eens_dia = sum(value(instance.LoadShedding[t]) for t in instance.T)
            eens_ano = eens_dia * value(instance.operational_days)

            annual_investment = (
                (value(instance.crf_pv) * value(instance.capex_pv_kw) + value(instance.om_pv_kw_year)) * pv
                + (value(instance.crf_bess) * value(instance.capex_bess_kwh) + value(instance.om_bess_kwh_year)) * bess
                + (value(instance.crf_trafo) * value(instance.capex_trafo_kw) + value(instance.om_trafo_kw_year)) * trafo
            )

            daily_rev = sum(
                value(instance.tariff_ev) * value(instance.P_EV_load[t])
                - value(instance.grid_price[t]) * value(instance.P_grid_import[t])
                for t in instance.T
            )
            annual_op = value(instance.operational_days) * daily_rev

            # Autossuficiência
            served = sum(
                (value(instance.P_EV_load[t]) - value(instance.LoadShedding[t]))
                for t in instance.T
            )
            local = sum(
                value(instance.P_pv_gen[t]) + value(instance.P_bess_discharge[t]) - value(instance.P_bess_charge[t])
                for t in instance.T
            )
            self_suf = min(1.0, max(0.0, local / max(served, 1e-9)))

            return ParetoPoint(
                epsilon=epsilon,
                status="optimal",
                f1_capex_anual_brl=annual_investment,
                f2_eens_kwh_dia=eens_dia,
                f2_eens_kwh_ano=eens_ano,
                P_pv_cap=pv,
                E_bess_cap=bess,
                P_trafo_cap=trafo,
                self_sufficiency=self_suf,
                annual_profit_brl=annual_op - annual_investment,
            )
        else:
            return ParetoPoint(
                epsilon=epsilon,
                status="infeasible" if term == TerminationCondition.infeasible else "timeout",
                f1_capex_anual_brl=float("nan"),
                f2_eens_kwh_dia=float("nan"),
                f2_eens_kwh_ano=float("nan"),
                P_pv_cap=float("nan"),
                E_bess_cap=float("nan"),
                P_trafo_cap=float("nan"),
                self_sufficiency=float("nan"),
                annual_profit_brl=float("nan"),
            )

    def solve(self) -> ParetoResult:
        """
        Executa a varredura ε-constraint completa.

        Returns:
            ParetoResult com a fronteira de Pareto completa.
        """
        # Passo 1: resolver sem restrição ε (ε = demanda total máxima)
        total_ev = sum(self.model_params.get("P_EV_load", {t: 100 for t in range(1, 25)}).values())
        epsilon_max = total_ev  # limite superior: todo a demanda pode ser shed

        if self.verbose:
            print(f"[Pareto] Calculando ponto sem restrição ε (ε_max = {epsilon_max:.1f} kWh/dia)...")
        p_max = self._solve_instance(epsilon_max)

        # EENS sem restrição
        eens_max = p_max.f2_eens_kwh_dia if p_max.status == "optimal" else epsilon_max

        # Passo 2: resolver com ε = 0 (zero shed)
        if self.verbose:
            print(f"[Pareto] Calculando ponto com ε = 0 (zero shed)...")
        p_min = self._solve_instance(0.0)
        eens_min = p_min.f2_eens_kwh_dia if p_min.status == "optimal" else 0.0

        # Passo 3: grade de ε
        if eens_max <= 0.0:
            epsilon_values = [0.0]
        else:
            step = eens_max / max(self.n_epsilon_points - 1, 1)
            epsilon_values = [eens_max - i * step for i in range(self.n_epsilon_points)]
            epsilon_values = [max(0.0, e) for e in epsilon_values]

        # Passo 4: resolver para cada ε
        points: List[ParetoPoint] = []
        for i, eps in enumerate(epsilon_values):
            if self.verbose:
                print(f"[Pareto] Resolvendo ponto {i+1}/{len(epsilon_values)}: ε = {eps:.3f}...")
            pt = self._solve_instance(eps)
            points.append(pt)

        n_opt = sum(1 for p in points if p.status == "optimal")
        n_inf = sum(1 for p in points if p.status != "optimal")

        return ParetoResult(
            points=points,
            n_optimal=n_opt,
            n_infeasible=n_inf,
            epsilon_values=epsilon_values,
            eens_max_kwh_dia=eens_max,
            eens_min_kwh_dia=eens_min,
        )


# ---------------------------------------------------------------------------
# Função de conveniência
# ---------------------------------------------------------------------------

def run_pareto_analysis(
    dat_file: Optional[str] = None,
    n_epsilon_points: int = 10,
    solver_name: str = "cbc",
    verbose: bool = True,
    save_plot: Optional[str] = None,
    irradiance_cf: Optional[Dict[int, float]] = None,
    grid_price: Optional[Dict[int, float]] = None,
    P_EV_load: Optional[Dict[int, float]] = None,
    **model_params,
) -> ParetoResult:
    """
    Executa análise completa de Pareto ε-constraint e opcionalmente plota.

    Args:
        dat_file: caminho para arquivo .dat (se fornecido, carrega irr/price/load de lá).
        n_epsilon_points: número de pontos na fronteira Pareto.
        solver_name: nome do solver ("cbc", "gurobi", "glpk").
        verbose: imprime progresso.
        save_plot: caminho para salvar figura (None = não plota).
        irradiance_cf, grid_price, P_EV_load: séries temporais alternativas.
        **model_params: parâmetros adicionais do modelo.

    Returns:
        ParetoResult com a fronteira de Pareto.
    """
    # Perfis padrão (dados_exemplo.dat)
    if irradiance_cf is None:
        irradiance_cf = {
            1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.10, 6: 0.30,
            7: 0.50, 8: 0.70, 9: 0.90, 10: 1.00, 11: 0.95, 12: 0.90,
            13: 0.85, 14: 0.80, 15: 0.70, 16: 0.50, 17: 0.30, 18: 0.10,
            19: 0.00, 20: 0.00, 21: 0.00, 22: 0.00, 23: 0.00, 24: 0.00,
        }
    if grid_price is None:
        grid_price = {
            1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25, 6: 0.25,
            7: 0.54, 8: 0.88, 9: 0.88, 10: 0.88, 11: 0.88, 12: 0.54,
            13: 0.54, 14: 0.54, 15: 0.54, 16: 0.54, 17: 0.88, 18: 1.10,
            19: 1.10, 20: 1.10, 21: 0.88, 22: 0.54, 23: 0.25, 24: 0.25,
        }
    if P_EV_load is None:
        P_EV_load = {
            1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
            9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
            16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
            22: 72, 23: 54, 24: 42,
        }

    solver = EpsilonConstraintSolver(
        solver_name=solver_name,
        n_epsilon_points=n_epsilon_points,
        verbose=verbose,
        irradiance_cf=irradiance_cf,
        grid_price=grid_price,
        P_EV_load=P_EV_load,
        **model_params,
    )

    result = solver.solve()
    result.print_summary()

    if save_plot:
        result.plot(save_path=save_plot)

    return result


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 7 — Fronteira de Pareto (ε-constraint)")
    print("=" * 60)
    print("\nExecutando análise de Pareto com 5 pontos (demo rápida)...\n")

    result = run_pareto_analysis(
        n_epsilon_points=5,
        solver_name="cbc",
        verbose=True,
    )

    print(f"\nResumo:")
    print(f"  EENS sem restrição: {result.eens_max_kwh_dia:.2f} kWh/dia")
    print(f"  EENS com zero shed: {result.eens_min_kwh_dia:.2f} kWh/dia")
    print(f"  Pontos ótimos: {result.n_optimal}")
    print(f"  Pontos inviáveis: {result.n_infeasible}")
