from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    Reals,
    Set,
    Var,
    minimize,
    value,
)


"""
Modelo AbstractModel para eletroposto PV-BESS-Rede com cenarios.

Foco: incorporar blocos de restricoes associados aos itens 3.2.2, 3.2.3, 4, 5 e 6,
com avaliacao tecnica e desempenho de fornecimento para eletropostos em rodovias brasileiras.

Estrutura principal:
- Decisoes de investimento (comuns a todos os cenarios):
  P_pv_cap, E_bess_cap, P_trafo_cap
- Decisoes operacionais por cenario e hora:
  importacao/exportacao da rede, carga/descarga da bateria, SOC e corte de carga
- Objetivo: minimizar indice tecnico esperado de risco de fornecimento
- Suporte a multiplos cenarios via conjunto SC e probabilidade prob_sc
"""


def build_model() -> AbstractModel:
    m = AbstractModel()

    # ---------------------------
    # Conjuntos
    # ---------------------------
    m.T = RangeSet(1, 24)
    m.SC = Set(doc="Cenarios de operacao")

    # ---------------------------
    # Parametros globais
    # ---------------------------
    m.delta_t = Param(within=NonNegativeReals, default=1.0)

    # Probabilidade de cada cenario (somatorio esperado = 1)
    m.prob_sc = Param(m.SC, within=NonNegativeReals, mutable=True)

    # Custos de investimento
    m.capex_pv_kw = Param(within=NonNegativeReals)
    m.capex_bess_kwh = Param(within=NonNegativeReals)
    m.capex_trafo_kw = Param(within=NonNegativeReals)

    # Custo de degradacao da bateria (throughput de carga+descarga)
    m.c_deg_bess = Param(within=NonNegativeReals, default=0.0)

    # Penalidade por energia nao suprida (load shedding)
    m.c_ens = Param(within=NonNegativeReals, default=1e4)

    # Parametros tecnicos do BESS
    m.eta_charge = Param(within=NonNegativeReals)
    m.eta_discharge = Param(within=NonNegativeReals)
    m.soc_min_frac = Param(within=NonNegativeReals)
    m.soc_max_frac = Param(within=NonNegativeReals)
    m.soc_initial_frac = Param(within=NonNegativeReals)
    m.c_rate_charge = Param(within=NonNegativeReals)
    m.c_rate_discharge = Param(within=NonNegativeReals)

    # Limites maximos de projeto para Big-M fisico
    m.P_pv_cap_max = Param(within=NonNegativeReals, default=5000.0)
    m.E_bess_cap_max = Param(within=NonNegativeReals, default=1000.0)
    m.P_trafo_cap_max = Param(within=NonNegativeReals, default=1000.0)

    # Limites de desempenho tecnico do fornecimento
    m.max_ens_ratio = Param(within=NonNegativeReals, default=0.0)
    m.min_self_suff_ratio = Param(within=NonNegativeReals, default=0.0)
    m.max_hourly_ens_frac = Param(within=NonNegativeReals, default=1.0)
    m.min_soc_reserve_frac = Param(within=NonNegativeReals, default=0.0)
    m.max_grid_import_ratio = Param(within=NonNegativeReals, default=1.0)
    m.max_bess_throughput_ratio = Param(within=NonNegativeReals, default=10.0)

    # Pesos do indice tecnico (multicriterio)
    m.w_ens = Param(within=NonNegativeReals, default=1e6)
    m.w_grid_import = Param(within=NonNegativeReals, default=1.0)
    m.w_bess_throughput = Param(within=NonNegativeReals, default=0.01)
    m.w_cap_regularization = Param(within=NonNegativeReals, default=1e-3)

    # Parametros por cenario e hora
    m.grid_price = Param(m.SC, m.T, within=NonNegativeReals)
    m.export_price = Param(m.SC, m.T, within=NonNegativeReals)
    m.irradiance_cf = Param(m.SC, m.T, within=NonNegativeReals)
    m.P_EV_load = Param(m.SC, m.T, within=NonNegativeReals)
    # Disponibilidade da rede (1=disponivel; 0=indisponivel), util em cenario de falhas.
    m.grid_availability = Param(m.SC, m.T, within=NonNegativeReals, default=1.0)

    # ---------------------------
    # Variaveis de investimento (nao antecipativas)
    # ---------------------------
    m.P_pv_cap = Var(within=NonNegativeReals)
    m.E_bess_cap = Var(within=NonNegativeReals)
    m.P_trafo_cap = Var(within=NonNegativeReals)

    # ---------------------------
    # Variaveis operacionais por cenario e hora
    # ---------------------------
    m.P_pv_gen = Var(m.SC, m.T, within=NonNegativeReals)
    m.P_grid_import = Var(m.SC, m.T, within=NonNegativeReals)
    m.P_grid_export = Var(m.SC, m.T, within=NonNegativeReals)
    m.P_bess_charge = Var(m.SC, m.T, within=NonNegativeReals)
    m.P_bess_discharge = Var(m.SC, m.T, within=NonNegativeReals)
    m.SOC = Var(m.SC, m.T, within=NonNegativeReals)
    m.LoadShedding = Var(m.SC, m.T, within=NonNegativeReals)

    # Binarias para nao simultaneidade (carga/descarga e importacao/exportacao)
    m.y_bess = Var(m.SC, m.T, within=Binary)
    m.y_grid = Var(m.SC, m.T, within=Binary)

    # ---------------------------
    # Item 3.2.2 - Restricoes do sistema de armazenamento (BESS)
    # ---------------------------
    def bess_cap_upper_rule(model):
        return model.E_bess_cap <= model.E_bess_cap_max

    m.BESSCapUpper = Constraint(rule=bess_cap_upper_rule)

    def pv_cap_upper_rule(model):
        return model.P_pv_cap <= model.P_pv_cap_max

    m.PVCapUpper = Constraint(rule=pv_cap_upper_rule)

    def bess_charge_limit_rule(model, sc, t):
        return model.P_bess_charge[sc, t] <= model.c_rate_charge * model.E_bess_cap

    def bess_discharge_limit_rule(model, sc, t):
        return model.P_bess_discharge[sc, t] <= model.c_rate_discharge * model.E_bess_cap

    m.BESSChargePowerLimit = Constraint(m.SC, m.T, rule=bess_charge_limit_rule)
    m.BESSDischargePowerLimit = Constraint(m.SC, m.T, rule=bess_discharge_limit_rule)

    # Nao simultaneidade carga/descarga com Big-M fisico
    def bess_charge_mode_rule(model, sc, t):
        return model.P_bess_charge[sc, t] <= model.c_rate_charge * model.E_bess_cap_max * model.y_bess[sc, t]

    def bess_discharge_mode_rule(model, sc, t):
        return model.P_bess_discharge[sc, t] <= model.c_rate_discharge * model.E_bess_cap_max * (1 - model.y_bess[sc, t])

    m.BESSChargeMode = Constraint(m.SC, m.T, rule=bess_charge_mode_rule)
    m.BESSDischargeMode = Constraint(m.SC, m.T, rule=bess_discharge_mode_rule)

    def soc_min_rule(model, sc, t):
        return model.SOC[sc, t] >= model.soc_min_frac * model.E_bess_cap

    def soc_max_rule(model, sc, t):
        return model.SOC[sc, t] <= model.soc_max_frac * model.E_bess_cap

    m.SOCMin = Constraint(m.SC, m.T, rule=soc_min_rule)
    m.SOCMax = Constraint(m.SC, m.T, rule=soc_max_rule)

    # Reserva tecnica adicional para eventos de contingencia em rodovia.
    def soc_reserve_rule(model, sc, t):
        return model.SOC[sc, t] >= model.min_soc_reserve_frac * model.E_bess_cap

    m.SOCReserve = Constraint(m.SC, m.T, rule=soc_reserve_rule)

    def soc_balance_rule(model, sc, t):
        if t == model.T.first():
            return model.SOC[sc, t] == model.soc_initial_frac * model.E_bess_cap + model.delta_t * (
                model.eta_charge * model.P_bess_charge[sc, t]
                - model.P_bess_discharge[sc, t] / model.eta_discharge
            )
        t_prev = model.T.prev(t)
        return model.SOC[sc, t] == model.SOC[sc, t_prev] + model.delta_t * (
            model.eta_charge * model.P_bess_charge[sc, t]
            - model.P_bess_discharge[sc, t] / model.eta_discharge
        )

    m.SOCBalance = Constraint(m.SC, m.T, rule=soc_balance_rule)

    def terminal_soc_rule(model, sc):
        return model.SOC[sc, model.T.last()] == model.soc_initial_frac * model.E_bess_cap

    m.TerminalSOC = Constraint(m.SC, rule=terminal_soc_rule)

    # ---------------------------
    # Item 3.2.3 - Restricoes de interface com a rede
    # ---------------------------
    def trafo_cap_upper_rule(model):
        return model.P_trafo_cap <= model.P_trafo_cap_max

    m.TrafoCapUpper = Constraint(rule=trafo_cap_upper_rule)

    def grid_import_limit_rule(model, sc, t):
        return model.P_grid_import[sc, t] <= model.P_trafo_cap * model.grid_availability[sc, t]

    def grid_export_limit_rule(model, sc, t):
        return model.P_grid_export[sc, t] <= model.P_trafo_cap * model.grid_availability[sc, t]

    m.GridImportLimit = Constraint(m.SC, m.T, rule=grid_import_limit_rule)
    m.GridExportLimit = Constraint(m.SC, m.T, rule=grid_export_limit_rule)

    # Nao simultaneidade importacao/exportacao
    def grid_import_mode_rule(model, sc, t):
        return model.P_grid_import[sc, t] <= model.P_trafo_cap_max * model.y_grid[sc, t]

    def grid_export_mode_rule(model, sc, t):
        return model.P_grid_export[sc, t] <= model.P_trafo_cap_max * (1 - model.y_grid[sc, t])

    m.GridImportMode = Constraint(m.SC, m.T, rule=grid_import_mode_rule)
    m.GridExportMode = Constraint(m.SC, m.T, rule=grid_export_mode_rule)

    # ---------------------------
    # Item 4 - Restricao de balanco de energia e atendimento da carga
    # ---------------------------
    def pv_generation_limit_rule(model, sc, t):
        return model.P_pv_gen[sc, t] <= model.P_pv_cap * model.irradiance_cf[sc, t]

    m.PVGenerationLimit = Constraint(m.SC, m.T, rule=pv_generation_limit_rule)

    def energy_balance_rule(model, sc, t):
        return (
            model.P_pv_gen[sc, t]
            + model.P_grid_import[sc, t]
            + model.P_bess_discharge[sc, t]
            == model.P_EV_load[sc, t]
            - model.LoadShedding[sc, t]
            + model.P_bess_charge[sc, t]
            + model.P_grid_export[sc, t]
        )

    m.EnergyBalance = Constraint(m.SC, m.T, rule=energy_balance_rule)

    # ---------------------------
    # Item 5 - Restricoes de desempenho tecnico do fornecimento
    # ---------------------------
    # 5.1 Confiabilidade: limite maximo para energia nao suprida no cenario.
    def ens_ratio_rule(model, sc):
        total_load = sum(model.P_EV_load[sc, t] * model.delta_t for t in model.T)
        total_ens = sum(model.LoadShedding[sc, t] * model.delta_t for t in model.T)
        return total_ens <= model.max_ens_ratio * total_load

    m.ENSRatioLimit = Constraint(m.SC, rule=ens_ratio_rule)

    # 5.2 Criticidade operacional: limita ENS por hora para evitar colapsos localizados.
    def ens_hourly_rule(model, sc, t):
        return model.LoadShedding[sc, t] <= model.max_hourly_ens_frac * model.P_EV_load[sc, t]

    m.ENSHourlyLimit = Constraint(m.SC, m.T, rule=ens_hourly_rule)

    # 5.3 Autossuficiencia minima: fracao minima da demanda atendida por PV+BESS.
    def self_sufficiency_rule(model, sc):
        supplied_by_local = sum(
            (model.P_pv_gen[sc, t] + model.P_bess_discharge[sc, t] - model.P_bess_charge[sc, t]) * model.delta_t
            for t in model.T
        )
        total_served_load = sum((model.P_EV_load[sc, t] - model.LoadShedding[sc, t]) * model.delta_t for t in model.T)
        return supplied_by_local >= model.min_self_suff_ratio * total_served_load

    m.SelfSufficiencyMin = Constraint(m.SC, rule=self_sufficiency_rule)

    # 5.4 Dependencia maxima da rede para atendimento da carga no cenario.
    def grid_dependency_rule(model, sc):
        total_import = sum(model.P_grid_import[sc, t] * model.delta_t for t in model.T)
        total_load = sum(model.P_EV_load[sc, t] * model.delta_t for t in model.T)
        return total_import <= model.max_grid_import_ratio * total_load

    m.GridDependencyLimit = Constraint(m.SC, rule=grid_dependency_rule)

    # 5.5 Limite de estresse ciclico diario do BESS.
    def bess_throughput_rule(model, sc):
        throughput = sum(
            (model.P_bess_charge[sc, t] + model.P_bess_discharge[sc, t]) * model.delta_t
            for t in model.T
        )
        return throughput <= model.max_bess_throughput_ratio * model.E_bess_cap

    m.BESSThroughputLimit = Constraint(m.SC, rule=bess_throughput_rule)

    # ---------------------------
    # Item 6 - Restricoes para analise de cenarios
    # ---------------------------
    # Decisoes de investimento sao compartilhadas entre todos os cenarios por definicao
    # (nao antecipacao implicita pela modelagem). Aqui reforcamos normalizacao de probabilidades.
    def prob_normalization_rule(model):
        return sum(model.prob_sc[sc] for sc in model.SC) == 1.0

    m.ProbabilityNormalization = Constraint(rule=prob_normalization_rule)

    # ---------------------------
    # Funcao objetivo - indice tecnico esperado
    # ---------------------------
    def technical_viability_index_rule(model):
        expected_ens = 0.0
        expected_grid_import = 0.0
        expected_bess_throughput = 0.0
        for sc in model.SC:
            ens_sc = sum(model.LoadShedding[sc, t] * model.delta_t for t in model.T)
            grid_import_sc = sum(model.P_grid_import[sc, t] * model.delta_t for t in model.T)
            bess_throughput_sc = sum(
                (model.P_bess_charge[sc, t] + model.P_bess_discharge[sc, t]) * model.delta_t
                for t in model.T
            )

            expected_ens += model.prob_sc[sc] * ens_sc
            expected_grid_import += model.prob_sc[sc] * grid_import_sc
            expected_bess_throughput += model.prob_sc[sc] * bess_throughput_sc

        # Regularizacao fraca para desempate de solucoes tecnicamente equivalentes.
        cap_regularization = model.w_cap_regularization * (
            model.P_pv_cap + model.E_bess_cap + model.P_trafo_cap
        )

        return (
            model.w_ens * expected_ens
            + model.w_grid_import * expected_grid_import
            + model.w_bess_throughput * expected_bess_throughput
            + cap_regularization
        )

    m.TechnicalViabilityIndex = Objective(rule=technical_viability_index_rule, sense=minimize)

    return m


if __name__ == "__main__":
    # Execucao de exemplo:
    # 1) criar arquivo .dat com parametros e cenarios
    # 2) descomentar o bloco abaixo e ajustar o solver local
    #
    # from pyomo.environ import SolverFactory
    # instance = build_model().create_instance("dados_cenarios_artigo.dat")
    # result = SolverFactory("gurobi").solve(instance, tee=False)
    # print("Status:", result.solver.status)
    # print("Termination:", result.solver.termination_condition)
    # print("Indice tecnico de viabilidade:", value(instance.TechnicalViabilityIndex))
    pass
