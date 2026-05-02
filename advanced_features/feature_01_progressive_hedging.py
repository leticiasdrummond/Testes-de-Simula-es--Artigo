"""
Feature 1 — Programação Estocástica de Dois Estágios com Progressive Hedging
==============================================================================

Objetivo
--------
Formalizar a estrutura já esboçada no modelo base (decisões de investimento
compartilhadas entre cenários) com uma formulação de Stochastic Programming
completa, resolvida via Progressive Hedging (PH) — decomposição de Lagrange
progressiva sobre o conjunto de cenários.

Formulação matemática
---------------------
Primeiro estágio (não antecipatório):
    x = (P_pv_cap, E_bess_cap, P_trafo_cap)  — comuns a todos os cenários

Segundo estágio por cenário s ∈ S:
    y_s = despacho operacional: P_pv_gen[s,t], P_grid_import[s,t], ...

Restrição de não-antecipação (explícita):
    x_s == x̄  para todo s ∈ S

onde x̄ é a média ponderada das decisões de investimento nos subproblemas,
atualizada iterativamente no passo de "reconciliação" do PH.

Equação de atualização do multiplicador PH (w_s):
    w_s^{k+1} = w_s^k + ρ * (x_s^k - x̄^k)

Penalização quadrática no subproblema de cada cenário s:
    min  f_s(x_s, y_s)  +  w_s^T x_s  +  (ρ/2) ||x_s - x̄||²

onde ρ > 0 é o parâmetro de penalização (rho).

Grupos sazonais
---------------
Os cenários são agrupados em estações do ano:
    - VERAO  : cenários de alta irradiância e demanda VE elevada
    - INVERNO: cenários de baixa irradiância e demanda moderada
    - INTER  : cenários intermediários (outono/primavera)

Estrutura temporal em árvore (simplificada):
    raiz → {VERAO, INVERNO, INTER} → subconjuntos de cenários operacionais

Referências
-----------
- Rockafellar & Wets (1991) "Scenarios and Policy Aggregation in Optimization
  Under Uncertainty." Mathematics of Operations Research.
- Watson & Woodruff (2011) "Progressive hedging innovations for a class of
  stochastic mixed-integer resource allocation problems." Computational
  Management Science.

Uso
---
    from advanced_features.feature_01_progressive_hedging import (
        ProgressiveHedging, ScenarioTree, build_scenario_subproblem
    )

    tree = ScenarioTree.from_seasonal_groups(scenarios, season_map, probabilities)
    ph = ProgressiveHedging(tree, rho=10.0, max_iter=100, tol=1e-4)
    result = ph.solve(solver_name="cbc")
    print(result.consensus_investment)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    Set,
    SolverFactory,
    Var,
    maximize,
    value,
)


# ---------------------------------------------------------------------------
# Enumeração das estações sazonais
# ---------------------------------------------------------------------------

class Season(Enum):
    VERAO = "verao"
    INVERNO = "inverno"
    INTER = "inter"


# ---------------------------------------------------------------------------
# Estrutura de dados de cenário
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """Representa um único cenário de operação com sua estação e probabilidade."""

    name: str
    season: Season
    probability: float
    irradiance_cf: Dict[int, float]   # t -> fator de capacidade FV [0,1]
    grid_price: Dict[int, float]      # t -> BRL/kWh
    ev_load: Dict[int, float]         # t -> kW
    grid_availability: Dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isclose(1.0, 1.0):  # placeholder — validar externamente
            pass
        # Disponibilidade padrão: rede sempre disponível
        if not self.grid_availability:
            self.grid_availability = {t: 1.0 for t in self.irradiance_cf}


@dataclass
class ScenarioTree:
    """
    Árvore de cenários com grupos sazonais.

    A raiz representa a decisão de investimento (primeiro estágio, comum a todos).
    Cada folha é um cenário operacional (segundo estágio).
    """

    scenarios: List[Scenario]
    season_groups: Dict[Season, List[str]]  # season -> lista de nomes de cenários

    @classmethod
    def from_seasonal_groups(
        cls,
        scenarios: List[Scenario],
        validate: bool = True,
    ) -> "ScenarioTree":
        """Constrói a árvore agrupando automaticamente cenários por estação."""
        groups: Dict[Season, List[str]] = {s: [] for s in Season}
        total_prob = 0.0
        for sc in scenarios:
            groups[sc.season].append(sc.name)
            total_prob += sc.probability

        if validate and not math.isclose(total_prob, 1.0, rel_tol=1e-6):
            raise ValueError(
                f"Probabilidades somam {total_prob:.6f}; esperado 1.0. "
                "Normalize antes de criar ScenarioTree."
            )

        return cls(scenarios=scenarios, season_groups=groups)

    def scenario_by_name(self, name: str) -> Scenario:
        for sc in self.scenarios:
            if sc.name == name:
                return sc
        raise KeyError(f"Cenário '{name}' não encontrado na árvore.")

    @property
    def n_scenarios(self) -> int:
        return len(self.scenarios)

    def season_of(self, scenario_name: str) -> Season:
        return self.scenario_by_name(scenario_name).season


# ---------------------------------------------------------------------------
# Resultado de uma iteração do PH
# ---------------------------------------------------------------------------

@dataclass
class PHIterResult:
    iteration: int
    primal_residual: float          # ||x_s - x̄|| médio ponderado
    dual_residual: float            # ||x̄^k - x̄^{k-1}||
    consensus_pv: float
    consensus_bess: float
    consensus_trafo: float
    converged: bool


@dataclass
class PHResult:
    consensus_investment: Dict[str, float]   # {"P_pv_cap": ..., "E_bess_cap": ..., ...}
    iterations: List[PHIterResult]
    converged: bool
    total_expected_cost: float


# ---------------------------------------------------------------------------
# Construção do subproblema por cenário (modelo Pyomo)
# ---------------------------------------------------------------------------

def build_scenario_subproblem(
    scenario: Scenario,
    *,
    # parâmetros de capacidade
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
    # multiplicadores e penalização do PH (atualizados a cada iteração)
    w_pv: float = 0.0,
    w_bess: float = 0.0,
    w_trafo: float = 0.0,
    x_bar_pv: float = 0.0,
    x_bar_bess: float = 0.0,
    x_bar_trafo: float = 0.0,
    rho: float = 10.0,
) -> AbstractModel:
    """
    Constrói o subproblema Pyomo para um único cenário com penalização PH.

    O subproblema inclui:
    - Variáveis de investimento x_s = (P_pv_cap, E_bess_cap, P_trafo_cap)
    - Variáveis de despacho operacional por hora t
    - Função objetivo: lucro do cenário + penalização PH

    A penalização PH aumentada é:
        penalização = w_s^T x_s + (ρ/2) ||x_s - x̄||²

    Nota: o termo quadrático ||x_s - x̄||² é linearizado via expansão:
        ||x - x̄||² = x² - 2*x̄*x + x̄²
    O term x̄² é constante e ignorado na otimização (não afeta as variáveis de decisão).
    O term x² torna o subproblema um MIQP (Mixed Integer Quadratic Program), compatível
    com Gurobi/CPLEX. Para solvers LP-only (CBC, GLPK), ρ deve ser nulo (PH clássico
    sem penalização quadrática) ou o QP deve ser aproximado por cortes lineares.
    """
    m = AbstractModel()
    m.T = RangeSet(1, 24)

    # Dados do cenário passados como parâmetros escalares e vetoriais
    m.prob = Param(initialize=scenario.probability, within=NonNegativeReals)
    m.w_pv = Param(initialize=w_pv)
    m.w_bess = Param(initialize=w_bess)
    m.w_trafo = Param(initialize=w_trafo)
    m.x_bar_pv = Param(initialize=x_bar_pv, within=NonNegativeReals)
    m.x_bar_bess = Param(initialize=x_bar_bess, within=NonNegativeReals)
    m.x_bar_trafo = Param(initialize=x_bar_trafo, within=NonNegativeReals)
    m.rho = Param(initialize=rho, within=NonNegativeReals)

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

    m.irradiance_cf = Param(m.T, initialize=scenario.irradiance_cf, within=NonNegativeReals)
    m.grid_price = Param(m.T, initialize=scenario.grid_price, within=NonNegativeReals)
    m.ev_load = Param(m.T, initialize=scenario.ev_load, within=NonNegativeReals)
    m.grid_avail = Param(m.T, initialize=scenario.grid_availability, within=NonNegativeReals)

    # Variáveis de investimento (cópia por cenário — PH reconcilia ao longo das iterações)
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

    # Restrições físicas
    def pv_limit(model, t):
        return model.P_pv_gen[t] <= model.P_pv_cap * model.irradiance_cf[t]
    m.PVLimit = Constraint(m.T, rule=pv_limit)

    def import_limit(model, t):
        return model.P_grid_import[t] <= model.P_trafo_cap * model.grid_avail[t]
    m.ImportLimit = Constraint(m.T, rule=import_limit)

    def export_limit(model, t):
        return model.P_grid_export[t] <= model.P_trafo_cap * model.grid_avail[t]
    m.ExportLimit = Constraint(m.T, rule=export_limit)

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

    def soc_min(model, t):
        return model.SOC[t] >= model.soc_min_frac * model.E_bess_cap
    m.SOCMin = Constraint(m.T, rule=soc_min)

    def soc_max(model, t):
        return model.SOC[t] <= model.soc_max_frac * model.E_bess_cap
    m.SOCMax = Constraint(m.T, rule=soc_max)

    def soc_balance(model, t):
        charge_net = model.eta_charge * model.P_bess_charge[t] - model.P_bess_discharge[t] / model.eta_discharge
        if t == model.T.first():
            return model.SOC[t] == model.soc_initial_frac * model.E_bess_cap + charge_net
        return model.SOC[t] == model.SOC[model.T.prev(t)] + charge_net
    m.SOCBalance = Constraint(m.T, rule=soc_balance)

    def terminal_soc(model):
        return model.SOC[model.T.last()] == model.soc_initial_frac * model.E_bess_cap
    m.TerminalSOC = Constraint(rule=terminal_soc)

    def energy_balance(model, t):
        return (
            model.P_pv_gen[t] + model.P_grid_import[t] + model.P_bess_discharge[t]
            == model.ev_load[t] - model.LoadShedding[t] + model.P_bess_charge[t] + model.P_grid_export[t]
        )
    m.EnergyBalance = Constraint(m.T, rule=energy_balance)

    # Função objetivo com penalização PH
    # Lucro anual = operacional - CAPEX anualizado - O&M
    # Penalização PH = w^T x + (ρ/2)(x - x̄)^T(x - x̄)  [expandida: ignora constante x̄²]
    def ph_objective(model):
        daily_rev = sum(
            model.tariff_ev * model.ev_load[t]
            - model.grid_price[t] * model.P_grid_import[t]
            for t in model.T
        )
        annual_profit = model.operational_days * daily_rev
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )
        # Penalização linear (w^T x) — quadrática requer MIQP solver (Gurobi/CPLEX)
        ph_linear_penalty = (
            model.w_pv * model.P_pv_cap
            + model.w_bess * model.E_bess_cap
            + model.w_trafo * model.P_trafo_cap
        )
        # Aproximação quadrática linearizada: (ρ/2)(x² - 2*x̄*x) ≈ -ρ*x̄*x (omitindo x²)
        # Para MIQP completo, trocar por: + (rho/2)*(x-x_bar)**2
        ph_proximal_linear = model.rho * (
            -model.x_bar_pv * model.P_pv_cap
            - model.x_bar_bess * model.E_bess_cap
            - model.x_bar_trafo * model.P_trafo_cap
        )
        return annual_profit - annual_investment - ph_linear_penalty + ph_proximal_linear

    m.PHObjective = Objective(rule=ph_objective, sense=maximize)
    return m


# ---------------------------------------------------------------------------
# Algoritmo de Progressive Hedging
# ---------------------------------------------------------------------------

class ProgressiveHedging:
    """
    Implementa o algoritmo de Progressive Hedging para problemas estocásticos
    de dois estágios com variáveis de investimento compartilhadas.

    Algoritmo (por iteração k):
    1. Resolver cada subproblema s com x̄^k e w_s^k fixos → obter x_s^{k+1}
    2. Calcular consenso: x̄^{k+1} = Σ_s prob_s * x_s^{k+1}
    3. Atualizar multiplicadores: w_s^{k+1} = w_s^k + ρ * (x_s^{k+1} - x̄^{k+1})
    4. Checar convergência: ||x_s - x̄|| < tol para todo s

    Convergência: garantida para problemas convexos; para MILP, aproximação heurística.
    """

    def __init__(
        self,
        tree: ScenarioTree,
        rho: float = 10.0,
        max_iter: int = 100,
        tol: float = 1e-4,
        verbose: bool = False,
        **scenario_params,
    ) -> None:
        self.tree = tree
        self.rho = rho
        self.max_iter = max_iter
        self.tol = tol
        self.verbose = verbose
        self.scenario_params = scenario_params

        # Inicializar multiplicadores e consenso
        self._w: Dict[str, Dict[str, float]] = {
            sc.name: {"pv": 0.0, "bess": 0.0, "trafo": 0.0}
            for sc in tree.scenarios
        }
        self._x_bar = {"pv": 0.0, "bess": 0.0, "trafo": 0.0}
        self._x_s: Dict[str, Dict[str, float]] = {
            sc.name: {"pv": 0.0, "bess": 0.0, "trafo": 0.0}
            for sc in tree.scenarios
        }

    def _solve_subproblem(self, sc: Scenario, solver_name: str) -> Dict[str, float]:
        """Resolve o subproblema de um cenário e retorna as variáveis de investimento."""
        w = self._w[sc.name]
        model = build_scenario_subproblem(
            sc,
            w_pv=w["pv"],
            w_bess=w["bess"],
            w_trafo=w["trafo"],
            x_bar_pv=self._x_bar["pv"],
            x_bar_bess=self._x_bar["bess"],
            x_bar_trafo=self._x_bar["trafo"],
            rho=self.rho,
            **self.scenario_params,
        )
        instance = model.create_instance()
        solver = SolverFactory(solver_name)
        results = solver.solve(instance, tee=False)

        pv_val = value(instance.P_pv_cap)
        bess_val = value(instance.E_bess_cap)
        trafo_val = value(instance.P_trafo_cap)
        return {"pv": pv_val, "bess": bess_val, "trafo": trafo_val}

    def _update_consensus(self) -> None:
        """Atualiza x̄ como média ponderada pelas probabilidades dos cenários."""
        x_bar_new = {"pv": 0.0, "bess": 0.0, "trafo": 0.0}
        for sc in self.tree.scenarios:
            for key in ("pv", "bess", "trafo"):
                x_bar_new[key] += sc.probability * self._x_s[sc.name][key]
        self._x_bar = x_bar_new

    def _update_multipliers(self) -> None:
        """Atualiza os multiplicadores de Lagrange w_s."""
        for sc in self.tree.scenarios:
            for key in ("pv", "bess", "trafo"):
                self._w[sc.name][key] += self.rho * (
                    self._x_s[sc.name][key] - self._x_bar[key]
                )

    def _primal_residual(self) -> float:
        """Residual primal ponderado: Σ_s prob_s * ||x_s - x̄||."""
        res = 0.0
        for sc in self.tree.scenarios:
            for key in ("pv", "bess", "trafo"):
                res += sc.probability * abs(self._x_s[sc.name][key] - self._x_bar[key])
        return res

    def solve(self, solver_name: str = "cbc") -> PHResult:
        """
        Executa o algoritmo de Progressive Hedging até convergência ou max_iter.

        Args:
            solver_name: nome do solver Pyomo (ex.: "cbc", "gurobi", "glpk").

        Returns:
            PHResult com decisão de consenso, histórico de iterações e flag de convergência.
        """
        iteration_history: List[PHIterResult] = []
        x_bar_prev = dict(self._x_bar)

        for k in range(1, self.max_iter + 1):
            # Passo 1: resolver subproblemas
            for sc in self.tree.scenarios:
                self._x_s[sc.name] = self._solve_subproblem(sc, solver_name)

            # Passo 2: atualizar consenso
            self._update_consensus()

            # Passo 3: calcular resíduos
            primal_res = self._primal_residual()
            dual_res = sum(
                abs(self._x_bar[key] - x_bar_prev[key]) for key in ("pv", "bess", "trafo")
            )
            x_bar_prev = dict(self._x_bar)

            converged = primal_res < self.tol

            iter_result = PHIterResult(
                iteration=k,
                primal_residual=primal_res,
                dual_residual=dual_res,
                consensus_pv=self._x_bar["pv"],
                consensus_bess=self._x_bar["bess"],
                consensus_trafo=self._x_bar["trafo"],
                converged=converged,
            )
            iteration_history.append(iter_result)

            if self.verbose:
                print(
                    f"[PH] iter={k:3d} | primal={primal_res:.6f} | dual={dual_res:.6f}"
                    f" | PV={self._x_bar['pv']:.1f} kW | BESS={self._x_bar['bess']:.1f} kWh"
                    f" | Trafo={self._x_bar['trafo']:.1f} kW"
                )

            # Passo 4: atualizar multiplicadores
            self._update_multipliers()

            if converged:
                break

        return PHResult(
            consensus_investment={
                "P_pv_cap": self._x_bar["pv"],
                "E_bess_cap": self._x_bar["bess"],
                "P_trafo_cap": self._x_bar["trafo"],
            },
            iterations=iteration_history,
            converged=iteration_history[-1].converged if iteration_history else False,
            total_expected_cost=sum(
                sc.probability * self._x_s[sc.name]["pv"] for sc in self.tree.scenarios
            ),  # placeholder — substituir por valor objetivo real
        )


# ---------------------------------------------------------------------------
# Utilitários: criação de cenários sazonais representativos
# ---------------------------------------------------------------------------

def make_seasonal_scenarios(
    base_irr_summer: Dict[int, float],
    base_irr_winter: Dict[int, float],
    base_irr_inter: Dict[int, float],
    base_ev_load: Dict[int, float],
    base_grid_price: Dict[int, float],
    n_scenarios_per_season: int = 3,
    ev_load_variability: float = 0.15,
    seed: int = 42,
) -> List[Scenario]:
    """
    Gera cenários representativos para as três estações usando perturbação
    estocástica sobre os perfis base de irradiância e carga VE.

    Args:
        base_irr_*: dicionários t -> irradiância normalizada por estação.
        base_ev_load: perfil base de demanda VE (t -> kW).
        base_grid_price: perfil base de preço da rede (t -> BRL/kWh).
        n_scenarios_per_season: número de cenários por estação.
        ev_load_variability: desvio relativo máximo da carga VE (±).
        seed: semente aleatória para reprodutibilidade.

    Returns:
        Lista de Scenario com probabilidades normalizadas.
    """
    import random
    rng = random.Random(seed)

    season_irr = {
        Season.VERAO: base_irr_summer,
        Season.INVERNO: base_irr_winter,
        Season.INTER: base_irr_inter,
    }
    # Pesos sazonais: verão pesa mais em rodovias brasileiras
    season_weights = {Season.VERAO: 0.40, Season.INVERNO: 0.30, Season.INTER: 0.30}

    scenarios: List[Scenario] = []
    for season, base_irr in season_irr.items():
        weight = season_weights[season]
        prob_per_sc = weight / n_scenarios_per_season

        for i in range(n_scenarios_per_season):
            # Perturbação multiplicativa na carga VE
            ev_load_sc = {
                t: max(0.0, v * (1.0 + rng.uniform(-ev_load_variability, ev_load_variability)))
                for t, v in base_ev_load.items()
            }
            # Perturbação aditiva pequena na irradiância (mantém [0,1])
            irr_sc = {
                t: min(1.0, max(0.0, v + rng.uniform(-0.05, 0.05)))
                for t, v in base_irr.items()
            }

            scenarios.append(Scenario(
                name=f"{season.value}_sc{i+1}",
                season=season,
                probability=prob_per_sc,
                irradiance_cf=irr_sc,
                grid_price=dict(base_grid_price),
                ev_load=ev_load_sc,
            ))

    return scenarios


# ---------------------------------------------------------------------------
# Demonstração (execução direta)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Perfis de irradiância por estação (24h normalizados)
    irr_summer = {
        1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.15, 6: 0.35,
        7: 0.60, 8: 0.80, 9: 0.95, 10: 1.00, 11: 1.00, 12: 0.95,
        13: 0.90, 14: 0.85, 15: 0.75, 16: 0.60, 17: 0.40, 18: 0.15,
        19: 0.00, 20: 0.00, 21: 0.00, 22: 0.00, 23: 0.00, 24: 0.00,
    }
    irr_winter = {
        1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.05, 6: 0.20,
        7: 0.40, 8: 0.60, 9: 0.75, 10: 0.85, 11: 0.90, 12: 0.85,
        13: 0.80, 14: 0.70, 15: 0.55, 16: 0.35, 17: 0.15, 18: 0.05,
        19: 0.00, 20: 0.00, 21: 0.00, 22: 0.00, 23: 0.00, 24: 0.00,
    }
    irr_inter = {t: 0.85 * irr_summer[t] for t in range(1, 25)}

    base_ev = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
        9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
        16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
        22: 72, 23: 54, 24: 42,
    }
    base_price = {
        1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25, 6: 0.25,
        7: 0.54, 8: 0.88, 9: 0.88, 10: 0.88, 11: 0.88, 12: 0.54,
        13: 0.54, 14: 0.54, 15: 0.54, 16: 0.54, 17: 0.88, 18: 1.10,
        19: 1.10, 20: 1.10, 21: 0.88, 22: 0.54, 23: 0.25, 24: 0.25,
    }

    print("=" * 60)
    print("Feature 1 — Progressive Hedging")
    print("=" * 60)

    scenarios = make_seasonal_scenarios(
        irr_summer, irr_winter, irr_inter, base_ev, base_price,
        n_scenarios_per_season=2, seed=42
    )
    tree = ScenarioTree.from_seasonal_groups(scenarios)

    print(f"Árvore de cenários: {tree.n_scenarios} cenários")
    for sc in tree.scenarios:
        print(f"  {sc.name}: prob={sc.probability:.4f} | estação={sc.season.value}")

    ph = ProgressiveHedging(tree, rho=5.0, max_iter=10, tol=1e-3, verbose=True)
    result = ph.solve(solver_name="cbc")

    print("\nResultado do Progressive Hedging:")
    print(f"  Convergiu: {result.converged}")
    print(f"  Iterações: {len(result.iterations)}")
    print(f"  Consenso de investimento:")
    for k, v in result.consensus_investment.items():
        print(f"    {k}: {v:.2f}")
