# Conteúdo central das modelagens (com data-versão)

Este documento consolida, de forma rastreável, os elementos centrais de cada modelagem principal do repositório.

---

## 1) `1_2_1_caso_referencia_min_custo_energ.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** minimizar custo total de energia (compra da rede + degradação do BESS − receita de exportação).
- **Variáveis de decisão:** `P_grid[t]`, `P_export[t]`, `P_charge[t]`, `P_discharge[t]`, `SOC[t]`, `u_charge[t]`, `u_discharge[t]`.
- **Restrições-chave:** balanço de potência; dinâmica de SOC; limites mínimo/máximo de SOC; SOC terminal; limites de carga/descarga; não simultaneidade carga/descarga.
- **Cenários:** operação horária de 24 h com perfis fixos de demanda comercial, demanda EV e geração FV.
- **Critérios de desempenho:** valor da função objetivo (R$), perfis horários de despacho e SOC.
- **Regras de calibração:** parâmetros de demanda e geração definidos em séries horárias determinísticas; eficiência e limites do BESS definidos por premissas técnicas.

---

## 2) `main2.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** minimizar custo de compra de energia da rede.
- **Variáveis de decisão:** `P_buy[t]`, `P_sell[t]`, `P_ch[t]`, `P_dch[t]`, `S[t]`.
- **Restrições-chave:** balanço energético; dinâmica inicial e recursiva da bateria; limite de energia do BESS; limite de compra da rede.
- **Cenários:** definido pelo arquivo `.dat` (horizonte `N` e séries de entrada por período).
- **Critérios de desempenho:** função objetivo e indicadores agregados no relatório (`energia_total_*`, `soc_min`, `soc_max`).
- **Regras de calibração:** calibração orientada por valores de entrada em `data.dat` (ou arquivo equivalente), incluindo preços, carga, geração FV e parâmetros do BESS.

---

## 3) `main.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** maximizar lucro operacional anualizado menos custos de investimento (com opção de formulação “article-like” com CRF e O&M).
- **Variáveis de decisão:**  
  - investimento: `P_pv_cap`, `E_bess_cap`, `P_trafo_cap`;  
  - operação horária: `P_pv_gen[t]`, `P_grid_import[t]`, `P_grid_export[t]`, `P_bess_charge[t]`, `P_bess_discharge[t]`, `SOC[t]`, `LoadShedding[t]`, `y_bess[t]`.
- **Restrições-chave:** limite de geração FV; limites de importação/exportação via transformador; limites de potência e capacidade do BESS; não simultaneidade carga/descarga (Big-M); janela e dinâmica de SOC; SOC terminal; balanço de energia; serviço sem corte de carga (`NoLoadShedding`).
- **Cenários:** dia representativo de 24 horas (`T=1..24`) com séries de irradiância, preço da rede e carga EV.
- **Critérios de desempenho:** `Obj`, capacidades ótimas, fluxos energéticos anuais/horários e indicadores econômicos do relatório.
- **Regras de calibração:** parâmetros técnicos/econômicos e séries horárias via `.dat`; limites superiores (`*_cap_max`) como âncoras físicas de Big-M; habilitação ou bloqueio de exportação via `allow_grid_export`.

---

## 4) `modelo_abstract_artigo_itens_322_323_4_5_6.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** minimizar índice técnico de viabilidade/risco de fornecimento em múltiplos cenários.
- **Variáveis de decisão:**  
  - investimento: `P_pv_cap`, `E_bess_cap`, `P_trafo_cap`;  
  - operação por cenário e hora: `P_pv_gen[sc,t]`, `P_grid_import[sc,t]`, `P_grid_export[sc,t]`, `P_bess_charge[sc,t]`, `P_bess_discharge[sc,t]`, `SOC[sc,t]`, `LoadShedding[sc,t]`, `y_bess[sc,t]`, `y_grid[sc,t]`.
