"""
Feature 3 — Carregamento Inteligente V1G / Smart Charging
==========================================================

Objetivo
--------
Transformar `P_EV_load` de parâmetro fixo (demanda inelástica) em variável de
decisão com janelas de flexibilidade temporal, modelando o comportamento de
carregamento inteligente V1G (Vehicle-to-Grid unidirecional: apenas fluxo
rede → veículo, sem injeção VE → rede).

Formulação matemática
---------------------

Variáveis de decisão adicionais:
    P_EV_flex[t]  ∈ [P_EV_min[t], P_EV_max[t]]   [kW]
        Potência de carregamento efetivamente entregue à frota VE na hora t.
        Substitui P_EV_load[t] como parâmetro exógeno.

    P_EV_defer[t] ≥ 0   [kW]
        Carga adiada: diferença entre a demanda inelástica e a entregue.
        P_EV_defer[t] = P_EV_nominal[t] - P_EV_flex[t]

Restrições de flexibilidade:
    (a) Janela de potência horária:
            P_EV_flex[t] ∈ [P_EV_nominal[t] * (1 - flex_down[t]),
                             P_EV_nominal[t] * (1 + flex_up[t])]

    (b) Energia total da sessão garantida (satisfação mínima da frota):
            Σ_t P_EV_flex[t] * delta_t ≥ (1 - max_energy_deficit) * Σ_t P_EV_nominal[t] * delta_t

    (c) Energia adicional permitida (janelas de absorção de excedente PV):
            Σ_t P_EV_flex[t] * delta_t ≤ (1 + max_energy_surplus) * Σ_t P_EV_nominal[t] * delta_t

Função custo de desconforto (penalidade de adiamento):
    custo_desconforto = c_discomfort * Σ_t P_EV_defer[t] * delta_t
    onde c_discomfort [BRL/kWh] é o custo de insatisfação do usuário por kWh postergado.

Benefício do smart charging:
    O otimizador pode deslocar carga para horários de:
    - Menor preço da rede (arbitragem tarifária)
    - Maior geração FV (absorção de excedente solar)
    - Menor stress do BESS (ciclos de menor DoD)

Referências
-----------
- Clement-Nyns et al. (2010) "The Impact of Charging Plug-In Hybrid Electric
  Vehicles on a Residential Distribution Grid." IEEE Trans. Power Syst.
- Yao et al. (2014) "Modeling and Optimization Study of Commercial Building
  Microgrid System." Energy.
- IEA (2023) "Global EV Outlook." International Energy Agency.

Uso
---
    from advanced_features.feature_03_smart_charging import build_model_v1g

    model = build_model_v1g(
        flex_up=0.30,    # pode carregar até 30% a mais que o nominal em qualquer hora
        flex_down=0.80,  # pode reduzir até 80% da demanda nominal
        c_discomfort=0.5,  # BRL/kWh de insatisfação
        max_energy_deficit=0.05,  # máximo 5% de déficit energético total na sessão
    )
"""

from __future__ import annotations

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
    Reals,
    SolverFactory,
    Var,
    maximize,
    value,
)


# ---------------------------------------------------------------------------
# Parâmetros de flexibilidade
# ---------------------------------------------------------------------------

@dataclass
class SmartChargingConfig:
    """Configuração do carregamento inteligente V1G."""

    flex_up: float = 0.30
    """Fração máxima acima do perfil nominal que pode ser carregada em qualquer hora."""

    flex_down: float = 0.50
    """Fração máxima de redução do perfil nominal em qualquer hora."""

    max_energy_deficit: float = 0.05
    """Déficit máximo de energia na sessão diária (fração da energia nominal total)."""

    max_energy_surplus: float = 0.10
    """Superávit máximo de energia na sessão diária (fração da energia nominal total)."""

    c_discomfort: float = 0.50
    """Custo de insatisfação do usuário por kWh adiado/não entregue [BRL/kWh]."""

    allow_per_hour_flexibility: bool = True
    """Se True, flexibilidade é aplicada por hora; se False, apenas na janela total."""

    @classmethod
    def conservative(cls) -> "SmartChargingConfig":
        """Configuração conservadora: pequena janela de flexibilidade, penalidade alta."""
        return cls(flex_up=0.10, flex_down=0.20, max_energy_deficit=0.02, c_discomfort=1.0)

    @classmethod
    def moderate(cls) -> "SmartChargingConfig":
        """Configuração moderada: janela razoável, penalidade moderada."""
        return cls(flex_up=0.30, flex_down=0.50, max_energy_deficit=0.05, c_discomfort=0.50)

    @classmethod
    def aggressive(cls) -> "SmartChargingConfig":
        """Configuração agressiva: grande flexibilidade, penalidade baixa."""
        return cls(flex_up=0.50, flex_down=0.80, max_energy_deficit=0.10, c_discomfort=0.20)


# ---------------------------------------------------------------------------
# Construção do modelo V1G
# ---------------------------------------------------------------------------

