"""
Feature 8 — Otimização Robusta Γ (Bertsimas & Sim)
====================================================

Objetivo
--------
Complementar a esperança matemática estocástica com uma formulação robusta
para cenários adversos, controlada pelo parâmetro Γ (gamma) que governa o
grau de conservadorismo da solução.

Formulação de robustez Γ (Bertsimas & Sim, 2004)
-------------------------------------------------

Incerteza nos parâmetros:
    Cada parâmetro incerto p̃_i varia em torno do seu valor nominal p̂_i
    dentro de um intervalo de perturbação [-p̄_i, +p̄_i]:
        p̃_i ∈ [p̂_i - p̄_i, p̂_i + p̄_i]

Parâmetro Γ ∈ [0, |I|]:
    - Γ = 0: sem perturbação (solução determinística)
    - Γ = |I|: todas as perturbações simultâneas (robusto máximo = minimax)
    - Γ ∈ (0, |I|): conservadorismo controlável

Reformulação dual robusta (linear):
    Para uma restrição de desigualdade do tipo:
        Σ_i a_i(p̃_i) x_i ≤ b
    com p̃_i ∈ [â_i, â_i + ā_i], a versão robusta Γ é:
        Σ_i â_i x_i + max_{S∪{t}: |S|≤Γ} { Σ_{i∈S} ā_i x_i + (Γ-⌊Γ⌋) ā_t x_t } ≤ b

    Via dualidade LP (Bertsimas & Sim), isso equivale a:
        Σ_i â_i x_i + Γ*z + Σ_i p_i ≤ b
        p_i + z ≥ ā_i * x_i    (para todo i)
        p_i ≥ 0, z ≥ 0

Parâmetros incertos neste modelo
---------------------------------
Os dois parâmetros mais críticos para o dimensionamento do eletroposto são:

1. irradiance_cf[t]: fator de capacidade FV (incerteza de recurso solar)
   - Perturbação: ±Δ_irr[t] = irr_uncertainty * irradiance_cf_nominal[t]
   - Origem: variabilidade de nuvens, sazonalidade, degradação do painel

2. P_EV_load[t]: demanda de recarga VE (incerteza de chegada de veículos)
   - Perturbação: ±Δ_ev[t] = ev_uncertainty * P_EV_load_nominal[t]
   - Origem: padrão estocástico de chegadas (dados Dutra: σ ≈ 15-25%)

Reformulação robusta aplicada
------------------------------
Restrição de balanço de energia robusta (lado da geração FV):
    P_pv_gen[t] ≤ P_pv_cap * (irradiance_cf[t] - Δ_irr[t] * z_irr - p_irr[t] / P_pv_cap)
    p_irr[t] + z_irr ≥ Δ_irr[t] * P_pv_cap   (para t perturbável)

Restrição de balanço robusta (lado da carga VE):
    A carga efetiva no pior caso:
    P_EV_load_robust[t] = P_EV_load[t] + Δ_ev[t] (adiciona robustez ao lado da demanda)

Referências
-----------
- Bertsimas & Sim (2004) "The Price of Robustness." Operations Research.
- Ben-Tal & Nemirovski (1999) "Robust solutions of uncertain linear programs." OR Letters.
- Pozo & Contreras (2013) "A chance-constrained unit commitment with an n-K
  security criterion and significant wind generation." IEEE Trans. Power Syst.

Uso
---
    from advanced_features.feature_08_robust_gamma import (
        RobustGammaConfig, build_robust_model, sensitivity_gamma
    )

    config = RobustGammaConfig(
        gamma_irr=5.0,   # até 5 horas com irradiância adversa
        gamma_ev=3.0,    # até 3 horas com carga VE adversa
        irr_uncertainty=0.20,   # ±20% de incerteza na irradiância
        ev_uncertainty=0.25,    # ±25% de incerteza na carga VE
    )
    model = build_robust_model(config)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
    maximize,
    minimize,
    value,
)
from pyomo.opt import SolverStatus, TerminationCondition


# ---------------------------------------------------------------------------
# Configuração de robustez
# ---------------------------------------------------------------------------

@dataclass
class RobustGammaConfig:
    """
    Configuração do modelo de robustez Γ de Bertsimas & Sim.

    Atributos
    ---------
    gamma_irr : Γ para a incerteza de irradiância ∈ [0, 24]
        Número (possivelmente fracionário) de períodos com irradiância adversa
        que o modelo garante suportar simultaneamente.
        - Γ=0: determinístico (sem robustez à irradiância)
        - Γ=24: robusto ao pior caso simultâneo em todas as horas

    gamma_ev : Γ para a incerteza de carga VE ∈ [0, 24]
        Número de períodos com demanda VE adversa (acima do nominal).

    irr_uncertainty : incerteza relativa da irradiância ∈ (0, 1]
        Perturbação máxima: Δ_irr[t] = irr_uncertainty * irr_nominal[t]
        Exemplo: 0.20 = ±20% de variação da irradiância nominal.

    ev_uncertainty : incerteza relativa da carga VE ∈ (0, 1]
        Perturbação máxima: Δ_ev[t] = ev_uncertainty * P_EV_load_nominal[t]
        Exemplo: 0.25 = ±25% de variação da carga VE nominal.

    robust_side : "conservative" ou "aggressive"
        "conservative": irradiância no pior caso (-Δ) E carga no pior caso (+Δ)
        "aggressive": apenas irradiância ou apenas carga no pior caso
    """

    gamma_irr: float = 6.0
    gamma_ev: float = 4.0
    irr_uncertainty: float = 0.20
    ev_uncertainty: float = 0.25
    robust_side: str = "conservative"

    def __post_init__(self) -> None:
        if not 0.0 <= self.gamma_irr <= 24.0:
            raise ValueError(f"gamma_irr deve estar em [0, 24]. Recebido: {self.gamma_irr}")
        if not 0.0 <= self.gamma_ev <= 24.0:
            raise ValueError(f"gamma_ev deve estar em [0, 24]. Recebido: {self.gamma_ev}")
        if not 0.0 < self.irr_uncertainty <= 1.0:
            raise ValueError(f"irr_uncertainty deve estar em (0, 1]. Recebido: {self.irr_uncertainty}")
        if not 0.0 < self.ev_uncertainty <= 1.0:
            raise ValueError(f"ev_uncertainty deve estar em (0, 1]. Recebido: {self.ev_uncertainty}")

    @classmethod
    def deterministic(cls) -> "RobustGammaConfig":
        """Caso determinístico (Γ=0, equivalente ao modelo base)."""
        return cls(gamma_irr=0.0, gamma_ev=0.0, irr_uncertainty=0.01, ev_uncertainty=0.01)

    @classmethod
    def moderate(cls) -> "RobustGammaConfig":
        """Robustez moderada: protege contra ~25% das horas com condições adversas."""
        return cls(gamma_irr=6.0, gamma_ev=4.0, irr_uncertainty=0.20, ev_uncertainty=0.20)

    @classmethod
    def conservative(cls) -> "RobustGammaConfig":
        """Robustez conservadora: protege contra ~50% das horas com condições adversas."""
        return cls(gamma_irr=12.0, gamma_ev=8.0, irr_uncertainty=0.30, ev_uncertainty=0.30)

    @classmethod
    def worst_case(cls) -> "RobustGammaConfig":
        """Pior caso absoluto (minimax): todas as horas no pior cenário."""
        return cls(gamma_irr=24.0, gamma_ev=24.0, irr_uncertainty=0.40, ev_uncertainty=0.40)


# ---------------------------------------------------------------------------
# Construção do modelo robusto
# ---------------------------------------------------------------------------

def build_robust_model(
    config: Optional[RobustGammaConfig] = None,
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
    irradiance_cf_nominal: Optional[Dict[int, float]] = None,
    P_EV_load_nominal: Optional[Dict[int, float]] = None,
    grid_price: Optional[Dict[int, float]] = None,
) -> AbstractModel:
    """
    Constrói o modelo robusto Γ conforme Bertsimas & Sim (2004).

    Reformulação dual aplicada
    --------------------------
    Para a restrição de geração FV robusta:
        P_pv_gen[t] ≤ P_pv_cap * irr_nominal[t]   (nominal)
    →   P_pv_gen[t] ≤ P_pv_cap * (irr_nominal[t] - irr_uncertainty * irr_nominal[t] * u_irr[t])

    onde a perturbação total no pior caso satisfaz:
        Σ_t u_irr[t] ≤ gamma_irr,  u_irr[t] ∈ [0, 1]

    A reformulação dual substitui max_{u: Σu≤Γ, u∈[0,1]} por variáveis duais (z, p):
        P_pv_gen[t] ≤ P_pv_cap * irr_nominal[t] - p_irr[t]
        p_irr[t] + z_irr ≥ irr_uncertainty * irr_nominal[t] * P_pv_cap
        p_irr[t] ≥ 0, z_irr ≥ 0
        Σ_t p_irr[t] + gamma_irr * z_irr ≤ 0  (embutido no limite de geração)

    Para a demanda VE robusta (pior caso = carga máxima):
        P_EV_load_robust[t] = P_EV_load_nominal[t] + p_ev[t] / 1
    →   balanço usa P_EV_load[t] + ev_uncertainty * P_EV_load[t] * v_ev[t]

    Args:
        config: configuração de robustez. Padrão: RobustGammaConfig.moderate().
        Demais: parâmetros técnico-econômicos e perfis temporais.

    Returns:
        AbstractModel Pyomo com reformulação dual robusta.
    """
    if config is None:
        config = RobustGammaConfig.moderate()

    # Perfis padrão
    if irradiance_cf_nominal is None:
        irradiance_cf_nominal = {
            1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.10, 6: 0.30,
            7: 0.50, 8: 0.70, 9: 0.90, 10: 1.00, 11: 0.95, 12: 0.90,
            13: 0.85, 14: 0.80, 15: 0.70, 16: 0.50, 17: 0.30, 18: 0.10,
            19: 0.00, 20: 0.00, 21: 0.00, 22: 0.00, 23: 0.00, 24: 0.00,
        }
    if P_EV_load_nominal is None:
        P_EV_load_nominal = {
            1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
            9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
            16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
            22: 72, 23: 54, 24: 42,
        }
    if grid_price is None:
        grid_price = {
            1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25, 6: 0.25,
            7: 0.54, 8: 0.88, 9: 0.88, 10: 0.88, 11: 0.88, 12: 0.54,
            13: 0.54, 14: 0.54, 15: 0.54, 16: 0.54, 17: 0.88, 18: 1.10,
            19: 1.10, 20: 1.10, 21: 0.88, 22: 0.54, 23: 0.25, 24: 0.25,
        }

    # Perturbações por hora
    delta_irr = {t: config.irr_uncertainty * irradiance_cf_nominal[t] for t in range(1, 25)}
    delta_ev = {t: config.ev_uncertainty * P_EV_load_nominal[t] for t in range(1, 25)}

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

    # Parâmetros de robustez
    m.gamma_irr = Param(initialize=config.gamma_irr, within=NonNegativeReals)
    m.gamma_ev = Param(initialize=config.gamma_ev, within=NonNegativeReals)

    # Perfis nominais e perturbações
    m.irr_nominal = Param(m.T, initialize=irradiance_cf_nominal, within=NonNegativeReals)
    m.delta_irr = Param(m.T, initialize=delta_irr, within=NonNegativeReals)
    m.ev_nominal = Param(m.T, initialize=P_EV_load_nominal, within=NonNegativeReals)
    m.delta_ev = Param(m.T, initialize=delta_ev, within=NonNegativeReals)
    m.grid_price = Param(m.T, initialize=grid_price, within=NonNegativeReals)

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

    # Variáveis duais robustas — irradiância
    m.z_irr = Var(within=NonNegativeReals)       # variável dual escalar
    m.p_irr = Var(m.T, within=NonNegativeReals)  # variáveis duais por hora

    # Variáveis duais robustas — carga VE
    m.z_ev = Var(within=NonNegativeReals)
    m.p_ev = Var(m.T, within=NonNegativeReals)

    # Variável de pior caso da carga VE efetiva
    m.P_EV_robust = Var(m.T, within=NonNegativeReals)  # carga robusta = nominal + pior caso

    # Restrições do sistema base
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

    # Restrições robustas de geração FV (pior caso: irradiância mínima)
    # P_pv_gen[t] ≤ P_pv_cap * irr_nominal[t] - p_irr[t]
    def pv_robust_limit(model, t):
        return model.P_pv_gen[t] <= model.P_pv_cap * model.irr_nominal[t] - model.p_irr[t]
    m.PVRobustLimit = Constraint(m.T, rule=pv_robust_limit)

    # Dual: p_irr[t] + z_irr ≥ delta_irr[t] * P_pv_cap
    # (vincula a perturbação dual à capacidade PV — produto bilinear, linearizado via big-M)
    # Linearização: delta_irr[t] * P_pv_cap ≤ delta_irr[t] * P_pv_cap_max (constante)
    def pv_dual_per_hour(model, t):
        return model.p_irr[t] + model.z_irr >= model.delta_irr[t] * model.P_pv_cap_max
    m.PVDualPerHour = Constraint(m.T, rule=pv_dual_per_hour)

    # Restrição do orçamento de incerteza irradiância:
    # Σ_t p_irr[t] + gamma_irr * z_irr ≤ budget (incorporado no limite PV acima)
    # Nota: a formulação Bertsimas-Sim garante que |S| ≤ Γ horas são perturbadas
    def irr_budget(model):
        return sum(model.p_irr[t] for t in model.T) + model.gamma_irr * model.z_irr <= model.gamma_irr * max(delta_irr.values())
    m.IrrBudget = Constraint(rule=irr_budget)

    # Restrições robustas de carga VE (pior caso: demanda máxima)
    # P_EV_robust[t] = P_EV_nominal[t] + p_ev[t] (perturbação aditiva)
    def ev_robust_def(model, t):
        return model.P_EV_robust[t] >= model.ev_nominal[t] + model.p_ev[t]
    m.EVRobustDef = Constraint(m.T, rule=ev_robust_def)

    def ev_robust_nominal(model, t):
        return model.P_EV_robust[t] >= model.ev_nominal[t]
    m.EVRobustNominal = Constraint(m.T, rule=ev_robust_nominal)

    # Dual EV: p_ev[t] + z_ev ≥ delta_ev[t]
    def ev_dual_per_hour(model, t):
        return model.p_ev[t] + model.z_ev >= model.delta_ev[t]
    m.EVDualPerHour = Constraint(m.T, rule=ev_dual_per_hour)

    # Orçamento EV: Σ p_ev[t] + gamma_ev * z_ev ≤ budget
    def ev_budget(model):
        return sum(model.p_ev[t] for t in model.T) + model.gamma_ev * model.z_ev <= model.gamma_ev * max(delta_ev.values())
    m.EVBudget = Constraint(rule=ev_budget)

    # Balanço de energia robusto (usa carga robusta)
    def energy_balance_robust(model, t):
        return (
            model.P_pv_gen[t] + model.P_grid_import[t] + model.P_bess_discharge[t]
            == model.P_EV_robust[t] - model.LoadShedding[t] + model.P_bess_charge[t] + model.P_grid_export[t]
        )
    m.EnergyBalance = Constraint(m.T, rule=energy_balance_robust)

    def no_shedding(model, t):
        return model.LoadShedding[t] == 0.0
    m.NoShedding = Constraint(m.T, rule=no_shedding)

    # Função objetivo: maximizar lucro líquido robusto
    def objective_rule(model):
        daily_rev = sum(
            model.tariff_ev * model.ev_nominal[t]  # receita na demanda nominal
            - model.grid_price[t] * model.P_grid_import[t]
            for t in model.T
        )
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )
        return model.operational_days * daily_rev - annual_investment

    m.Obj = Objective(rule=objective_rule, sense=maximize)
    return m


# ---------------------------------------------------------------------------
# Análise de sensibilidade ao Γ (price of robustness)
# ---------------------------------------------------------------------------

def sensitivity_gamma(
    gamma_values: Optional[List[float]] = None,
    solver_name: str = "cbc",
    verbose: bool = True,
    **model_params,
) -> List[Dict]:
    """
    Analisa o "Price of Robustness" — como o dimensionamento e custo variam
    com o parâmetro Γ.

    Args:
        gamma_values: lista de Γ a testar. Padrão: [0, 2, 4, 6, 8, 12, 16, 24].
        solver_name: nome do solver Pyomo.
        verbose: imprime progresso.
        **model_params: parâmetros do modelo robusto.

    Returns:
        Lista de dicionários com resultados por Γ.
    """
    if gamma_values is None:
        gamma_values = [0.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0]

    results = []
    for gamma in gamma_values:
        if verbose:
            print(f"[Γ-Robustez] Γ_irr={gamma:.1f}, Γ_ev={gamma/2:.1f}...")

        config = RobustGammaConfig(
            gamma_irr=gamma,
            gamma_ev=gamma / 2,
            irr_uncertainty=model_params.pop("irr_uncertainty", 0.20),
            ev_uncertainty=model_params.pop("ev_uncertainty", 0.25),
        )
        try:
            model = build_robust_model(config, **model_params)
            instance = model.create_instance()
            solver = SolverFactory(solver_name)
            res = solver.solve(instance, tee=False)

            is_opt = (
                res.solver.status == SolverStatus.ok and
                res.solver.termination_condition in (
                    TerminationCondition.optimal, TerminationCondition.locallyOptimal
                )
            )

            if is_opt:
                pv = value(instance.P_pv_cap)
                bess = value(instance.E_bess_cap)
                trafo = value(instance.P_trafo_cap)
                inv = (
                    (config.gamma_irr * 0 + value(instance.crf_pv) * value(instance.capex_pv_kw)) * pv
                    + value(instance.crf_bess) * value(instance.capex_bess_kwh) * bess
                    + value(instance.crf_trafo) * value(instance.capex_trafo_kw) * trafo
                )
                results.append({
                    "gamma_irr": gamma,
                    "gamma_ev": gamma / 2,
                    "P_pv_cap": pv,
                    "E_bess_cap": bess,
                    "P_trafo_cap": trafo,
                    "status": "optimal",
                })
            else:
                results.append({"gamma_irr": gamma, "gamma_ev": gamma / 2, "status": "infeasible"})
        except Exception as e:
            results.append({"gamma_irr": gamma, "gamma_ev": gamma / 2, "status": f"error: {e}"})

    return results


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 8 — Otimização Robusta Γ (Bertsimas & Sim)")
    print("=" * 60)

    configs = [
        ("Determinístico (Γ=0)", RobustGammaConfig.deterministic()),
        ("Moderado (Γ=6,4)", RobustGammaConfig.moderate()),
        ("Conservador (Γ=12,8)", RobustGammaConfig.conservative()),
    ]

    print("\nConfiguração dos modelos robustos:")
    for name, cfg in configs:
        print(f"\n  [{name}]")
        print(f"    Γ_irr={cfg.gamma_irr} | Γ_ev={cfg.gamma_ev}")
        print(f"    Δ_irr={cfg.irr_uncertainty*100:.0f}% | Δ_ev={cfg.ev_uncertainty*100:.0f}%")
        print(f"    Proteção irradiância: garante contra {cfg.gamma_irr:.0f} horas adversas simultâneas")
        print(f"    Proteção carga VE: garante contra {cfg.gamma_ev:.0f} horas de demanda acima do nominal")
        model = build_robust_model(cfg)
        print(f"    Modelo construído com sucesso ✓")

    print("\nNota: para executar o solver e comparar dimensionamentos, use:")
    print("  sensitivity_gamma(gamma_values=[0,4,8,12,24], solver_name='cbc')")
