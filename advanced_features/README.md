# Advanced Modeling Features — Eletroposto PV-BESS-Rede

Este diretório contém as **10 extensões avançadas de modelagem** para o modelo de
otimização do eletroposto fotovoltaico com armazenamento em bateria e integração
à rede elétrica. Cada módulo é independente e pode ser usado isoladamente ou
combinado com o modelo base (`main.py`).

---

## Sumário

| Módulo | Feature | Impacto | Esforço |
|:---|:---|:---|:---|
| `feature_01_progressive_hedging.py` | Programação Estocástica (Progressive Hedging) | 🔴 Alto | 🟡 Médio |
| `feature_02_dod_degradation.py` | Degradação de Bateria DoD-aware | 🟡 Médio | 🟡 Médio |
| `feature_03_smart_charging.py` | Carregamento Inteligente V1G | 🟡 Médio | 🟢 Baixo |
| `feature_04_aneel_tariff.py` | Tarifa Horo-Sazonal ANEEL | 🔴 Alto | 🟢 Baixo |
| `feature_05_reliability_metrics.py` | Métricas SAIDI/EENS | 🟡 Médio | 🟢 Baixo |
| `feature_06_multiday.py` | Horizonte Multi-dia | 🟡 Médio | 🟡 Médio |
| `feature_07_pareto_epsilon.py` | Fronteira de Pareto (ε-constraint) | 🔴 Alto | 🟢 Baixo |
| `feature_08_robust_gamma.py` | Robustez Γ (Bertsimas & Sim) | 🟢 Avançado | 🔴 Alto |
| `feature_09_emissions.py` | Emissões de CO₂ e Créditos de Carbono | 🟡 Médio | 🟢 Baixo |
| `feature_10_benders.py` | Decomposição de Benders | 🟢 Avançado | 🔴 Alto |

---

## Instalação de Dependências

```bash
# Dependências base (já necessárias para main.py)
pip install pyomo

# Para Feature 6 (redução de cenários k-means)
pip install scikit-learn numpy

# Para plots (Features 2, 5, 7)
pip install matplotlib numpy

# Solver CBC (livre) — recomendado para testes
conda install -c conda-forge coincbc
# ou
pip install cylp

# Solver Gurobi (comercial, licença acadêmica gratuita)
# Ver: https://www.gurobi.com/academia/academic-program-and-licenses/
```

---

## Uso Rápido

### Feature 7 — Fronteira de Pareto (maior impacto, menor esforço)

```python
from advanced_features.feature_07_pareto_epsilon import run_pareto_analysis

result = run_pareto_analysis(
    n_epsilon_points=10,
    solver_name="cbc",
    verbose=True,
    save_plot="pareto_capex_eens.png",
)
result.print_summary()
```

### Feature 4 — Tarifa ANEEL

```python
from advanced_features.feature_04_aneel_tariff import (
    ANEELTariffConfig, build_model_aneel, compute_aneel_bill
)

tariff = ANEELTariffConfig.enel_sp_reference()
model = build_model_aneel(tariff)

# Calcular fatura para um perfil de importação
bill = compute_aneel_bill(
    grid_import_profile={t: 80.0 for t in range(1, 25)},
    tariff=tariff,
    P_contracted=100.0,   # kW contratados na ponta
    P_contracted_fp=80.0, # kW contratados fora da ponta
)
print(f"Total fatura: {bill['total_BRL_mes']:.2f} BRL/mês")
```

### Feature 2 — Degradação DoD

```python
from advanced_features.feature_02_dod_degradation import (
    PWLDegradationCurve, sensitivity_table
)

curve = PWLDegradationCurve.lifepo4_default()
tabela = sensitivity_table(curve, capex_per_kwh=700.0)
for row in tabela:
    print(f"DoD={row['DoD']:.0%} → c_deg={row['c_deg_BRL_kWh']:.4f} BRL/kWh")
```

### Feature 5 — Métricas EENS/SAIDI

```python
from advanced_features.feature_05_reliability_metrics import (
    compute_reliability_from_profiles, plot_pareto_capex_eens
)

report = compute_reliability_from_profiles(
    load_profiles={"normal": {...}, "falha": {...}},
    shed_profiles={"normal": {t: 0 for t in range(1,25)}, "falha": {...}},
    # ... demais perfis ...
    probabilities={"normal": 0.90, "falha": 0.10},
)
report.print_summary()
```

### Feature 9 — Emissões de CO₂

```python
from advanced_features.feature_09_emissions import (
    ONSEmissionFactors, EmissionsModel
)

factors = ONSEmissionFactors.brazil_national_2023()
model = EmissionsModel(factors, carbon_price_brl_ton=80.0)
report = model.compute_annual_report(
    grid_import_profile={t: 80.0 for t in range(1, 25)},
    pv_generation_profile={t: max(0, (t-6)*10) if 6<=t<=12 else 0 for t in range(1,25)},
    ev_load_profile={t: 100.0 for t in range(1, 25)},
)
report.print_summary()
```

---

## Execução dos Demos

Cada módulo pode ser executado diretamente para demonstração:

```bash
# Feature 2 — Tabela de degradação DoD
python -m advanced_features.feature_02_dod_degradation

# Feature 3 — Análise de smart charging (sem solver)
python -m advanced_features.feature_03_smart_charging

# Feature 4 — Fatura ANEEL
python -m advanced_features.feature_04_aneel_tariff

# Feature 5 — Métricas de confiabilidade (sem solver)
python -m advanced_features.feature_05_reliability_metrics

# Feature 6 — Horizonte multi-dia
python -m advanced_features.feature_06_multiday

# Feature 7 — Fronteira de Pareto (requer CBC ou Gurobi)
python -m advanced_features.feature_07_pareto_epsilon

# Feature 8 — Robustez Γ
python -m advanced_features.feature_08_robust_gamma

# Feature 9 — Emissões CO₂ (sem solver)
python -m advanced_features.feature_09_emissions

# Feature 10 — Benders (requer CBC ou Gurobi)
python -m advanced_features.feature_10_benders
```