def build_model_v1g(
    config: Optional[SmartChargingConfig] = None,
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
) -> AbstractModel:
    """
    Constrói o modelo Pyomo com Smart Charging V1G.

    Diferenças em relação ao modelo base (main.py)
    ------------------------------------------------
    1. `P_EV_load[t]` é agora parâmetro de referência (perfil nominal exógeno).
    2. Nova variável `P_EV_flex[t]`: carga efetivamente entregue (decisão do otimizador).
    3. Nova variável `P_EV_defer[t]`: desvio negativo do perfil nominal.
    4. Restrições de janela de potência por hora.
    5. Restrição de energia total mínima e máxima na sessão diária.
    6. Função objetivo inclui custo de desconforto do usuário.

    Args:
        config: configuração de flexibilidade. Padrão: SmartChargingConfig.moderate().
        Demais: parâmetros técnico-econômicos do sistema.

    Returns:
        AbstractModel Pyomo. Séries temporais devem ser fornecidas via .dat ou dict.
    """
    if config is None:
        config = SmartChargingConfig.moderate()

    m = AbstractModel()
    m.T = RangeSet(1, 24)

    # Parâmetros econômicos
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

    # Parâmetros técnicos BESS
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

    # Parâmetros de flexibilidade do smart charging
    m.flex_up = Param(initialize=config.flex_up, within=NonNegativeReals)
    m.flex_down = Param(initialize=config.flex_down, within=NonNegativeReals)
    m.max_energy_deficit = Param(initialize=config.max_energy_deficit, within=NonNegativeReals)
    m.max_energy_surplus = Param(initialize=config.max_energy_surplus, within=NonNegativeReals)
    m.c_discomfort = Param(initialize=config.c_discomfort, within=NonNegativeReals)

    # Séries temporais — passadas via .dat
    m.irradiance_cf = Param(m.T, within=NonNegativeReals)
    m.grid_price = Param(m.T, within=NonNegativeReals)
    m.P_EV_nominal = Param(m.T, within=NonNegativeReals)  # perfil nominal (referência)

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
    m.y_bess = Var(m.T, within=Binary)

    # Variáveis de smart charging
    m.P_EV_flex = Var(m.T, within=NonNegativeReals)   # carga efetivamente entregue [kW]
    m.P_EV_defer = Var(m.T, within=NonNegativeReals)  # carga adiada (desconforto) [kW]

    # Restrições do sistema base
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

    # Balanço de energia — usa P_EV_flex (variável) em vez de P_EV_load (parâmetro)
    def energy_balance(model, t):
        return (
            model.P_pv_gen[t] + model.P_grid_import[t] + model.P_bess_discharge[t]
            == model.P_EV_flex[t] + model.P_bess_charge[t] + model.P_grid_export[t]
        )
    m.EnergyBalance = Constraint(m.T, rule=energy_balance)

    # Restrições de smart charging
    # (a) Janela de potência por hora: P_EV_flex[t] ∈ [min, max]
    def ev_flex_lower(model, t):
        return model.P_EV_flex[t] >= model.P_EV_nominal[t] * (1.0 - model.flex_down)
    m.EVFlexLower = Constraint(m.T, rule=ev_flex_lower)

    def ev_flex_upper(model, t):
        return model.P_EV_flex[t] <= model.P_EV_nominal[t] * (1.0 + model.flex_up)
    m.EVFlexUpper = Constraint(m.T, rule=ev_flex_upper)

    # (b) Energia total mínima garantida na sessão diária
    def ev_energy_min(model):
        E_nominal = sum(model.P_EV_nominal[t] for t in model.T)
        E_flex = sum(model.P_EV_flex[t] for t in model.T)
        return E_flex >= (1.0 - model.max_energy_deficit) * E_nominal
    m.EVEnergyMin = Constraint(rule=ev_energy_min)

    # (c) Energia total máxima na sessão diária
    def ev_energy_max(model):
        E_nominal = sum(model.P_EV_nominal[t] for t in model.T)
        E_flex = sum(model.P_EV_flex[t] for t in model.T)
        return E_flex <= (1.0 + model.max_energy_surplus) * E_nominal
    m.EVEnergyMax = Constraint(rule=ev_energy_max)

    # (d) Definição do desvio de carga (desconforto)
    def ev_defer_def(model, t):
        return model.P_EV_defer[t] >= model.P_EV_nominal[t] - model.P_EV_flex[t]
    m.EVDeferDef = Constraint(m.T, rule=ev_defer_def)

    # Função objetivo
    def objective_rule(model):
        daily_rev_ev = sum(model.tariff_ev * model.P_EV_flex[t] for t in model.T)
        daily_cost_import = sum(model.grid_price[t] * model.P_grid_import[t] for t in model.T)
        daily_discomfort = model.c_discomfort * sum(model.P_EV_defer[t] for t in model.T)

        annual_operational = model.operational_days * (daily_rev_ev - daily_cost_import - daily_discomfort)
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )
        return annual_operational - annual_investment

    m.Obj = Objective(rule=objective_rule, sense=maximize)
    return m


# ---------------------------------------------------------------------------
# Análise de impacto do smart charging
# ---------------------------------------------------------------------------

