from pathlib import Path

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
    value,
)
from pyomo.opt import SolverStatus, TerminationCondition


"""
Modelo Pyomo (AbstractModel) para microrrede de eletroposto em rodovia brasileira.
Base conceitual: Secao 3.2 do artigo de referencia — otimizacao simultanea de
configuracao de capacidade e despacho de um eletroposto integrado com FV e BESS.

=============================================================================
RESUMO DO PROBLEMA
=============================================================================
O modelo determina simultaneamente:
  (a) o dimensionamento otimo de ativos (capacidade PV em kW, BESS em kWh,
      transformador de conexao com a rede em kW); e
  (b) o despacho operacional horario desses ativos ao longo de um dia
      representativo de 24 horas (t = 1..24).

A funcao objetivo maximiza o lucro economico anualizado, descontado o custo
de investimento. A solucao viavel satisfaz restricoes fisicas (balanco de
energia, limites de potencia, dinamica de SOC) e de qualidade de servico
(atendimento integral da demanda de recarga de veiculos eletricos — VE).

=============================================================================
CONJUNTOS
=============================================================================
  T = {1, 2, ..., 24}  — horizonte horario discretizado (um dia representativo)

=============================================================================
PARAMETROS (com unidades)
=============================================================================
Escalares economicos:
  delta_t                   [h]          Duracao de cada periodo (default=1)
  operational_days_equivalent [dias/ano] Fator de anualizacao do dia representativo
  tariff_ev                 [BRL/kWh]    Tarifa de venda de recarga ao usuario VE
  export_price_factor       [-]          Fracao do grid_price paga pela exportacao
  allow_grid_export         {0,1}        Habilita (1) ou proibe (0) exportacao
  use_article_like_objective {0,1}       Seletor: 0=objetivo simplificado, 1=artigo

CAPEX (investimento unitario):
  capex_pv_kw               [BRL/kW]     Custo unitario do arranjo FV
  capex_bess_kwh             [BRL/kWh]   Custo unitario do armazenamento
  capex_trafo_kw             [BRL/kW]    Custo unitario do transformador

Anualizacao (versao artigo):
  crf_pv                    [-]          Capital Recovery Factor do FV
  crf_bess                  [-]          Capital Recovery Factor do BESS
  crf_trafo                 [-]          Capital Recovery Factor do trafo
  om_pv_kw_year             [BRL/(kW·ano)]  O&M anual do FV por kW instalado
  om_bess_kwh_year          [BRL/(kWh·ano)] O&M anual do BESS por kWh instalado
  om_trafo_kw_year          [BRL/(kW·ano)]  O&M anual do trafo por kW instalado

Tecnico BESS:
  eta_charge                [-]          Eficiencia de carga (tipicamente 0.90-0.95)
  eta_discharge             [-]          Eficiencia de descarga (tipicamente 0.90-0.95)
  soc_min_frac              [-]          SOC minimo como fracao da capacidade
  soc_max_frac              [-]          SOC maximo como fracao da capacidade
  soc_initial_frac          [-]          SOC inicial/final (condicao de periodicidade)
  c_rate_charge             [1/h]        C-rate maximo de carga
  c_rate_discharge          [1/h]        C-rate maximo de descarga
  E_bess_cap_max            [kWh]        Limite superior de projeto (usado no Big-M)
  P_pv_cap_max              [kW]         Limite superior de projeto para FV
  P_trafo_cap_max           [kW]         Limite superior de projeto para trafo

Series horarias (indexadas por t in T):
  irradiance_cf[t]          [-]          Fator de capacidade FV (∈ [0,1])
  grid_price[t]             [BRL/kWh]    Tarifa TOU de importacao/referencia
  P_EV_load[t]              [kW]         Demanda inelastica de recarga VE

=============================================================================
VARIAVEIS DE DECISAO
=============================================================================
Investimento (primeiro estagio — escalares):
  P_pv_cap                  [kW]         Capacidade FV instalada
  E_bess_cap                [kWh]        Capacidade energetica do BESS
  P_trafo_cap               [kW]         Capacidade do transformador

Operacionais (segundo estagio — indexadas por t):
  P_pv_gen[t]               [kW]         Potencia FV gerada e injetada
  P_grid_import[t]          [kW]         Importacao da rede
  P_grid_export[t]          [kW]         Exportacao para a rede
  P_bess_charge[t]          [kW]         Potencia de carga do BESS
  P_bess_discharge[t]       [kW]         Potencia de descarga do BESS
  SOC[t]                    [kWh]        Estado de energia armazenado
  LoadShedding[t]           [kW]         Corte de carga (fixado a zero nesta versao)
  y_bess[t]                 {0,1}        Binaria de modo BESS: 1=carregando, 0=descarregando

=============================================================================
RESTRICOES (Nome Pyomo | Interpretacao | Ref. Artigo)
=============================================================================
  PVGenerationLimit         | P_pv_gen[t] <= irradiance_cf[t]*P_pv_cap          | Eq. de disponibilidade FV
  TrafoImportLimit          | P_grid_import[t] <= P_trafo_cap                    | Limite interface rede (importacao)
  TrafoExportLimit          | P_grid_export[t] <= allow_grid_export*P_trafo_cap  | Limite interface rede (exportacao)
  BESSChargePowerLimit      | P_bess_charge[t] <= c_rate_charge * E_bess_cap     | C-rate de carga
  BESSDischargePowerLimit   | P_bess_discharge[t] <= c_rate_discharge * E_bess_cap | C-rate de descarga
  BESSCapacityUpperBound    | E_bess_cap <= E_bess_cap_max                       | Limite de projeto / Big-M anchor
  PVCapacityUpperBound      | P_pv_cap <= P_pv_cap_max                           | Limite de projeto FV
  TrafoCapacityUpperBound   | P_trafo_cap <= P_trafo_cap_max                     | Limite de projeto trafo
  BESSChargeModeMILP        | P_bess_charge[t] <= M * y_bess[t]                  | Big-M: y=1 permite carga
  BESSDischargeModeMILP     | P_bess_discharge[t] <= M * (1-y_bess[t])           | Big-M: y=0 permite descarga
  SOCMin                    | SOC[t] >= soc_min_frac * E_bess_cap                | Janela segura SOC (minimo)
  SOCMax                    | SOC[t] <= soc_max_frac * E_bess_cap                | Janela segura SOC (maximo)
  SOCBalance                | dinamica recursiva linear com eta_charge/discharge  | Conservacao de energia BESS
  TerminalSOC               | SOC[24] == soc_initial_frac * E_bess_cap           | Periodicidade (dia representativo)
  EnergyBalance             | FV + Import + Descarga = Carga_VE - Shedding       | Balanco nodal (inspirado Eq. 483 do artigo — verificar numeracao na versao final)
  NoLoadShedding            | LoadShedding[t] == 0                               | Servico ininterrupto (Bolsa #7)

=============================================================================
FUNCAO OBJETIVO
=============================================================================
  Forma simplificada  (use_article_like_objective = 0):
    max  operational_days * (Rev_EV + Rev_export - Cost_import) - CAPEX_total
    [BRL]

  Forma artigo-like   (use_article_like_objective = 1):
    max  operational_days * (Rev_EV + Rev_export - Cost_import)
         - (CRF_pv*capex_pv*P_pv_cap + CRF_bess*capex_bess*E_bess_cap + ...)
         - (om_pv*P_pv_cap + om_bess*E_bess_cap + om_trafo*P_trafo_cap)
    [BRL/ano]

  Nota: como P_EV_load e parametro exogeno, a receita de recarga VE e
  "quase constante" em relacao as decisoes de operacao — as variaveis de
  decisao atuam principalmente na minimizacao do custo liquido de suprimento
  e no dimensionamento otimo de ativos.

=============================================================================
ASSUNCOES / LIMITACOES
=============================================================================
  - Horizonte de 24h representativo (um dia tipico); sazonalidade nao captada.
  - Demanda VE (P_EV_load) tratada como inelastica e deterministicamente conhecida.
  - Sem degradacao de BESS ao longo do dia (SOC ideal, sem envelhecimento).
  - Exportacao de energia pode ser proibida via allow_grid_export = 0.
  - Load shedding mantido como variavel para rastreabilidade, mas fixado a zero.
  - Linearizacao Big-M usa E_bess_cap_max como M para nao-simultaneidade BESS.

=============================================================================
REQUISITOS DE EXECUCAO
=============================================================================
  Python  >= 3.9
  Pyomo   >= 6.10
  Solver  : Gurobi (padrao) — ver main() para alternativas CBC/GLPK.
  Dados   : arquivo .dat com todos os parametros listados acima (ver dados_exemplo.dat).
  Saida   : relatorio_saida.txt gerado por write_report().
"""


