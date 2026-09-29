# Auditoria dos modelos, perguntas e função científica dos arquivos

## 1) Perguntas de pesquisa revisadas

### 1.1 Qual pergunta cada modelo responde

| Arquivo | Pergunta de pesquisa efetivamente respondida | Escopo |
|---|---|---|
| `main.py` | Qual combinação de capacidade (PV/BESS/trafo) e despacho horário maximiza retorno econômico anualizado para uma demanda de recarga **exógena e inelástica**? | Dimensionamento + operação + viabilidade econômica |
| `modelo_abstract_artigo_itens_322_323_4_5_6.py` | Quais decisões de investimento compartilhadas entre cenários minimizam risco técnico esperado (ENS, dependência de rede, estresse de bateria) sob múltiplos cenários de demanda? | Confiabilidade + robustez técnica multi-cenário |
| `analise_fronteira_viabilidade.py` | Em que faixas de parâmetros o modelo principal permanece factível e economicamente viável? | Sensibilidade e fronteira de viabilidade |
| `simulacao_eletroposto_ve.py` | Quais perfis de carga/espera surgem da simulação estocástica de chegadas e sessões de recarga? | Geração de demanda e KPIs operacionais |
| `analise_secao_3_2_rodovia.py` | Como o recorte Dutra altera métricas operacionais frente ao perfil urbano de referência e como derivar `SC/prob_sc/P_EV_load` para o modelo abstrato? | Calibração empírica + geração de cenários |
| `main2.py` | Qual despacho minimiza custo de compra de energia da rede em formulação simplificada? | Auxiliar/legado (comparação) |

### 1.2 Decisão metodológica explícita (formulação canônica)

- **Formulação canônica da dissertação**: `main.py` (núcleo econômico de dimensionamento + operação).
- **Complementos canônicos**:
  - `analise_secao_3_2_rodovia.py` e `simulacao_eletroposto_ve.py` para construção/calibração de demanda;
  - `analise_fronteira_viabilidade.py` para análise de sensibilidade.
- **Modelo especializado para confiabilidade técnica**: `modelo_abstract_artigo_itens_322_323_4_5_6.py` (comparável por métricas comuns, mas objetivo distinto).
- **Legado**: `main2.py` (não canônico).

### 1.3 Classificação do cenário Dutra e da demanda VE

- **Dutra**: caso empírico calibrado (não é medição horária integral direta em cada ponto modelado).
- **Demanda VE (`P_EV_load`)**:
  - observada no nível agregado (estatísticas de chegadas e energia/sessão do recorte);
  - derivada por transformação de perfil horário e multiplicadores de cenário;
  - sintética no nível horário final por cenário (`base/pico/vale`).

### 1.4 O que responde à dissertação vs. o que é exploratório/legado

- **Resultados necessários à dissertação**:
  - capacidades ótimas e KPIs econômico-operacionais do `main.py`;
  - KPIs da calibração Dutra e cenários de demanda (`analise_secao_3_2_rodovia.py`);
  - fronteiras de sensibilidade (`analise_fronteira_viabilidade.py`).
- **Resultados complementares/exploratórios**:
  - índice técnico multi-cenário do modelo abstrato estendido;
  - comparativos do `main2.py`.

### 1.5 Conclusões sustentáveis vs. dependentes de calibração adicional

- **Sustentáveis com os dados atuais**:
  - trade-offs econômicos e operacionais condicionais às hipóteses adotadas;
  - efeito relativo de cenários `base/pico/vale` sobre dimensionamento/viabilidade;
  - sensibilidade de viabilidade a parâmetros-chave.
- **Exigem calibração adicional para generalização forte**:
  - projeções absolutas para tarifa/localidade específicos sem atualização de fontes;
  - inferências comportamentais de demanda (demanda é inelástica em `main.py`);
  - extrapolação para confiabilidade empírica real sem eventos observados de indisponibilidade.

## 2) Auditoria técnica por arquivo