def estimate_smart_charging_benefit(
    P_EV_nominal: Dict[int, float],
    grid_price: Dict[int, float],
    config: SmartChargingConfig,
    delta_t: float = 1.0,
) -> Dict[str, float]:
    """
    Estima o benefício potencial máximo do smart charging sem solver (análise rápida).

    Estratégia heurística:
    - Desloca carga dos horários de pico tarifário para os de menor tarifa.
    - Respeita janelas de flexibilidade.
    - Calcula a redução de custo de importação potencial.

    Args:
        P_EV_nominal: perfil nominal de carga VE [kW] por hora.
        grid_price: preço horário da rede [BRL/kWh].
        config: configuração de flexibilidade.
        delta_t: duração do intervalo [h].

    Returns:
        Dicionário com métricas de benefício estimado.
    """
    hours = sorted(P_EV_nominal.keys())
    E_nominal = sum(P_EV_nominal[t] * delta_t for t in hours)

    # Calcular custo de importação sem smart charging (cenário base)
    base_cost = sum(grid_price[t] * P_EV_nominal[t] * delta_t for t in hours)

    # Ordenar horas por preço (desloca carga dos caros para baratos)
    sorted_by_price = sorted(hours, key=lambda t: grid_price[t])
    flex_load = dict(P_EV_nominal)  # cópia

    # Reduzir nas horas caras (cima do ranking), aumentar nas baratas
    price_threshold = sorted(set(grid_price.values()))[len(set(grid_price.values())) // 2]
    expensive_hours = [t for t in hours if grid_price[t] > price_threshold]
    cheap_hours = [t for t in hours if grid_price[t] <= price_threshold]

    deferred_kwh = 0.0
    for t in expensive_hours:
        reduction = P_EV_nominal[t] * config.flex_down * delta_t
        flex_load[t] = max(
            P_EV_nominal[t] * (1 - config.flex_down),
            flex_load[t] - reduction / delta_t,
        )
        deferred_kwh += reduction

    # Redistribuir nas horas baratas (respeitando flex_up)
    for t in cheap_hours:
        if deferred_kwh <= 0:
            break
        headroom = P_EV_nominal[t] * config.flex_up * delta_t
        added = min(headroom, deferred_kwh)
        flex_load[t] = flex_load[t] + added / delta_t
        deferred_kwh -= added

    smart_cost = sum(grid_price[t] * flex_load[t] * delta_t for t in hours)
    peak_nominal = max(P_EV_nominal.values())
    peak_smart = max(flex_load.values())

    return {
        "E_nominal_kWh": E_nominal,
        "custo_base_BRL": base_cost,
        "custo_smart_BRL": smart_cost,
        "reducao_custo_BRL": base_cost - smart_cost,
        "reducao_custo_pct": (base_cost - smart_cost) / base_cost * 100,
        "pico_base_kW": peak_nominal,
        "pico_smart_kW": peak_smart,
        "reducao_pico_pct": (peak_nominal - peak_smart) / peak_nominal * 100,
    }


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 3 — Smart Charging V1G")
    print("=" * 60)

    P_EV = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
        9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
        16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
        22: 72, 23: 54, 24: 42,
    }
    price = {
        1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25, 6: 0.25,
        7: 0.54, 8: 0.88, 9: 0.88, 10: 0.88, 11: 0.88, 12: 0.54,
        13: 0.54, 14: 0.54, 15: 0.54, 16: 0.54, 17: 0.88, 18: 1.10,
        19: 1.10, 20: 1.10, 21: 0.88, 22: 0.54, 23: 0.25, 24: 0.25,
    }

    for cfg_name, cfg in [
        ("Conservador", SmartChargingConfig.conservative()),
        ("Moderado", SmartChargingConfig.moderate()),
        ("Agressivo", SmartChargingConfig.aggressive()),
    ]:
        metrics = estimate_smart_charging_benefit(P_EV, price, cfg)
        print(f"\n[{cfg_name}] (flex_down={cfg.flex_down:.0%}, flex_up={cfg.flex_up:.0%})")
        print(f"  Custo base:   {metrics['custo_base_BRL']:.2f} BRL/dia")
        print(f"  Custo smart:  {metrics['custo_smart_BRL']:.2f} BRL/dia")
        print(f"  Redução:      {metrics['reducao_custo_BRL']:.2f} BRL ({metrics['reducao_custo_pct']:.1f}%)")
        print(f"  Pico base:    {metrics['pico_base_kW']:.1f} kW")
        print(f"  Pico smart:   {metrics['pico_smart_kW']:.1f} kW ({metrics['reducao_pico_pct']:.1f}% redução)")

    print("\nModelo Pyomo V1G construído com sucesso.")
    model = build_model_v1g(SmartChargingConfig.moderate())
    print(f"  Variáveis de smart charging: P_EV_flex, P_EV_defer (por hora)")
    print(f"  Restrições adicionadas: EVFlexLower, EVFlexUpper, EVEnergyMin, EVEnergyMax, EVDeferDef")
