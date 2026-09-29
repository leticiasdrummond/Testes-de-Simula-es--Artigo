# Registro de dados levantados (auditoria metodológica)

## Convenções de classificação

1. **Dado primário/observado**
2. **Dado secundário/documental**
3. **Parâmetro de literatura**
4. **Dado derivado/transformado**
5. **Hipótese/premissa de modelagem**
6. **Cenário sintético**
7. **Entrada do modelo**
8. **Saída/resultado**
9. **Artefato legado**

## Itens rastreados

| ID | Classificação | Item | Fonte original | Período | Unidade | Transformação aplicada | Script responsável | Versão/commit | Destino no modelo | Hipótese associada |
|---|---|---|---|---|---|---|---|---|---|---|
| DUTRA-EMPIRICO | 1. Dado primário/observado | `recorte_empirico_dutra.json` (bloco `recorte_empirico_dutra`) | Levantamento de operação do corredor Dutra (eletropostos comparáveis), consolidado em `recorte_empirico_dutra.json` | 2025-01 a 2026-02 | chegadas/dia, kWh/sessão, fatores adimensionais | Consolidação de estatísticas observadas (média, desvio, p90, fatores) no JSON | `analise_secao_3_2_rodovia.py` (`save_empirical_record_json`) | e38f13e (marco citado na issue) + versão atual | Calibração de `arrivals_by_year`, `perturbation`, `scenario_probability` e base de `P_EV_load` | Caso Dutra é tratado como **caso empírico calibrado** (não medição horária direta em todos os pontos) |
| DUTRA-DOCUMENTAL | 2. Dado secundário/documental | Referências de tarifas, recurso solar e infraestrutura | `referencias_parametros_dutra.md` (ANEEL/MME, CRESESB/INPE/ONS/EPE, IRENA/NREL/EPE, mercado nacional) | Fontes com ano-base 2024-2026 (conforme documento) | BRL/kWh, BRL/kW, BRL/kWh, perfis adimensionais | Conversão para valores representativos utilizados nos arquivos `.dat` | Curadoria documental + parametrização em `.dat` | e38f13e + versão atual | Alimenta `grid_price`, `capex_*`, `irradiance_cf`, limites técnicos | Valores são representativos e exigem atualização para concessionária/modalidade tarifária específica |
| DUTRA-LITERATURA | 3. Parâmetro de literatura | Eficiências e limites operacionais de BESS (`eta_*`, `soc_*`, `c_rate_*`) | `referencias_parametros_dutra.md` (IEC/IEEE e revisões técnicas) | Sem série temporal (parâmetros estruturais) | adimensional ou 1/h | Seleção de faixas conservadoras para estudo de pré-viabilidade | Edição dos arquivos `.dat` e leitura pelos modelos Pyomo | e38f13e + versão atual | Restrições técnicas em `main.py` e `modelo_abstract_artigo_itens_322_323_4_5_6.py` | Janela de operação conservadora para robustez operacional |
| DUTRA-RECORTE-ABSTRACT | 4. Dado derivado/transformado | `entrada_recorte_empirico_dutra_abstract.dat` (`SC`, `prob_sc`, `P_EV_load`) | `recorte_empirico_dutra.json` + perfil horário da função `corridor_profile_dutra()` | Ano-alvo do recorte abstrato: 2030 (`RECORTE_PESQUISA`) | kW por hora, probabilidade | `P_EV_load` horário é derivado por `daily_arrivals × energia_média_sessão × perfil_horário`, com multiplicadores `base/pico/vale` | `analise_secao_3_2_rodovia.py` (`save_abstract_input_dat`) | e38f13e + versão atual | Entrada de demanda e cenários no modelo abstrato estendido | Cenários `base/pico/vale` são **perfis sintéticos escalados por CV**, não observações horárias diretas |
| LOADSHEDDING-ZERO | 5. Hipótese/premissa de modelagem | `LoadShedding[t] == 0` em `main.py` | Definição de modelagem no código (`NoLoadShedding`) | Horizonte diário representativo (24h) | kW | Restrição fixa atendimento ininterrupto | `main.py` | versão atual | Delimita o conjunto viável do modelo principal | Atendimento ininterrupto é requisito de modelagem, não evidência empírica |
| CENARIOS-BASE-PICO-VALE | 6. Cenário sintético | Cenários `dutra_empirico_base/pico/vale` | Regras de cenarização em `analise_secao_3_2_rodovia.py` | 2026/2030/2035 (calibração) e 2030 (recorte abstrato) | fator multiplicativo e curvas em kW | Escalonamento por coeficiente de variação observado (`cv`) | `analise_secao_3_2_rodovia.py` | e38f13e + versão atual | `SC`, `prob_sc`, `P_EV_load` em entradas abstratas | Uso para análise de sensibilidade/robustez, não para inferência causal direta |
| DUTRA-INPUT | 7. Entrada do modelo | `dados_dutra_abstract_completo.dat` | Combina `entrada_recorte_empirico_dutra_abstract.dat` (derivado) + parâmetros representativos técnicos/econômicos | 24h representativas por cenário | mistas (kW, kWh, BRL, adimensionais) | Integração de blocos de dados derivados e parâmetros representativos para execução direta | Montagem manual/versionada do `.dat` completo | e38f13e + versão atual | Executa `modelo_abstract_artigo_itens_322_323_4_5_6.py` | Separar leitura entre “derivado empírico” e “representativo técnico” ao interpretar resultados |
| RESULTADOS-PRINCIPAIS | 8. Saída/resultado | `relatorio_saida.txt`, `resultado_secao_3_2_dutra.csv`, `relatorio_secao_3_2_dutra.txt`, outputs de fronteira | Execuções de `main.py`, `analise_secao_3_2_rodovia.py` e `analise_fronteira_viabilidade.py` | Conforme execução | BRL/ano, kW, kWh, índices e KPIs | Pós-processamento interno de cada script | Scripts de execução correspondentes | commit da execução reprodutível | Base para indicadores da dissertação e análises complementares | Resultados dependem das hipóteses de demanda inelástica e cenário representativo |
| LEGADO-MAIN2 | 9. Artefato legado | `main2.py` + `data.dat` + `relatorio1.txt` | Versão simplificada de despacho com foco em minimização de compra da rede | 24h (N configurável) | kW, kWh, BRL | Formulação paralela, não integrada ao pipeline principal da dissertação | `main2.py` | versão atual (legado mantido para comparação) | Referência histórica/comparativa | Não adotar como formulação canônica sem requalificação metodológica explícita |

## Separação solicitada para `DUTRA-INPUT`

- **Bloco derivado do recorte empírico**: `SC`, `prob_sc`, `P_EV_load` (origem em `entrada_recorte_empirico_dutra_abstract.dat`).
- **Bloco representativo técnico/econômico**: `capex_*`, `grid_price`, `irradiance_cf`, limites técnicos e pesos (origem documental/literatura).

Essa separação deve ser mantida em toda interpretação de resultado para não apresentar parâmetros representativos como se fossem observações primárias.
