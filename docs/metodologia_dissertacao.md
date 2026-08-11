# Metodologia da dissertação baseada no repositório

**Data-versão do documento:** 2026-08-11 · v1.0  
**Escopo:** estrutura metodológica completa para dissertação sobre eletroposto rodoviário com integração PV-BESS-rede, simulação de demanda e otimização.

---

## 1) Delimitação do problema da dissertação

### 1.1 Pergunta central
Como dimensionar e operar, de forma tecnicamente robusta e economicamente viável, um eletroposto rodoviário integrado com geração fotovoltaica (PV), armazenamento em baterias (BESS) e rede elétrica, sob incerteza de demanda de recarga de veículos elétricos?

### 1.2 Objetivo geral
Desenvolver e validar uma metodologia integrada de simulação e otimização para apoiar decisões de capacidade e despacho operacional de eletropostos em corredores rodoviários brasileiros.

### 1.3 Objetivos específicos
1. Construir cenários de demanda (determinísticos e estocásticos) para operação de recarga.
2. Formular modelos matemáticos de decisão de investimento e operação.
3. Avaliar desempenho técnico-econômico por métricas comparáveis entre cenários.
4. Quantificar sensibilidade dos resultados a parâmetros críticos.
5. Consolidar rastreabilidade entre premissas, modelos, dados e conclusões.

### 1.4 Hipóteses de trabalho
- H1: A representação estocástica da demanda melhora a robustez de planejamento frente a picos de atendimento.
- H2: O acoplamento PV-BESS reduz dependência de rede e melhora indicadores técnico-econômicos em cenários rodoviários.
- H3: A calibração empírica do corredor (ex.: Dutra) melhora aderência dos resultados frente a abordagem puramente urbana.
- H4: A análise de fronteira de viabilidade identifica faixas paramétricas úteis para decisão de investimento.

### 1.5 Escopo metodológico
- **Simulação de demanda:** `simulacao_eletroposto_ve.py` e `analise_secao_3_2_rodovia.py`.
- **Modelagem de otimização:** `main.py`, `main2.py`, `modelo_abstract_artigo_itens_322_323_4_5_6.py`, `1_2_1_caso_referencia_min_custo_energ.py`.
- **Análise de viabilidade/sensibilidade:** `analise_fronteira_viabilidade.py`.

---

## 2) Estrutura da revisão de literatura

### 2.1 Blocos temáticos
1. Planejamento de infraestrutura de recarga de VE.
2. Integração PV-BESS-rede em eletropostos.
3. Otimização estocástica e modelagem multicenário.
4. Métricas técnico-econômicas de desempenho e confiabilidade.

### 2.2 Literatura internacional x contexto brasileiro
- **Internacional:** formulações de simulação-otimização e planejamento de recarga.
- **Brasil:** expansão da eletromobilidade, perfis de uso, sinal tarifário e parâmetros de mercado/regulação.

### 2.3 Lacunas que a dissertação busca preencher
- Ausência de integração sistemática entre simulação de filas/demanda e otimização de capacidade/despacho para rodovias brasileiras.
- Necessidade de calibração explícita por recorte empírico nacional para reduzir viés de cenários urbanos ou internacionais.
- Falta de rastreabilidade metodológica completa entre premissas, parâmetros e conclusões.

---

## 3) Base bibliográfica rastreável

Tabela-base para uso em capítulos de fundamentação, metodologia e discussão.

| Referência | Tema | Variável/Parâmetro suportado | Seção da dissertação |
|---|---|---|---|
| Xi, Sioshansi, Marano (2013) | Simulação-otimização de infraestrutura de recarga | Estrutura de comparação determinístico vs estocástico; lógica de operação em estação | Seção 2 (revisão) e Seção 5 (protocolo) |
| Zhao et al. (2016) | Planejamento de capacidade/localização e filas | Critérios de dimensionamento e métricas de atendimento/espera | Seção 2 e Seção 4 |
| ABVE (2025) | Mercado brasileiro de eletromobilidade | Mix tecnológico e evolução de demanda | Seção 3 (dados/calibração) |
| EPE (2025) | Projeções de eletromobilidade no Brasil | Crescimento de cenários por ano e contextualização nacional | Seção 2 e Seção 3 |
| ANEEL/MME (tarifas e sinal horário) | Estrutura tarifária nacional | Curvas de `grid_price`, preço ponta/intermediário/fora de ponta | Seção 3 e Seção 4 |
| CRESESB/INPE/ONS/EPE | Recurso solar e sazonalidade | Perfil `irradiance_cf` | Seção 3 e Seção 4 |
| IRENA / NREL / EPE | Custos de tecnologias | `capex_pv_kw`, `capex_bess_kwh`, `capex_trafo_kw` | Seção 3 e Seção 4 |
| IEC/IEEE e literatura Li-ion | Parâmetros técnicos de bateria | `eta_*`, limites SOC, taxa C, premissas operacionais | Seção 4 |
| Referências de concessionárias/mercado | Interface de conexão | limites de transformador e premissas de rede | Seção 3 e Seção 4 |