---

## Descrição Técnica Detalhada

### Feature 1 — Progressive Hedging (Programação Estocástica)

Implementa o algoritmo de **Progressive Hedging** (Rockafellar & Wets, 1991) para
problemas estocásticos de dois estágios. A estrutura de cenários é organizada em
uma **árvore sazonal** (verão/inverno/intermediário), e as restrições de não-antecipação
são impostas via multiplicadores de Lagrange atualizados iterativamente.

**Formulação:**
- Primeiro estágio (não antecipatório): decisões de capacidade `(P_pv_cap, E_bess_cap, P_trafo_cap)`
- Segundo estágio (por cenário): despacho operacional
- Penalização PH: `w_s^T x_s + (ρ/2)||x_s - x̄||²`

### Feature 2 — Degradação DoD-aware

Substitui o parâmetro escalar `c_deg_bess` por uma **curva Piecewise Linear** de
ciclos de vida × DoD (Wang et al., 2014). O custo de degradação passa a ser
endógeno ao modelo, com variável auxiliar `SOC_min` e aproximação linear por partes.

**Curvas disponíveis:** LiFePO4, NMC.

### Feature 3 — Smart Charging V1G

Transforma `P_EV_load` de parâmetro fixo em **variável de decisão** com janelas de
flexibilidade `[P_nominal*(1-flex_down), P_nominal*(1+flex_up)]`. Inclui custo de
desconforto do usuário e restrição de energia total da sessão.

### Feature 4 — Tarifa ANEEL

Modela a estrutura tarifária brasileira Grupo A (TUSD-Energia + TUSD-Demanda),
com **demanda contratada** como variável de decisão e penalidade de ultrapassagem
(3× tarifa de demanda, conforme ANEEL RN 1000/2021).

**Referências disponíveis:** Enel SP, CEMIG, Light/Rio.

### Feature 5 — Métricas SAIDI/EENS

Calcula pós-otimização:
- **EENS** (Expected Energy Not Served) [kWh/ano]
- **LOLP** (Loss of Load Probability) [-]
- **LOLE** (Loss of Load Expectation) [h/ano]
- **SAIDI/SAIFI equivalentes** por sessão de recarga VE

Inclui função de plotagem da fronteira Pareto CAPEX × EENS.

### Feature 6 — Horizonte Multi-dia

Estende o horizonte de 24h para múltiplos dias representativos com:
- **Continuidade de SOC** entre dias (sem reset inter-dia)
- **Redução de cenários** via k-means (requer scikit-learn)
- **Pesos** proporcionais à frequência de cada tipo de dia

### Feature 7 — Pareto ε-constraint

Gera a **fronteira de Pareto** CAPEX × EENS via método ε-constraint (Mavrotas, 2009),
eliminando a subjetividade dos pesos ad-hoc. Cada ponto da fronteira corresponde a
um dimensionamento ótimo para um nível de confiabilidade diferente.

### Feature 8 — Robustez Γ (Bertsimas & Sim)

Implementa a **reformulação dual robusta** de Bertsimas & Sim (2004) com parâmetro
Γ ∈ [0, 24] controlando o conservadorismo. Aplica incerteza simultânea em:
- Irradiância solar: Δ_irr = `irr_uncertainty × irr_nominal`
- Demanda VE: Δ_ev = `ev_uncertainty × ev_nominal`

### Feature 9 — Emissões de CO₂

Calcula:
- Emissões de operação [kgCO₂/ano] usando **MEF horário do ONS**
- Emissões evitadas vs. rede sem FV/BESS e vs. frota a gasolina
- **Créditos de carbono** elegíveis [tCO₂/ano] e receita potencial [BRL/ano]

**Regiões:** Nacional, Sudeste, Nordeste.

### Feature 10 — Decomposição de Benders

Implementa o algoritmo clássico de **Benders Decomposition** (Benders, 1962):
- **Master problem**: decide capacidades de investimento com variável η (aproximação do lucro operacional)
- **Subproblemas** (LP): operação por cenário com investimento fixo
- **Cortes de otimalidade**: gerados iterativamente até convergência do gap LB/UB

Compatível com CBC, GLPK e Gurobi.

---

## Referências Bibliográficas

- Bertsimas & Sim (2004) "The Price of Robustness." Operations Research.
- Benders (1962) "Partitioning procedures for solving mixed-variables programming problems."
- Billinton & Allan (1996) "Reliability Evaluation of Power Systems." 2nd ed.
- Birge & Louveaux (2011) "Introduction to Stochastic Programming." 2nd ed. Springer.
- IEEE Std 1366 (2012) "Guide for Electric Power Distribution Reliability Indices."
- Mavrotas (2009) "Effective implementation of the ε-constraint method in MOMMP." Applied Mathematics.
- Rockafellar & Wets (1991) "Scenarios and Policy Aggregation in Optimization Under Uncertainty."
- Van Slyke & Wets (1969) "L-shaped linear programs with applications to optimal control."
- Wang et al. (2014) "Cycle-life model for graphite-LiFePO4 cells." J. Power Sources.
- ANEEL Resolução Normativa 1000/2021 — Condições gerais de fornecimento.
- MCiD/SEEG (2023) "Sistema de Estimativa de Emissões e Remoções de GEE."
- ONS (2023) "Fatores de Emissão para Estudos de Geração Distribuída."
