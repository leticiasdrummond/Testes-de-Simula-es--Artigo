"""
advanced_features — Extensões Avançadas de Modelagem para o Eletroposto PV-BESS-Rede
======================================================================================

Cada submódulo implementa uma funcionalidade de modelagem independente que pode ser
usada isoladamente ou combinada com o modelo base (main.py / modelo_abstract_artigo_*.py).

Módulos disponíveis
-------------------
feature_01_progressive_hedging
    Programação estocástica de dois estágios com Progressive Hedging (não-antecipação).

feature_02_dod_degradation
    Degradação de bateria dependente da profundidade de descarga (DoD-aware aging).

feature_03_smart_charging
    Carregamento inteligente V1G com janelas de flexibilidade e custos de desconforto.

feature_04_aneel_tariff
    Gestão de demanda contratada com tarifa horo-sazonal ANEEL (componente de demanda).

feature_05_reliability_metrics
    Cálculo pós-otimização de EENS, LOLP e índice SAIDI equivalente.

feature_06_multiday
    Horizonte multi-dia com continuidade de SOC entre dias e redução de cenários.

feature_07_pareto_epsilon
    Fronteira de Pareto CAPEX × EENS via método ε-constraint iterativo.

feature_08_robust_gamma
    Otimização robusta Γ (Bertsimas & Sim) para incerteza em irradiância e carga VE.

feature_09_emissions
    Modelo de emissões de CO₂ com fator de emissão horário do ONS e créditos de carbono.

feature_10_benders
    Decomposição de Benders clássica: master de investimento + subproblemas por cenário.
"""
