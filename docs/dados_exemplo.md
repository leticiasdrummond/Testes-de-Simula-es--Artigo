# Documentação do Arquivo de Dados (`.dat`)

Este documento descreve o formato e o significado de cada campo dos arquivos
de entrada `.dat` utilizados pelo modelo Pyomo (`main.py`).
O arquivo de exemplo completo é `dados_exemplo.dat` na raiz do repositório.

---

## Estrutura geral

Os arquivos `.dat` seguem a sintaxe do Pyomo para `AbstractModel`.
Parâmetros escalares usam `param <nome> := <valor>;` e séries horárias usam
blocos tabulares `param <nome> := <t> <valor> ... ;`.

---

## Parâmetros obrigatórios

### Escalares de controle

| Parâmetro                   | Tipo    | Unidade   | Intervalo/Valores | Descrição |
|-----------------------------|---------|-----------|-------------------|-----------|
| `delta_t`                   | Real    | h         | > 0 (padrão: 1)   | Duração de cada período horário |
| `operational_days_equivalent` | Real  | dias/ano  | > 0 (padrão: 365) | Fator de anualização do dia representativo |
| `use_article_like_objective`| Inteiro | —         | {0, 1}            | 0 = objetivo simplificado; 1 = objetivo artigo-like (CRF + O&M) |
| `allow_grid_export`         | Inteiro | —         | {0, 1}            | 0 = exportação para rede proibida; 1 = habilitada |

### Tarifas e fatores econômicos

| Parâmetro           | Tipo | Unidade    | Descrição |
|---------------------|------|------------|-----------|
| `tariff_ev`         | Real | BRL/kWh    | Tarifa de venda de energia ao usuário de VE |
| `export_price_factor` | Real | —        | Fração de `grid_price[t]` paga pela exportação (ex.: 0,70 = 70 %) |

### CAPEX (custo unitário de investimento)

| Parâmetro        | Tipo | Unidade   | Descrição |
|------------------|------|-----------|-----------|
| `capex_pv_kw`    | Real | BRL/kW    | Custo unitário do arranjo fotovoltaico |
| `capex_bess_kwh` | Real | BRL/kWh   | Custo unitário do armazenamento de energia (BESS) |
| `capex_trafo_kw` | Real | BRL/kW    | Custo unitário do transformador de conexão com a rede |

### Anualização — obrigatórios apenas quando `use_article_like_objective = 1`

| Parâmetro           | Tipo | Unidade      | Descrição |
|---------------------|------|--------------|-----------|
| `crf_pv`            | Real | —            | Capital Recovery Factor do FV |
| `crf_bess`          | Real | —            | Capital Recovery Factor do BESS |
| `crf_trafo`         | Real | —            | Capital Recovery Factor do transformador |
| `om_pv_kw_year`     | Real | BRL/(kW·ano) | O&M anual do FV por kW instalado |
| `om_bess_kwh_year`  | Real | BRL/(kWh·ano)| O&M anual do BESS por kWh instalado |
| `om_trafo_kw_year`  | Real | BRL/(kW·ano) | O&M anual do transformador por kW instalado |

### Parâmetros técnicos do BESS

| Parâmetro            | Tipo | Unidade | Intervalo típico | Descrição |
|----------------------|------|---------|------------------|-----------|
| `eta_charge`         | Real | —       | (0, 1]           | Eficiência de carga (ex.: 0,91) |
| `eta_discharge`      | Real | —       | (0, 1]           | Eficiência de descarga (ex.: 0,91) |
| `soc_min_frac`       | Real | —       | [0, 1)           | SOC mínimo como fração da capacidade (ex.: 0,05) |
| `soc_max_frac`       | Real | —       | (0, 1]           | SOC máximo como fração da capacidade (ex.: 0,95) |
| `soc_initial_frac`   | Real | —       | [soc_min, soc_max] | SOC inicial/final — garante periodicidade do dia representativo |
| `c_rate_charge`      | Real | 1/h     | > 0              | C-rate máximo de carga (ex.: 1,00 = carrega em 1 h) |
| `c_rate_discharge`   | Real | 1/h     | > 0              | C-rate máximo de descarga |