> Observação: completar no capítulo de referências os metadados finais (autor completo, título, periódico/editora, ano, DOI/URL e data de acesso quando aplicável).

---

## 4) Arquitetura metodológica da dissertação

### Camada 1 — Dados e calibração
- Fontes de parâmetros e hipóteses: `referencias_parametros_dutra.md`, `hipoteses_metodologia_calibracao_dutra.md`, `recorte_empirico_dutra.json`.
- Entradas estruturadas: arquivos `.dat` e `.json`.

### Camada 2 — Simulação de demanda e cenários
- Geração de chegadas e sessões de recarga por perfil/ano/cenário.
- Saídas em CSV/TXT para análise de atendimento e filas.

### Camada 3 — Modelo de otimização
- Decisões de investimento e despacho.
- Restrições físicas, operacionais e de qualidade de serviço.

### Camada 4 — Sensibilidade e fronteira de viabilidade
- Varredura paramétrica para limites de factibilidade e desempenho.
- Identificação de regiões de maior risco/robustez.

### Camada 5 — Interpretação e implicações
- Tradução de resultados para recomendações técnico-econômicas.
- Discussão de aplicabilidade, limitações e agenda de expansão da pesquisa.

---

## 5) Representação padronizada das modelagens

Cada modelagem usada na dissertação deve ser documentada com o padrão:
1. Objetivo.
2. Variáveis de decisão.
3. Restrições-chave.
4. Cenários.
5. Critérios de desempenho.
6. Regras de calibração.
7. Data-versão.

**Núcleo já consolidado no repositório:** `docs/conteudo_central_modelagens.md` (usar como base oficial para o capítulo metodológico).

---

## 6) Protocolo de experimentos

### 6.1 Conjunto base de cenários
- Modos: determinístico e estocástico.
- Anos-base: 2026, 2030, 2035.
- Corredor principal: Dutra (com possibilidade de extensão para outros corredores).

### 6.2 Métricas de comparação
- Atendimento: chegadas, atendidos, energia entregue.
- Qualidade operacional: espera média, espera p95, pico de potência, utilização.
- Técnico-econômicas: valor objetivo, capacidades ótimas, dependência de rede, perdas FV, indicadores de viabilidade.

### 6.3 Critérios de robustez
- Consistência entre cenários determinísticos e estocásticos.
- Estabilidade de decisão sob variação de parâmetros críticos.
- Manutenção de desempenho mínimo sob choques de demanda.

### 6.4 Sensibilidade padronizada
- Priorizar parâmetros de tarifa, CAPEX, eficiência, limites de SOC/taxa C e disponibilidade de rede.
- Reportar faixa viável e comportamento das métricas em cada varredura.

---

## 7) Matriz de rastreabilidade ponta a ponta

| Pergunta/hipótese | Modelo/experimento | Dados de entrada | Saída/KPI | Conclusão esperada |
|---|---|---|---|---|
| H1 (demanda estocástica melhora robustez) | `simulacao_eletroposto_ve.py` + `analise_secao_3_2_rodovia.py` | Perfis horários, mix de veículos, parâmetros de perturbação, calibração empírica | espera média, p95, pico, utilização | evidenciar risco de subdimensionamento no caso determinístico |
| H2 (PV-BESS melhora desempenho) | `main.py` e `modelo_abstract_artigo_*` | preços, irradiância, carga EV, parâmetros BESS/PV/trafo | lucro/objetivo, importação de rede, capacidades ótimas | identificar ganhos operacionais e econômicos |
| H3 (calibração rodoviária melhora aderência) | `analise_secao_3_2_rodovia.py` | `RECORTE_EMPIRICO_DUTRA` e dados derivados | comparação urbano vs rodoviário, energia/sessão | mostrar redução de viés na representação da demanda |
| H4 (fronteira identifica limites de decisão) | `analise_fronteira_viabilidade.py` | base `.dat` + parâmetros de sensibilidade | faixa viável, métricas técnicas/econômicas | delimitar regiões de viabilidade para investimento |

### Controle de versão para resultados na dissertação
Registrar, para cada figura/tabela:
1. versão do arquivo de dados de entrada;
2. versão do modelo/script;
3. data de execução;
4. nome do artefato de saída usado no texto.

---

## 8) Plano de redação final da metodologia (capítulo da dissertação)

### Seção 1 — Desenho de pesquisa e justificativa
- problema, objetivos, hipóteses e contribuição.

### Seção 2 — Revisão de literatura e posicionamento
- síntese crítica por blocos temáticos e lacunas.

### Seção 3 — Dados, hipóteses e calibração
- fontes, premissas e recorte empírico.

### Seção 4 — Formulação dos modelos
- modelagens de simulação e otimização com representação padronizada.

### Seção 5 — Protocolo experimental e validação
- cenários, métricas, robustez e sensibilidade.

### Seção 6 — Limitações e agenda futura
- limites metodológicos, risco de generalização e próximos passos.

---

## Referências internas do repositório (apoio à redação)

- `docs/conteudo_central_modelagens.md`
- `docs/dados_exemplo.md`
- `hipoteses_metodologia_calibracao_dutra.md`
- `referencias_parametros_dutra.md`
- `README.md`