def build_model() -> AbstractModel:
    """Constroi e retorna o AbstractModel Pyomo da microrrede do eletroposto.

    Entradas (via arquivo .dat passado a create_instance):
        Todos os parametros escalares e series horarias descritos na docstring
        do modulo (delta_t, tariff_ev, capex_*, crf_*, eta_*, soc_*, c_rate_*,
        E_bess_cap_max, P_pv_cap_max, P_trafo_cap_max, irradiance_cf[t],
        grid_price[t], P_EV_load[t], use_article_like_objective, etc.).

    Saidas:
        AbstractModel com:
          - Conjunto T (horizonte horario 1..24)
          - Todos os Param, Var, Constraint e Objective documentados no modulo
          - Pronto para receber dados via model.create_instance(data_file)
    """
    model = AbstractModel()


    # Horizonte horario.
    # Interpretacao fisica: discretiza a operacao da microrrede em 24 intervalos,
    # usualmente associados a 24 horas tipicas de um dia representativo.
    # Interpretacao economica: essa discretizacao permite calcular receitas e custos
    # por periodo tarifario, capturando arbitragem temporal de energia.
    # Interpretacao de modelagem: RangeSet define o indice temporal do problema
    # deterministico de programacao matematica, base para todas as variaveis e
    # restricoes acopladas no tempo (especialmente SOC do BESS).
    model.T = RangeSet(1, 24)

    # Parametros economicos.
    # - delta_t converte potencia (kW) em energia (kWh) no periodo.
    # - operational_days_equivalent anualiza a operacao diaria representativa.
    # - tariff_ev e o preco de venda do servico de recarga ao usuario final.
    # - export_price_factor reduz a remuneracao da exportacao em relacao ao preco
    #   de compra da rede (mecanismo de compensacao/mercado menos favoravel).
    # - use_article_like_objective atua como seletor continuo entre duas funcoes
    #   objetivo lineares; na pratica, usar 0 ou 1 preserva interpretacao clara.
    model.delta_t = Param(within=NonNegativeReals, default=1.0)  # horas
    model.operational_days_equivalent = Param(within=NonNegativeReals, default=365.0)
    model.tariff_ev = Param(within=NonNegativeReals)  # BRL/kWh
    model.export_price_factor = Param(within=NonNegativeReals, default=0.7)
    model.allow_grid_export = Param(within=NonNegativeReals, default=1.0)
    model.use_article_like_objective = Param(within=NonNegativeReals, default=0.0)

    # CAPEX (BRL por unidade de capacidade).
    # Interpretacao fisica: cada decisao de investimento dimensiona um ativo real
    # (arranjo PV em kW, BESS em kWh, transformador em kW).
    # Interpretacao economica: representa desembolso inicial para habilitar a
    # operacao da estacao de recarga e a flexibilidade energetica.
    # Interpretacao de modelagem: custo linear por capacidade instalada, sem
    # economias de escala, preservando problema MILP/LP linear.
    model.capex_pv_kw = Param(within=NonNegativeReals)
    model.capex_bess_kwh = Param(within=NonNegativeReals)
    model.capex_trafo_kw = Param(within=NonNegativeReals)

    # Parametros de anualizacao (versao mais proxima do artigo).
    # CRF converte CAPEX em fluxo anual equivalente (custo de capital), enquanto
    # O&M adiciona custo operacional fixo por capacidade instalada.
    # Em termos de planejamento, aproxima comparacao entre beneficio anual e
    # encargo anualizado dos ativos, evitando mistura direta de fluxos e estoque.
    model.crf_pv = Param(within=NonNegativeReals, default=0.0)
    model.crf_bess = Param(within=NonNegativeReals, default=0.0)
    model.crf_trafo = Param(within=NonNegativeReals, default=0.0)
    model.om_pv_kw_year = Param(within=NonNegativeReals, default=0.0)
    model.om_bess_kwh_year = Param(within=NonNegativeReals, default=0.0)
    model.om_trafo_kw_year = Param(within=NonNegativeReals, default=0.0)

    # Parametros tecnicos BESS.
    # Interpretacao fisica:
    # - eta_charge/eta_discharge modelam perdas eletroquimicas e de conversao.
    # - limites SOC evitam sobrecarga e descarga profunda, preservando vida util.
    # - c-rate relaciona potencia maxima com energia instalada.
    # Interpretacao de modelagem:
    # - todos entram linearmente, mantendo formulacao tratavel por solver MILP.
    # - E_bess_cap_max e um limite exogeno de projeto usado para Big-M robusto.
    model.eta_charge = Param(within=NonNegativeReals)
    model.eta_discharge = Param(within=NonNegativeReals)
    model.soc_min_frac = Param(within=NonNegativeReals)
    model.soc_max_frac = Param(within=NonNegativeReals)
    model.soc_initial_frac = Param(within=NonNegativeReals)
    model.c_rate_charge = Param(within=NonNegativeReals)
    model.c_rate_discharge = Param(within=NonNegativeReals)
    model.E_bess_cap_max = Param(within=NonNegativeReals, default=2000.0)
    model.P_pv_cap_max = Param(within=NonNegativeReals, default=1000.0)
    model.P_trafo_cap_max = Param(within=NonNegativeReals, default=500.0)

    # Series horarias.
    # irradiance_cf: recurso renovavel exogeno por hora.
    # grid_price: sinal economico temporal para importacao/exportacao.
    # P_EV_load: demanda inelastica de recarga a ser atendida sem interrupcao.
    model.irradiance_cf = Param(model.T, within=NonNegativeReals)
    model.grid_price = Param(model.T, within=NonNegativeReals)
    model.P_EV_load = Param(model.T, within=NonNegativeReals)

    # Variaveis de investimento (primeiro estagio implito).
    # Essas variaveis sintetizam decisoes de planejamento da infraestrutura e
    # acoplam todos os periodos operacionais, pois capacidade e compartilhada no dia.
    model.P_pv_cap = Var(within=NonNegativeReals)  # kW
    model.E_bess_cap = Var(within=NonNegativeReals)  # kWh
    model.P_trafo_cap = Var(within=NonNegativeReals)  # kW

    # Variaveis operacionais (segundo estagio de despacho horario).
    # Interpretacao fisica: fluxos de potencia e estado energetico da bateria.
    # Interpretacao economica: cada fluxo participa de receitas/custos no objetivo.
    # Interpretacao de modelagem: y_bess torna explicita a logica disjuntiva
    # carga-versus-descarga via linearizacao Big-M (classe MILP).
    model.P_pv_gen = Var(model.T, within=NonNegativeReals)  # kW
    model.P_grid_import = Var(model.T, within=NonNegativeReals)  # kW
    model.P_grid_export = Var(model.T, within=NonNegativeReals)  # kW
    model.P_bess_charge = Var(model.T, within=NonNegativeReals)  # kW
    model.P_bess_discharge = Var(model.T, within=NonNegativeReals)  # kW
    model.SOC = Var(model.T, within=NonNegativeReals)  # kWh
    model.LoadShedding = Var(model.T, within=NonNegativeReals)  # kW
    model.y_bess = Var(model.T, within=Binary)

    # ---------------------------------------------------------------------
    # BLOCO DE RESTRICOES
    # ---------------------------------------------------------------------
    # Em leitura de sistema eletrico, as restricoes reproduzem:
    # - disponibilidade de recurso (PV),
    # - limites de interface com rede (transformador),
    # - limites eletroenergeticos do BESS,
    # - conservacao de energia por periodo,
    # - requisito de continuidade de atendimento da carga de VE.
    # Em leitura de otimizacao, esse conjunto define o poliedro viavel do MILP.

    # limite de geracao fotovoltaica por fator de capacidade
    # Eq. de disponibilidade PV.
    # Fisico: potencia PV injetada nao pode exceder potencia nominal instalada
    # multiplicada pelo fator horario de irradiancia.
    # Economico: investir em mais PV amplia teto de geracao e reduz dependencia de
    # compra da rede em horas solares.
    # Modelagem: restricao linear de acoplamento entre variavel de investimento
    # (P_pv_cap) e variavel de operacao (P_pv_gen[t]).
    def pv_generation_limit_rule(m, t):
        return m.P_pv_gen[t] <= m.P_pv_cap * m.irradiance_cf[t]

    model.PVGenerationLimit = Constraint(model.T, rule=pv_generation_limit_rule)

    # Limites de transformador (importacao/exportacao).
    # Fisico: a interface com a rede possui capacidade aparente contratada/instalada
    # que limita fluxo em qualquer sentido.
    # Economico: maior trafo aumenta opcao de arbitragem e seguranca de suprimento,
    # mas cobra CAPEX adicional.
    # Modelagem: limite linear por periodo para importacao e exportacao.
    def trafo_import_limit_rule(m, t):
        return m.P_grid_import[t] <= m.P_trafo_cap

    def trafo_export_limit_rule(m, t):
        return m.P_grid_export[t] <= m.P_trafo_cap * m.allow_grid_export

    model.TrafoImportLimit = Constraint(model.T, rule=trafo_import_limit_rule)
    model.TrafoExportLimit = Constraint(model.T, rule=trafo_export_limit_rule)

    # Limites de potencia de carga/descarga do BESS.
    # Fisico: conversores e a propria quimica impõem taxa maxima de carga/descarga
    # proporcional ao tamanho energetico instalado (c-rate).
    # Economico: baterias maiores permitem maiores rampas de arbitragem, potencialmente
    # aumentando captura de spread tarifario.
    # Modelagem: vinculacao linear P <= c_rate * E_cap.
    def bess_charge_power_limit_rule(m, t):
        return m.P_bess_charge[t] <= m.c_rate_charge * m.E_bess_cap

    def bess_discharge_power_limit_rule(m, t):
        return m.P_bess_discharge[t] <= m.c_rate_discharge * m.E_bess_cap

    model.BESSChargePowerLimit = Constraint(model.T, rule=bess_charge_power_limit_rule)
    model.BESSDischargePowerLimit = Constraint(model.T, rule=bess_discharge_power_limit_rule)

    # -------------------------------------------------------------------------
    # Limite superior fisico da capacidade de BESS — ancora do Big-M.
    # -------------------------------------------------------------------------
    # Nome Pyomo    : BESSCapacityUpperBound
    # Interpretacao : Impede que o solver expanda a bateria alem do limite de
    #                 projeto E_bess_cap_max (fisicamente justificado por restricoes
    #                 de espaco, conexao ou orcamento disponivel).
    # Papel no MILP : E_bess_cap_max serve como o valor M das restricoes
    #                 BESSChargeModeMILP/BESSDischargeModeMILP (ver abaixo).
    #                 Um M derivado deste limite e seguro (nao poda solucoes viaveis)
    #                 e numericamente melhor do que uma constante arbitraria grande.
    # Diferenca art.: Parametro de projeto exogeno; no artigo pode ser fixo ou variavel
    #                 de cenario.
    # -------------------------------------------------------------------------
    def bess_capacity_upper_bound_rule(m):
        return m.E_bess_cap <= m.E_bess_cap_max
    model.BESSCapacityUpperBound = Constraint(rule=bess_capacity_upper_bound_rule)

    # Limites de capacidade de investimento para manter o problema fisicamente
    # plausivel e evitar expansao ilimitada de ativos.
    def pv_capacity_upper_bound_rule(m):
        return m.P_pv_cap <= m.P_pv_cap_max

    def trafo_capacity_upper_bound_rule(m):
        return m.P_trafo_cap <= m.P_trafo_cap_max

    model.PVCapacityUpperBound = Constraint(rule=pv_capacity_upper_bound_rule)
    model.TrafoCapacityUpperBound = Constraint(rule=trafo_capacity_upper_bound_rule)

    # -------------------------------------------------------------------------
    # Nao simultaneidade de carga/descarga (MILP linearizado via Big-M).
    # -------------------------------------------------------------------------
    # Nome Pyomo    : BESSChargeModeMILP / BESSDischargeModeMILP
    # Interpretacao : Em cada hora t, a bateria opera em modo carga OU descarga;
    #                 nunca simultaneamente (evita ciclo artificial sem significado fisico).
    # Equacao artigo: restricao disjuntiva padrao para modelagem de BESS em MILP.
    # Diferenca impl: Big-M derivado de E_bess_cap_max (limite fisico de projeto),
    #                 nao de constante arbitrariamente grande.
    #
    # Mecanismo:
    #   y_bess[t] = 1  ->  permite carga  (P_bess_charge[t] <= M)
    #                       bloqueia descarga (P_bess_discharge[t] <= 0)
    #   y_bess[t] = 0  ->  bloqueia carga (P_bess_charge[t] <= 0)
    #                       permite descarga (P_bess_discharge[t] <= M)
    #   onde M = c_rate * E_bess_cap_max.
    #
    # Escolha do Big-M:
    #   M = c_rate * E_bess_cap_max e suficientemente alto para nao cortar nenhuma
    #   solucao viavel (ja que P_bess_charge <= c_rate * E_bess_cap <= c_rate * E_bess_cap_max),
    #   mas fisicamente justificado — evita degradacao numerica da relaxacao LP.
    # -------------------------------------------------------------------------

    def bess_charge_limit_milp(m, t):
        return m.P_bess_charge[t] <= m.c_rate_charge * m.E_bess_cap_max * m.y_bess[t]

    def bess_discharge_limit_milp(m, t):
        return m.P_bess_discharge[t] <= m.c_rate_discharge * m.E_bess_cap_max * (1 - m.y_bess[t])

    model.BESSChargeModeMILP = Constraint(model.T, rule=bess_charge_limit_milp)
    model.BESSDischargeModeMILP = Constraint(model.T, rule=bess_discharge_limit_milp)

    # Limites de SOC.
    # Fisico: janela operacional segura da bateria (reserva minima e teto maximo).
    # Economico: manter SOC minimo reduz risco de indisponibilidade para carga critica.
    # Modelagem: desigualdades lineares dependentes da capacidade decidida.
    def soc_min_rule(m, t):
        return m.SOC[t] >= m.soc_min_frac * m.E_bess_cap

    def soc_max_rule(m, t):
        return m.SOC[t] <= m.soc_max_frac * m.E_bess_cap

    model.SOCMin = Constraint(model.T, rule=soc_min_rule)
    model.SOCMax = Constraint(model.T, rule=soc_max_rule)

    # Dinamica do SOC.
    # Fisico: conservacao de energia no armazenamento, com perdas na carga/descarga.
    # Economico: desloca energia no tempo para aproveitar diferencas de preco e
    # reduzir importacao em horarios caros.
    # Modelagem: equacoes lineares recursivas acoplam periodos consecutivos,
    # tornando o problema intertemporal.
    def soc_balance_rule(m, t):
        if t == m.T.first():
            return m.SOC[t] == m.soc_initial_frac * m.E_bess_cap + m.delta_t * (
                m.eta_charge * m.P_bess_charge[t] - m.P_bess_discharge[t] / m.eta_discharge
            )
        t_prev = m.T.prev(t)
        return m.SOC[t] == m.SOC[t_prev] + m.delta_t * (
            m.eta_charge * m.P_bess_charge[t] - m.P_bess_discharge[t] / m.eta_discharge
        )

    model.SOCBalance = Constraint(model.T, rule=soc_balance_rule)

    # Condicao ciclica: SOC final igual ao inicial.
    # Fisico: evita "esvaziar" ou "encher" artificialmente a bateria no ultimo
    # periodo para inflar resultado de um dia representativo.
    # Economico: assegura comparabilidade interdiaria e neutralidade energetica do
    # estado final no calculo anualizado.
    # Modelagem: fecha o horizonte com restricao terminal de consistencia.
    def terminal_soc_rule(m):
        return m.SOC[m.T.last()] == m.soc_initial_frac * m.E_bess_cap

    model.TerminalSOC = Constraint(rule=terminal_soc_rule)

    # -------------------------------------------------------------------------
    # Balanco de energia no barramento equivalente da microrrede.
    # -------------------------------------------------------------------------
    # Nome Pyomo    : EnergyBalance
    # Interpretacao : Conservacao de potencia em cada hora — todas as fontes
    #                 devem igualar todos os usos (incluindo carga/descarga BESS).
    #                 Fontes: P_pv_gen + P_grid_import + P_bess_discharge
    #                 Usos  : P_EV_load - LoadShedding + P_bess_charge + P_grid_export
    # Equacao artigo: inspirada na Eq. 483 do artigo de referencia (balanco nodal).
    #                 Verificar numeracao exata na versao final do artigo.
    # Diferenca impl: load shedding fixado a zero (ver NoLoadShedding) — estrutura
    #                 mantida para facilitar extensao futura com demanda flexivel.
    # -------------------------------------------------------------------------
    def energy_balance_rule(m, t):
        return (
            m.P_pv_gen[t] + m.P_grid_import[t] + m.P_bess_discharge[t]
            == m.P_EV_load[t] - m.LoadShedding[t] + m.P_bess_charge[t] + m.P_grid_export[t]
        )

    model.EnergyBalance = Constraint(model.T, rule=energy_balance_rule)

    # Restricao de continuidade de servico: sem load shedding.
    # Fisico: impõe atendimento integral da demanda de recarga em todas as horas.
    # Economico: representa compromisso de qualidade de servico (Bolsa #7), sem
    # aceitar perda de receita por demanda nao atendida.
    # Modelagem: LoadShedding e mantida no modelo para rastreabilidade/expansao
    # futura, mas fixada a zero nesta versao.
    def no_shedding_rule(m, t):
        return m.LoadShedding[t] == 0.0

    model.NoLoadShedding = Constraint(model.T, rule=no_shedding_rule)

    # -------------------------------------------------------------------------
    # Funcao objetivo: maximizacao de desempenho economico anualizado.
    # -------------------------------------------------------------------------
    # Nome Pyomo  : Obj (sense=maximize)
    # Interpretacao economica:
    #   - Receita principal : tariff_ev * P_EV_load[t] * delta_t  (BRL/h -> BRL/dia)
    #     Nota: como P_EV_load e parametro exogeno (demanda inelastica conhecida),
    #     a receita de recarga VE e "quase constante" — as decisoes do solver atuam
    #     principalmente na minimizacao do custo liquido de suprimento e no
    #     dimensionamento otimo dos ativos.
    #   - Receita secundaria: export_price_factor * grid_price[t] * P_grid_export[t]
    #   - Custo principal   : grid_price[t] * P_grid_import[t]
    #
    # Anualizacao:
    #   operational_days_equivalent converte o lucro de um dia representativo
    #   em valor anual equivalente, permitindo subtrair o custo de investimento
    #   (que e um desembolso ou encargo anual) na mesma unidade monetaria.
    #
    # Forma simplificada (use_article_like_objective = 0):
    #   Subtrai CAPEX total de uma vez — adequado para analise de payback simples.
    #   Unidade: BRL (fluxo anual menos estoque de investimento).
    #
    # Forma artigo-like (use_article_like_objective = 1):
    #   Subtrai CAPEX anualizado via CRF (Capital Recovery Factor) e O&M anual.
    #   CRF converte o investimento de uma vez em fluxo anual equivalente,
    #   respeitando valor do dinheiro no tempo (taxa de desconto embutida no CRF).
    #   Unidade: BRL/ano — comparacao homogenea entre beneficio e encargo anuais.
    #
    # Selecao: combinacao convexa linear pelos parametros 0/1; preserva estrutura
    # linear do MILP sem introducao de nao-linearidades.
    # -------------------------------------------------------------------------
    def objective_rule(m):
        daily_revenue_ev = sum(m.tariff_ev * m.P_EV_load[t] * m.delta_t for t in m.T)
        daily_revenue_export = sum(
            m.export_price_factor * m.grid_price[t] * m.P_grid_export[t] * m.delta_t for t in m.T
        )
        daily_cost_import = sum(m.grid_price[t] * m.P_grid_import[t] * m.delta_t for t in m.T)

        annual_operational_profit = m.operational_days_equivalent * (
            daily_revenue_ev + daily_revenue_export - daily_cost_import
        )

        capex_total = (
            m.capex_pv_kw * m.P_pv_cap
            + m.capex_bess_kwh * m.E_bess_cap
            + m.capex_trafo_kw * m.P_trafo_cap
        )

        annualized_investment = (
            m.crf_pv * m.capex_pv_kw * m.P_pv_cap
            + m.crf_bess * m.capex_bess_kwh * m.E_bess_cap
            + m.crf_trafo * m.capex_trafo_kw * m.P_trafo_cap
        )

        annual_om = (
            m.om_pv_kw_year * m.P_pv_cap
            + m.om_bess_kwh_year * m.E_bess_cap
            + m.om_trafo_kw_year * m.P_trafo_cap
        )

        simplified_objective = annual_operational_profit - capex_total
        article_like_objective = annual_operational_profit - annualized_investment - annual_om

        return (1 - m.use_article_like_objective) * simplified_objective + (
            m.use_article_like_objective * article_like_objective
        )

    model.Obj = Objective(rule=objective_rule, sense=maximize)

    return model