| Arquivo | Função científica | Problema matemático | Entradas-chave | Decisões/variáveis | Restrições e objetivo | Saídas | Papel metodológico |
|---|---|---|---|---|---|---|---|
| `main.py` | Modelo econômico principal do eletroposto integrado | MILP/LP de planejamento + despacho em 24h | `dados_exemplo.dat` (ou `.dat` compatível), `P_EV_load`, `grid_price`, `irradiance_cf`, CAPEX e parâmetros BESS | `P_pv_cap`, `E_bess_cap`, `P_trafo_cap`, despacho horário (`P_grid_*`, `P_bess_*`, `SOC`) | Balanço de energia, limites de capacidade/SOC, não simultaneidade, `LoadShedding=0`; objetivo de lucro anualizado menos custos/capital | `relatorio_saida.txt` | **Principal** |
| `main2.py` | Variante simplificada para despacho | LP de minimização de compra da rede | `data.dat`, `PV_gen`, `Load`, `buy_price`, `eta_*`, `W_BESS` | `P_buy`, `P_sell`, `P_ch`, `P_dch`, `S` | Balanço, dinâmica de bateria, limites de SOC e compra; objetivo minimizar compra da rede | `relatorio1.txt` | **Auxiliar/legado** |
| `modelo_abstract_artigo_itens_322_323_4_5_6.py` | Avaliação técnica multi-cenário com risco esperado | MILP multi-cenário com decisões de investimento compartilhadas | `SC`, `prob_sc`, `P_EV_load(sc,t)`, `grid_price`, `irradiance_cf`, pesos técnicos | Capacidade comum + operação por cenário (`LoadShedding`, `y_bess`, `y_grid`) | Limites técnicos, atendimento de carga, restrições de ENS/autossuficiência/dependência; objetivo minimiza índice técnico esperado | Variáveis/indicadores por cenário e capacidades ótimas | **Modelo especializado** (confiabilidade/robustez) |
| `simulacao_eletroposto_ve.py` | Gerar perfis e KPIs de recarga sob incerteza | Simulação estocástica (Monte Carlo) de chegadas/sessões | Mix de veículos, parque de carregadores, perfil horário, sementes aleatórias | Alocação de sessões, tempos de espera, potência agregada | Regras operacionais de atendimento e potência efetiva | `resultado_eletroposto_ve.csv`, `relatorio_eletroposto_ve.txt` | **Geração de insumo** |
| `analise_secao_3_2_rodovia.py` | Calibrar e comparar corredor Dutra e gerar entrada abstrata | Simulação + transformação de dados em cenários | `RECORTE_EMPIRICO_DUTRA`, perfil Dutra, anos de recorte | Construção de cenários e curvas horárias (`base/pico/vale`) | Regras de calibração por CV e energia média por sessão | `resultado_secao_3_2_dutra.csv`, `relatorio_secao_3_2_dutra.txt`, `recorte_empirico_dutra.json`, `entrada_recorte_empirico_dutra_abstract.dat` | **Calibração** |
| `analise_fronteira_viabilidade.py` | Medir faixa factível de parâmetros do modelo principal | Busca de fronteiras por bisseção com checagem de factibilidade | `.dat` base, lista de parâmetros, solver | Overriding de parâmetros e reexecução do `main.py` | Critério de factibilidade + extração de métricas econômicas/energéticas | CSVs/relatórios em `saida_fronteira_viabilidade/` | **Sensibilidade** |

## 3) Comparabilidade, duplicação e divergência

- **Diretamente comparáveis entre modelos**:
  - energia importada da rede, uso de BESS, capacidades instaladas (quando disponíveis).
- **Não diretamente comparáveis sem cuidado**:
  - valor da função objetivo de `main.py` (econômica) vs. do modelo abstrato estendido (índice técnico).
- **Duplicação/divergência identificada**:
  - coexistência de `main.py` e `main2.py` para problemas próximos com objetivos diferentes;
  - `main.py` fixa `LoadShedding=0`, enquanto o modelo abstrato permite ENS com penalização/restrições;
  - necessidade de declarar sempre qual formulação está sendo usada em cada resultado.

## 4) Cadeia rastreável exigida (de ponta a ponta)

1. **Pergunta de pesquisa**: dimensionar e operar eletroposto com critérios econômicos/técnicos explícitos.  
2. **Hipótese/objetivo**: demanda VE exógena, cenários representativos e operação com restrições físicas.  
3. **Cenário**: Dutra (`base/pico/vale`) e/ou cenários de sensibilidade de parâmetros.  
4. **Fonte dos dados**: recorte empírico Dutra + referências técnicas/documentais.  
5. **Transformação**: agregação estatística e derivação de `P_EV_load`/`SC`/`prob_sc`.  
6. **Entrada do modelo**: `.dat` (modular ou completo).  
7. **Formulação matemática**: `main.py` (canônica) ou modelo abstrato técnico (quando declarado).  
8. **Execução**: scripts Python com solver disponível.  
9. **Resultado**: relatórios e CSVs versionados.  
10. **Indicador**: lucro/capacidade/fluxos energéticos (modelo canônico) e índices técnicos (modelo especializado).  
11. **Interpretação**: decisão de investimento/operação condicionada às hipóteses adotadas.  
12. **Limitação**: demanda inelástica, parâmetros representativos e horizonte diário típico.