- **Restrições-chave:** limites de capacidade; limites de potência; não simultaneidade BESS e rede; dinâmica/limites/reserva de SOC; SOC terminal; balanço de energia; limites de ENS total e horário; autossuficiência mínima; dependência máxima de rede; limite de throughput do BESS; normalização de probabilidades de cenário.
- **Cenários:** conjunto `SC` com probabilidade `prob_sc`, dados horários por cenário (`grid_price`, `export_price`, `irradiance_cf`, `P_EV_load`, `grid_availability`).
- **Critérios de desempenho:** valor do índice técnico (`TechnicalViabilityIndex`) e métricas derivadas de atendimento, dependência de rede e uso do BESS.
- **Regras de calibração:** calibração por parâmetros de desempenho técnico (`max_ens_ratio`, `min_self_suff_ratio`, etc.), pesos multicritério (`w_*`) e dados de entrada por cenário.

---

## 5) `simulacao_eletroposto_ve.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** simular operação de eletroposto no Brasil e comparar casos determinísticos vs. estocásticos.
- **Variáveis de decisão (simulação):** seleção de carregador por sessão, instante de início, duração e fila implícita (via disponibilidade dos carregadores).
- **Restrições-chave:** alocação por disponibilidade temporal dos carregadores; potência efetiva limitada por tecnologia do veículo/carregador; curva de recarga com tapering por SOC; truncamentos físicos de SOC e tempo máximo de sessão.
- **Cenários:** anos (2026, 2030, 2035), perfis (`tipico`, `anti_tipico`) e casos aleatórios com diferentes perturbações; amostragem Monte Carlo.
- **Critérios de desempenho:** `chegadas`, `atendidos`, `energia_kwh`, `espera_media_min`, `espera_p95_min`, `pico_kw`, `fator_carga`, `utilizacao`.
- **Regras de calibração:** mix de veículos por ano, parque de carregadores por ano, perfis horários normalizados, distribuição estocástica de chegadas e SOC, eficiência de recarga e parâmetros de perturbação.

---

## 6) `analise_secao_3_2_rodovia.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** reproduzir e adaptar a análise da Seção 3.2 para corredor rodoviário brasileiro com recorte empírico.
- **Variáveis de decisão (simulação):** mesmas decisões operacionais da simulação-base de carregamento (alocação temporal em carregadores e atendimento de sessões).
- **Restrições-chave:** regras de capacidade/atendimento herdadas da simulação-base, acrescidas de calibração rodoviária (perfil horário, SOC de chegada e energia de viagem longa).
- **Cenários:** referência urbana e cenários rodoviários (ex.: Dutra), modos determinístico e estocástico, anos de análise e casos com perturbação.
- **Critérios de desempenho:** KPIs de atendimento e fila (`espera`, `p95`), energia atendida, pico e utilização, com comparação entre cenários.
- **Regras de calibração:** `RECORTE_EMPIRICO_DUTRA`, fatores de crescimento por ano, probabilidade de cenários (`scenario_probability`), ajuste de variabilidade (CV → perturbação), ajuste energético de viagem longa e geração de entrada para modelo abstrato (`entrada_recorte_empirico_dutra_abstract.dat`).

---

## 7) `analise_fronteira_viabilidade.py`

- **Data-versão do registro:** 2026-08-11 · v1.0  
- **Objetivo do modelo:** mapear fronteira de viabilidade por sensibilidade paramétrica do modelo de otimização principal.
- **Variáveis de decisão:** herdadas de `main.py` (capacidade de ativos e despacho horário), resolvidas a cada variação paramétrica.
- **Restrições-chave:** todas as restrições de `main.py`, reavaliadas a cada cenário de parâmetro.
- **Cenários:** varredura de parâmetros (`DEFAULT_ANALYSIS_PARAMS`) com busca de limites mínimo/máximo viáveis.
- **Critérios de desempenho:** faixa viável por parâmetro (`feasible_min`, `feasible_max`), status de solução e métricas econômicas/técnicas derivadas (`objective`, lucro operacional, uso de rede, perdas FV, proxy de redução de CO₂).
- **Regras de calibração:** limites por tipo de parâmetro (`UNIT_INTERVAL_PARAMS`, `PRACTICAL_UPPER_BOUNDS`), sobrescrita controlada de escalares no `.dat` e avaliação de factibilidade via solver.
