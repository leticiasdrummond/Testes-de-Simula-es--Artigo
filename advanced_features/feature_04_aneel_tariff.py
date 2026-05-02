"""
Feature 4 — Gestão de Demanda Contratada (Tarifa Horo-Sazonal ANEEL)
======================================================================

Objetivo
--------
Modelar a estrutura tarifária real brasileira conforme regulação ANEEL,
incorporando a componente de demanda contratada (TUSD — Tarifa de Uso do
Sistema de Distribuição) com registro de ponta e fora-ponta.

Contexto regulatório brasileiro (ANEEL)
----------------------------------------
A tarifa de energia para Grupo A (média/alta tensão) é composta por:

  1. TUSD-Energia (TUSDe): componente volumétrica [R$/MWh]
     Cobrada sobre o consumo de energia por posto tarifário (ponta/fora-ponta).

  2. TUSD-Demanda (TUSDd): componente de potência [R$/kW/mês]
     Cobrada sobre a demanda contratada ou a medida (máximo entre elas).
     - Demanda na ponta: horas de pico do sistema (geralmente 17h-22h)
     - Demanda fora-ponta: demais horas

  3. TE (Tarifa de Energia): paga à geradora [R$/MWh]

  4. Bandeiras tarifárias: sobrepreço em vermelho/amarelo/verde.

Formulação matemática
---------------------

Variável de demanda contratada:
    P_contracted [kW] — variável de decisão (contrato com distribuidora)

Parâmetro de custo de demanda:
    tariff_demand [BRL/kW/mês] — tarifa TUSD-D para posto de ponta

Restrição de potência contratada:
    P_grid_import[t] <= P_contracted  para todo t na ponta
    P_grid_import[t] <= P_contracted_fp  para todo t fora da ponta

Custo de demanda no objetivo:
    custo_demanda_mensal = tariff_demand * P_contracted + tariff_demand_fp * P_contracted_fp
    custo_demanda_anual = 12 * custo_demanda_mensal

Ultrapassagem de demanda (opcional):
    Se P_grid_import[t] > P_contracted, aplica tarifa de ultrapassagem:
    custo_ultrapassagem = 3 * tariff_demand * max(0, P_grid_import[t] - P_contracted)

Referências
-----------
- ANEEL Resolução Normativa 1000/2021 — Condições gerais de fornecimento de energia.
- ANEEL (2023) "Tarifas de Energia Elétrica — Procedimentos de Regulação Tarifária."
- PRODIST Módulo 7 — Cálculo de tarifas de uso do sistema de distribuição.

Uso
---
    from advanced_features.feature_04_aneel_tariff import (
        ANEELTariffConfig, build_model_aneel, compute_aneel_bill
    )

    tariff = ANEELTariffConfig(
        tariff_demand_peak=45.0,    # BRL/kW/mês na ponta
        tariff_demand_offpeak=20.0, # BRL/kW/mês fora da ponta
        peak_hours={17, 18, 19, 20, 21},  # horas de ponta
    )
    model = build_model_aneel(tariff)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    Set as PyomoSet,
    SolverFactory,
    Var,
    maximize,
    value,
)


# ---------------------------------------------------------------------------
# Configuração de tarifa ANEEL
# ---------------------------------------------------------------------------

@dataclass
class ANEELTariffConfig:
    """
    Configuração da estrutura tarifária ANEEL horo-sazonal Grupo A.

    Atributos
    ---------
    tariff_demand_peak : Tarifa de demanda na ponta [BRL/kW/mês]
        Referência: TUSD-D posto ponta da distribuidora local.
        Valores típicos: 30–80 BRL/kW/mês (varia por distribuidora e tensão).

    tariff_demand_offpeak : Tarifa de demanda fora da ponta [BRL/kW/mês]
        Geralmente 0 (não cobrado) ou 30–60% da tarifa de ponta.

    tariff_energy_peak : Tarifa volumétrica na ponta [BRL/kWh]
        Composição: TUSD-E ponta + TE ponta + encargos.
        Referência: 0.80–1.50 BRL/kWh (ponta, Grupo A, ANEEL 2023).

    tariff_energy_offpeak : Tarifa volumétrica fora da ponta [BRL/kWh]
        Referência: 0.40–0.90 BRL/kWh.

    peak_hours : conjunto de horas (1–24) consideradas "ponta tarifária"
        Padrão ANEEL: 17h–22h (horas 17, 18, 19, 20, 21 ou 18–21 conforme distribuidora).

    ultrapassagem_factor : fator de penalidade por ultrapassagem da demanda contratada
        Padrão ANEEL: 3x a tarifa de demanda.

    months_per_year : meses por ano (padrão: 12)
    """

    tariff_demand_peak: float = 45.0          # BRL/kW/mês
    tariff_demand_offpeak: float = 0.0        # BRL/kW/mês (muitas distribuidoras = 0)
    tariff_energy_peak: float = 1.10          # BRL/kWh na ponta
    tariff_energy_offpeak: float = 0.54       # BRL/kWh fora da ponta
    peak_hours: Set[int] = field(default_factory=lambda: {17, 18, 19, 20, 21})
    ultrapassagem_factor: float = 3.0         # fator de penalidade
    months_per_year: float = 12.0

    def is_peak(self, hour: int) -> bool:
        return hour in self.peak_hours

    def energy_tariff(self, hour: int) -> float:
        return self.tariff_energy_peak if self.is_peak(hour) else self.tariff_energy_offpeak

    @property
    def annual_demand_charge_per_kw(self) -> float:
        """Custo anual de demanda por kW contratado [BRL/kW/ano]."""
        return self.months_per_year * self.tariff_demand_peak

    @classmethod
    def enel_sp_reference(cls) -> "ANEELTariffConfig":
        """Referência aproximada para Enel SP (2023) — Grupo A4 (13,8kV)."""
        return cls(
            tariff_demand_peak=52.0,
            tariff_demand_offpeak=0.0,
            tariff_energy_peak=1.20,
            tariff_energy_offpeak=0.62,
            peak_hours={17, 18, 19, 20, 21},
        )

    @classmethod
    def cemig_reference(cls) -> "ANEELTariffConfig":
        """Referência aproximada para CEMIG (2023) — Grupo A4."""
        return cls(
            tariff_demand_peak=38.0,
            tariff_demand_offpeak=0.0,
            tariff_energy_peak=0.98,
            tariff_energy_offpeak=0.48,
            peak_hours={17, 18, 19, 20, 21},
        )

    @classmethod
    def light_reference(cls) -> "ANEELTariffConfig":
        """Referência aproximada para Light/Rio (2023) — Grupo A4."""
        return cls(
            tariff_demand_peak=47.0,
            tariff_demand_offpeak=0.0,
            tariff_energy_peak=1.05,
            tariff_energy_offpeak=0.55,
            peak_hours={18, 19, 20, 21},
        )


# ---------------------------------------------------------------------------
# Construção do modelo com tarifa ANEEL
# ---------------------------------------------------------------------------

def build_model_aneel(
    tariff: Optional[ANEELTariffConfig] = None,
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
    allow_ultrapassagem: bool = True,
) -> AbstractModel:
    """
    Constrói modelo Pyomo com estrutura tarifária ANEEL horo-sazonal completa.

    Diferenças em relação ao modelo base
    --------------------------------------
    1. `grid_price[t]` é substituído pela tarifa horo-sazonal ANEEL.
    2. Nova variável `P_contracted` [kW]: demanda contratada na ponta.
    3. Nova variável `P_contracted_fp` [kW]: demanda contratada fora da ponta.
    4. Restrição de potência contratada por posto tarifário.
    5. Custo de demanda anualizado na função objetivo.
    6. (Opcional) Custo de ultrapassagem como penalidade adicional.

    Args:
        tariff: configuração da tarifa ANEEL. Padrão: ANEELTariffConfig().
        allow_ultrapassagem: se True, permite ultrapassagem com penalidade;
                             se False, proíbe ultrapassagem (restrição rígida).
        Demais: parâmetros técnico-econômicos do sistema.

    Returns:
        AbstractModel Pyomo. Séries de carga passadas via .dat.
    """
    if tariff is None:
        tariff = ANEELTariffConfig()

    m = AbstractModel()
    m.T = RangeSet(1, 24)

    # Identificar horas de ponta (conjunto estático baseado na configuração)
    peak_list = sorted(tariff.peak_hours)
    offpeak_list = [t for t in range(1, 25) if t not in tariff.peak_hours]

    m.T_peak = PyomoSet(initialize=peak_list)
    m.T_offpeak = PyomoSet(initialize=offpeak_list)

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
    m.months_per_year = Param(initialize=tariff.months_per_year, within=NonNegativeReals)

    # Parâmetros tarifários ANEEL
    m.tariff_demand_peak = Param(initialize=tariff.tariff_demand_peak, within=NonNegativeReals)
    m.tariff_demand_offpeak = Param(initialize=tariff.tariff_demand_offpeak, within=NonNegativeReals)
    m.tariff_energy_peak = Param(initialize=tariff.tariff_energy_peak, within=NonNegativeReals)
    m.tariff_energy_offpeak = Param(initialize=tariff.tariff_energy_offpeak, within=NonNegativeReals)
    m.ultrapassagem_factor = Param(initialize=tariff.ultrapassagem_factor, within=NonNegativeReals)

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

    # Séries temporais — via .dat
    m.irradiance_cf = Param(m.T, within=NonNegativeReals)
    m.P_EV_load = Param(m.T, within=NonNegativeReals)

    # Variáveis de investimento
    m.P_pv_cap = Var(within=NonNegativeReals, bounds=(0, P_pv_cap_max))
    m.E_bess_cap = Var(within=NonNegativeReals, bounds=(0, E_bess_cap_max))
    m.P_trafo_cap = Var(within=NonNegativeReals, bounds=(0, P_trafo_cap_max))

    # Variável de demanda contratada (primeiro estágio!)
    m.P_contracted = Var(within=NonNegativeReals)       # kW contratados na ponta
    m.P_contracted_fp = Var(within=NonNegativeReals)    # kW contratados fora da ponta

    # Variáveis operacionais
    m.P_pv_gen = Var(m.T, within=NonNegativeReals)
    m.P_grid_import = Var(m.T, within=NonNegativeReals)
    m.P_grid_export = Var(m.T, within=NonNegativeReals)
    m.P_bess_charge = Var(m.T, within=NonNegativeReals)
    m.P_bess_discharge = Var(m.T, within=NonNegativeReals)
    m.SOC = Var(m.T, within=NonNegativeReals)
    m.LoadShedding = Var(m.T, within=NonNegativeReals)
    m.y_bess = Var(m.T, within=Binary)

    # Ultrapassagem de demanda (opcional)
    if allow_ultrapassagem:
        m.P_ultrapassagem = Var(m.T, within=NonNegativeReals)  # kW além do contratado

    # Restrições base
    def pv_limit(model, t):
        return model.P_pv_gen[t] <= model.P_pv_cap * model.irradiance_cf[t]
    m.PVLimit = Constraint(m.T, rule=pv_limit)

    def trafo_limit(model, t):
        return model.P_grid_import[t] <= model.P_trafo_cap
    m.TrafoLimit = Constraint(m.T, rule=trafo_limit)

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

    def no_shedding(model, t):
        return model.LoadShedding[t] == 0.0
    m.NoShedding = Constraint(m.T, rule=no_shedding)

    # Restrições de demanda contratada ANEEL
    # Horas de ponta: importação ≤ P_contracted (+ ultrapassagem se permitida)
    if allow_ultrapassagem:
        def contracted_peak_limit(model, t):
            return model.P_grid_import[t] <= model.P_contracted + model.P_ultrapassagem[t]
        m.ContractedPeakLimit = Constraint(m.T_peak, rule=contracted_peak_limit)

        def contracted_offpeak_limit(model, t):
            return model.P_grid_import[t] <= model.P_contracted_fp + model.P_ultrapassagem[t]
        m.ContractedOffpeakLimit = Constraint(m.T_offpeak, rule=contracted_offpeak_limit)
    else:
        # Sem ultrapassagem: restrição rígida
        def contracted_peak_rigid(model, t):
            return model.P_grid_import[t] <= model.P_contracted
        m.ContractedPeakLimit = Constraint(m.T_peak, rule=contracted_peak_rigid)

        def contracted_offpeak_rigid(model, t):
            return model.P_grid_import[t] <= model.P_contracted_fp
        m.ContractedOffpeakLimit = Constraint(m.T_offpeak, rule=contracted_offpeak_rigid)

    # P_contracted deve ser suficiente para o trafo (limite superior)
    def contracted_trafo_link_peak(model):
        return model.P_contracted <= model.P_trafo_cap
    m.ContractedTrafoLinkPeak = Constraint(rule=contracted_trafo_link_peak)

    def contracted_trafo_link_offpeak(model):
        return model.P_contracted_fp <= model.P_trafo_cap
    m.ContractedTrafoLinkOffpeak = Constraint(rule=contracted_trafo_link_offpeak)

    # Função objetivo com tarifa ANEEL
    def objective_rule(model):
        # Receita de recarga VE
        daily_rev_ev = sum(model.tariff_ev * model.P_EV_load[t] for t in model.T)

        # Custo de energia horo-sazonal (substitui grid_price homogêneo)
        daily_cost_energy_peak = model.tariff_energy_peak * sum(
            model.P_grid_import[t] for t in model.T_peak
        )
        daily_cost_energy_offpeak = model.tariff_energy_offpeak * sum(
            model.P_grid_import[t] for t in model.T_offpeak
        )
        daily_cost_energy = daily_cost_energy_peak + daily_cost_energy_offpeak

        annual_operational = model.operational_days * (daily_rev_ev - daily_cost_energy)

        # Custo anual de demanda contratada ANEEL [BRL/ano]
        annual_demand_cost = model.months_per_year * (
            model.tariff_demand_peak * model.P_contracted
            + model.tariff_demand_offpeak * model.P_contracted_fp
        )

        # Custo de ultrapassagem (se habilitado)
        if allow_ultrapassagem:
            daily_ultrapassagem_cost = model.ultrapassagem_factor * model.tariff_demand_peak * sum(
                model.P_ultrapassagem[t] for t in model.T
            )
            annual_ultrapassagem_cost = model.months_per_year * daily_ultrapassagem_cost
        else:
            annual_ultrapassagem_cost = 0.0

        # CAPEX e O&M anualizado
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )

        return (annual_operational - annual_demand_cost
                - annual_ultrapassagem_cost - annual_investment)

    m.Obj = Objective(rule=objective_rule, sense=maximize)
    return m


# ---------------------------------------------------------------------------
# Cálculo da fatura ANEEL pós-otimização
# ---------------------------------------------------------------------------

def compute_aneel_bill(
    grid_import_profile: Dict[int, float],
    tariff: ANEELTariffConfig,
    P_contracted: float,
    P_contracted_fp: float,
    delta_t: float = 1.0,
) -> Dict[str, float]:
    """
    Calcula a fatura ANEEL mensal para um perfil de importação de energia.

    Args:
        grid_import_profile: P_grid_import[t] para t=1..24 [kW].
        tariff: configuração tarifária ANEEL.
        P_contracted: demanda contratada na ponta [kW].
        P_contracted_fp: demanda contratada fora da ponta [kW].
        delta_t: duração de cada intervalo [h].

    Returns:
        Dicionário com componentes da fatura [BRL/mês].
    """
    energy_peak = sum(
        grid_import_profile.get(t, 0.0) * delta_t
        for t in tariff.peak_hours
    )
    energy_offpeak = sum(
        grid_import_profile.get(t, 0.0) * delta_t
        for t in range(1, 25) if t not in tariff.peak_hours
    )

    # Demanda medida (máximo de importação no período)
    demand_measured_peak = max(
        (grid_import_profile.get(t, 0.0) for t in tariff.peak_hours),
        default=0.0,
    )
    demand_measured_offpeak = max(
        (grid_import_profile.get(t, 0.0) for t in range(1, 25) if t not in tariff.peak_hours),
        default=0.0,
    )

    # ANEEL: cobra o maior entre contratado e medido
    demand_billed_peak = max(P_contracted, demand_measured_peak)
    demand_billed_offpeak = max(P_contracted_fp, demand_measured_offpeak)

    # Ultrapassagem (demanda medida > contratada)
    ultrapassagem_peak = max(0.0, demand_measured_peak - P_contracted)
    ultrapassagem_offpeak = max(0.0, demand_measured_offpeak - P_contracted_fp)

    # Componentes da fatura
    energy_cost_peak = tariff.tariff_energy_peak * energy_peak
    energy_cost_offpeak = tariff.tariff_energy_offpeak * energy_offpeak
    demand_cost_peak = tariff.tariff_demand_peak * demand_billed_peak
    demand_cost_offpeak = tariff.tariff_demand_offpeak * demand_billed_offpeak
    ultrapassagem_cost = tariff.ultrapassagem_factor * tariff.tariff_demand_peak * (
        ultrapassagem_peak + ultrapassagem_offpeak
    )

    total = energy_cost_peak + energy_cost_offpeak + demand_cost_peak + demand_cost_offpeak + ultrapassagem_cost

    return {
        "energia_ponta_kWh": energy_peak,
        "energia_fora_ponta_kWh": energy_offpeak,
        "demanda_medida_ponta_kW": demand_measured_peak,
        "demanda_medida_fora_ponta_kW": demand_measured_offpeak,
        "demanda_faturada_ponta_kW": demand_billed_peak,
        "demanda_faturada_fora_ponta_kW": demand_billed_offpeak,
        "custo_energia_ponta_BRL": energy_cost_peak,
        "custo_energia_fora_ponta_BRL": energy_cost_offpeak,
        "custo_demanda_ponta_BRL": demand_cost_peak,
        "custo_demanda_fora_ponta_BRL": demand_cost_offpeak,
        "custo_ultrapassagem_BRL": ultrapassagem_cost,
        "total_BRL_mes": total,
        "total_BRL_ano": total * tariff.months_per_year,
    }


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 4 — Tarifa Horo-Sazonal ANEEL")
    print("=" * 60)

    for nome, cfg in [
        ("Enel SP", ANEELTariffConfig.enel_sp_reference()),
        ("CEMIG", ANEELTariffConfig.cemig_reference()),
        ("Light/Rio", ANEELTariffConfig.light_reference()),
    ]:
        print(f"\n[{nome}]")
        print(f"  Demanda ponta: {cfg.tariff_demand_peak:.1f} BRL/kW/mês")
        print(f"  Energia ponta: {cfg.tariff_energy_peak:.2f} BRL/kWh")
        print(f"  Energia fora ponta: {cfg.tariff_energy_offpeak:.2f} BRL/kWh")
        print(f"  Horas de ponta: {sorted(cfg.peak_hours)}")
        print(f"  Custo anual de demanda/kW: {cfg.annual_demand_charge_per_kw:.0f} BRL/kW/ano")

    # Exemplo de fatura
    import_profile = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
        9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
        16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
        22: 72, 23: 54, 24: 42,
    }
    tariff = ANEELTariffConfig.enel_sp_reference()
    bill = compute_aneel_bill(import_profile, tariff, P_contracted=130.0, P_contracted_fp=115.0)

    print("\n--- Fatura ANEEL (Enel SP) — cenário base ---")
    for k, v in bill.items():
        print(f"  {k}: {v:.2f}")

    print("\nModelo Pyomo ANEEL construído com sucesso.")
    model = build_model_aneel(tariff)
    print(f"  Variáveis adicionadas: P_contracted, P_contracted_fp, P_ultrapassagem[t]")