### Limites superiores de capacidade (âncoras do Big-M)

| Parâmetro         | Tipo | Unidade | Descrição |
|-------------------|------|---------|-----------|
| `E_bess_cap_max`  | Real | kWh     | Limite máximo de projeto para a capacidade do BESS (usado como Big-M) |
| `P_pv_cap_max`    | Real | kW      | Limite máximo de projeto para a capacidade do FV |
| `P_trafo_cap_max` | Real | kW      | Limite máximo de projeto para o transformador |

> **Nota sobre o Big-M:** `E_bess_cap_max` serve como o valor M das restrições
> de não-simultaneidade BESS. Um M derivado deste limite físico é seguro (não
> elimina soluções viáveis) e numericamente mais robusto do que uma constante
> arbitrariamente grande.

---

## Séries horárias (indexadas por `t = 1..24`)

| Parâmetro         | Unidade | Intervalo esperado | Descrição |
|-------------------|---------|--------------------|-----------|
| `irradiance_cf[t]`| —       | [0, 1]             | Fator de capacidade FV hora a hora (0 = noite, 1 = irradiância máxima) |
| `grid_price[t]`   | BRL/kWh | > 0                | Tarifa TOU de importação/referência por hora |
| `P_EV_load[t]`    | kW      | ≥ 0                | Demanda de recarga de VE (inelástica — deve ser atendida integralmente) |

---

## Exemplo mínimo de arquivo `.dat` (3 horas)

O arquivo completo `dados_exemplo.dat` usa 24 horas. Para entender a estrutura,
um exemplo reduzido com apenas 3 períodos seria:

```
# Exemplo didático com T = {1, 2, 3} — apenas para ilustrar o formato.
# O modelo exige exatamente 24 períodos; este exemplo não é executável diretamente.

param delta_t := 1;
param operational_days_equivalent := 365;
param use_article_like_objective := 0;
param allow_grid_export := 0;

param tariff_ev := 1.60;
param export_price_factor := 0.70;

param capex_pv_kw   := 1200;
param capex_bess_kwh := 700;
param capex_trafo_kw := 1000;

param eta_charge    := 0.91;
param eta_discharge := 0.91;
param soc_min_frac  := 0.05;
param soc_max_frac  := 0.95;
param soc_initial_frac := 0.50;
param c_rate_charge    := 1.00;
param c_rate_discharge := 1.00;

param E_bess_cap_max  := 2000;
param P_pv_cap_max    := 1000;
param P_trafo_cap_max := 500;

param irradiance_cf :=
1  0.00
2  0.50
3  0.00
;

param grid_price :=
1  0.25
2  0.88
3  0.25
;

param P_EV_load :=
1  35
2  98
3  28
;
```

---

## Observações importantes

- **`allow_grid_export`**: quando `0`, a restrição `TrafoExportLimit` força
  `P_grid_export[t] = 0` em todos os períodos — a receita de exportação some
  da função objetivo. Cenário base (rodovia brasileira): exportação proibida.
- **`use_article_like_objective`**: quando `1`, os parâmetros de CRF e O&M
  **devem** estar presentes e não nulos no arquivo `.dat`; caso contrário, o
  objetivo artigo-like resulta em zero para os termos de custo de capital.
- **Periodicidade do SOC**: `soc_initial_frac` define tanto o estado inicial
  quanto o estado final do BESS (restrição `TerminalSOC`). Isso garante
  neutralidade energética da bateria no dia representativo.
- **Unidades de `grid_price`**: é a tarifa de *importação* (BRL/kWh). A
  remuneração de exportação é `export_price_factor × grid_price[t]`.