def write_report(instance, report_path: Path) -> None:
    """Gera relatorio textual da solucao otimizada em report_path.

    Formato do relatorio:
        1. Cabecalho identificador.
        2. Capacidades otimizadas (P_pv_cap, E_bess_cap, P_trafo_cap).
        3. Valor da funcao objetivo ativa e modo selecionado.
        4. Status de exportacao para a rede.
        5. Comparativo lado a lado dos dois modos de objetivo (simplificado e
           artigo-like), calculados sobre a mesma solucao para referencia.
        6. Tabela CSV com despacho horario (24 linhas):
           h, PV_gen, Grid_import, Grid_export, BESS_charge, BESS_discharge,
           SOC, EV_load, LoadShedding  — todos em kW (potencia) exceto SOC (kWh).

    Args:
        instance: instancia Pyomo concreta apos resolucao pelo solver.
        report_path: Path do arquivo .txt a ser criado/sobrescrito.
    """
    objective_value = value(instance.Obj)

    annual_revenue_ev = sum(
        value(instance.tariff_ev) * value(instance.P_EV_load[t]) * value(instance.delta_t)
        for t in instance.T
    ) * value(instance.operational_days_equivalent)
    annual_revenue_export = sum(
        value(instance.export_price_factor)
        * value(instance.grid_price[t])
        * value(instance.P_grid_export[t])
        * value(instance.delta_t)
        for t in instance.T
    ) * value(instance.operational_days_equivalent)
    annual_cost_import = sum(
        value(instance.grid_price[t]) * value(instance.P_grid_import[t]) * value(instance.delta_t)
        for t in instance.T
    ) * value(instance.operational_days_equivalent)
    annual_operational_profit = annual_revenue_ev + annual_revenue_export - annual_cost_import

    capex_total = (
        value(instance.capex_pv_kw) * value(instance.P_pv_cap)
        + value(instance.capex_bess_kwh) * value(instance.E_bess_cap)
        + value(instance.capex_trafo_kw) * value(instance.P_trafo_cap)
    )
    annualized_investment = (
        value(instance.crf_pv) * value(instance.capex_pv_kw) * value(instance.P_pv_cap)
        + value(instance.crf_bess) * value(instance.capex_bess_kwh) * value(instance.E_bess_cap)
        + value(instance.crf_trafo) * value(instance.capex_trafo_kw) * value(instance.P_trafo_cap)
    )
    annual_om = (
        value(instance.om_pv_kw_year) * value(instance.P_pv_cap)
        + value(instance.om_bess_kwh_year) * value(instance.E_bess_cap)
        + value(instance.om_trafo_kw_year) * value(instance.P_trafo_cap)
    )

    objective_simplified = annual_operational_profit - capex_total
    objective_article_like = annual_operational_profit - annualized_investment - annual_om

    with report_path.open("w", encoding="utf-8") as f:
        # Estrutura textual deterministicamente reproduzivel, util para comparacao
        # de cenarios e posterior ingestao por scripts de analise.
        f.write("RELATORIO DE OTIMIZACAO - MICRORREDE RODOVIA\n")
        f.write("=" * 72 + "\n\n")

        f.write("Capacidades otimizadas:\n")
        f.write(f"- PV (kW): {value(instance.P_pv_cap):.3f}\n")
        f.write(f"- BESS (kWh): {value(instance.E_bess_cap):.3f}\n")
        f.write(f"- Transformador (kW): {value(instance.P_trafo_cap):.3f}\n\n")

        f.write(f"Valor da funcao objetivo ativa (BRL): {objective_value:,.2f}\n")
        f.write(f"Modo objetivo (0=simplificado, 1=artigo): {value(instance.use_article_like_objective):.0f}\n\n")

        export_blocked = value(instance.allow_grid_export) < 0.5
        if export_blocked:
            f.write("*** EXPORTACAO BLOQUEADA NO CENARIO ***\n\n")
        else:
            f.write("Exportacao para rede: habilitada no cenario.\n\n")

        f.write("Comparativo lado a lado (avaliado na solucao otimizada):\n")
        f.write(f"- Objetivo simplificado (operacional anual - CAPEX): {objective_simplified:,.2f} BRL\n")
        f.write(
            "- Objetivo artigo-like (operacional anual - CAPEX anualizado CRF - O&M): "
            f"{objective_article_like:,.2f} BRL\n"
        )
        f.write(f"- Lucro operacional anual: {annual_operational_profit:,.2f} BRL\n")
        f.write(f"- CAPEX total (unico): {capex_total:,.2f} BRL\n")
        f.write(f"- CAPEX anualizado (CRF): {annualized_investment:,.2f} BRL/ano\n")
        f.write(f"- O&M anual: {annual_om:,.2f} BRL/ano\n\n")

        f.write("Despacho horario (kW / kWh):\n")
        f.write(
            "h,PV_gen,Grid_import,Grid_export,BESS_charge,BESS_discharge,SOC,EV_load,LoadShedding\n"
        )

        for t in instance.T:
            f.write(
                f"{t},"
                f"{value(instance.P_pv_gen[t]):.4f},"
                f"{value(instance.P_grid_import[t]):.4f},"
                f"{value(instance.P_grid_export[t]):.4f},"
                f"{value(instance.P_bess_charge[t]):.4f},"
                f"{value(instance.P_bess_discharge[t]):.4f},"
                f"{value(instance.SOC[t]):.4f},"
                f"{value(instance.P_EV_load[t]):.4f},"
                f"{value(instance.LoadShedding[t]):.4f}\n"
            )


def main() -> None:
    # Encapsula fluxo de execucao do experimento: leitura de dados, resolucao da
    # MILP e emissao de relatorio tecnico-economico.
    base_dir = Path(__file__).resolve().parent
    data_file = base_dir / "dados_exemplo.dat"
    report_file = base_dir / "relatorio_saida.txt"

    model = build_model()
    instance = model.create_instance(str(data_file))

    # Observacao de implementacao: o backend "gurobi" usa a interface de solver
    # esperada pelo Pyomo. Validacao explicita evita falhas silenciosas de ambiente.
    solver = SolverFactory("gurobi")
    if not solver.available(False):
        raise RuntimeError(
            "Solver Gurobi indisponivel via 'gurobi'. Verifique instalacao/licenca do Gurobi."
        )

    results = solver.solve(instance, tee=False)

    # Checagem de qualidade de solucao: status e termination condition precisam
    # confirmar resolucao valida (otima global ou local conforme backend).
    status_ok = results.solver.status == SolverStatus.ok
    term_ok = results.solver.termination_condition in {
        TerminationCondition.optimal,
        TerminationCondition.locallyOptimal,
    }

    if not (status_ok and term_ok):
        raise RuntimeError(
            "Falha na otimizacao. "
            f"Status: {results.solver.status}; "
            f"Termination: {results.solver.termination_condition}"
        )

    write_report(instance, report_file)
    print(f"Relatorio gerado com sucesso em: {report_file}")


if __name__ == "__main__":
    main()
