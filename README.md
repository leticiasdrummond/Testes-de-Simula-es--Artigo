# Visão Geral do Repositório

"Testes-de-Simulações-Artigo" é um repositório de pesquisa que sustenta um artigo acadêmico sobre a configuração simultânea de capacidade e a otimização do agendamento (scheduling) de um eletroposto integrado. O sistema combina geração solar fotovoltaica (FV), sistemas de armazenamento de energia em baterias (BESS) e conexão com a rede elétrica. O título do artigo está incluído como um PDF no repositório.

---

## Como Rodar

### 1. Pré-requisitos

```bash
pip install pyomo>=6.10.0 gurobipy pandas numpy matplotlib
```

Ou instale tudo de uma vez a partir do arquivo de dependências:

```bash
pip install -r requirements.txt
```

### 2. Solver

O script `main.py` usa o **Gurobi** por padrão (licença acadêmica gratuita disponível em [gurobi.com/academia](https://www.gurobi.com/academia/academic-program-and-licenses/)).

**Alternativas de solver (sem alterar o código de modelagem):**

| Solver | Gratuito | Como usar no Pyomo | Observação |
|--------|----------|--------------------|------------|
| **CBC** | ✅ | `SolverFactory("cbc")` | `pip install coincbc` ou `apt install coinor-cbc` |
| **GLPK** | ✅ | `SolverFactory("glpk")` | `apt install glpk-utils` |
| **HiGHS** | ✅ | `SolverFactory("highs")` | `pip install highspy` (via `appsi_highs`) |
| **Gurobi** | 🔑 | `SolverFactory("gurobi")` | Licença acadêmica gratuita |
| **CPLEX** | 🔑 | `SolverFactory("cplex")` | Licença acadêmica IBM disponível |

Para trocar o solver, edite a linha em `main.py`:
```python
solver = SolverFactory("cbc")   # ou "glpk", "highs", etc.
```
> **Nota**: solveres gratuitos podem ser mais lentos ou ter limites de escala.
> Para problemas maiores (múltiplos cenários, horizontes longos), Gurobi/CPLEX
> são recomendados.

### 3. Executar o modelo principal

```bash
python main.py
```

O script lê `dados_exemplo.dat` e gera `relatorio_saida.txt`.

### 4. O que é gerado

| Arquivo | Gerado por | Conteúdo |
|---------|------------|----------|
| `relatorio_saida.txt` | `main.py` | Capacidades ótimas, indicadores econômicos, despacho horário (CSV embutido) |
| `resultado_eletroposto_ve.csv` | `simulacao_eletroposto_ve.py` | Perfis de demanda VE estocásticos |
| `resultado_secao_3_2_*.csv` | `analise_secao_3_2_rodovia.py` | Cenários de rodovia |
| `saida_fronteira_viabilidade/` | `analise_fronteira_viabilidade.py` | Mapas de viabilidade econômica |

### 5. Personalizar o cenário

Edite `dados_exemplo.dat` (ou crie um novo `.dat`) trocando parâmetros como
`tariff_ev`, `capex_*`, `grid_price[t]`, etc. Veja a documentação completa dos
campos em [`docs/dados_exemplo.md`](docs/dados_exemplo.md).

---

## Tecnologias Principais

| Tecnologia | Função |
| :--- | :--- |
| **Python** | Toda a modelagem e simulação. |
| **Pyomo** | Framework de otimização matemática (MIP baseado em `AbstractModel`). |
| **Gurobi (gurobipy)** | Solver comercial para a resolução dos problemas de otimização. |
| **Pandas / NumPy** | Manipulação e análise de dados. |
| **Matplotlib** | Plotagem e visualização de dados. |
| **PyPSA** | Biblioteca de análise de sistemas de potência (referenciada em notebooks iniciais). |

---

## Organização do Código

### Modelos de Otimização (Core)

* **`main.py`**: O `AbstractModel` principal do Pyomo para a microrrede do eletroposto. Modela um horizonte de 24 horas com despacho de FV, BESS e rede. 
    * **Objetivo**: Maximizar o lucro operacional menos o CAPEX anualizado.
    * **Recursos**: Variável binária para exclusão de carga/descarga do BESS (restrição de não-simultaneidade via Big-M) e tratamento de corte de carga (load shedding) como suprimento ininterrupto.
* **`main2.py`**: Uma variante secundária do modelo Pyomo.
* **`modelo_abstract_artigo_itens_322_323_4_5_6.py`**: Modelo abstrato estendido para múltiplos cenários, cobrindo as seções 3.2.2 a 6 do artigo. Adiciona índices de desempenho técnico (taxa de energia não suprida, autossuficiência) e decisões de investimento compartilhadas entre cenários.
* **`1_2_1_caso_referencia_min_custo_energ.py / .ipynb`**: Caso de referência inicial para minimização de custos (comércio + demanda de carregamento VE + geração FV).

### Simulação

* **`simulacao_eletroposto_ve.py`**: Simulação estocástica/Monte Carlo de chegadas de VEs em um eletroposto brasileiro. Implementa a metodologia de perfil de tráfego adaptada para a realidade do Brasil, comparando chegadas determinísticas vs. estocásticas em intervalos de 15 minutos.
    * **Saída**: `relatorio_eletroposto_ve.txt` e `resultado_eletroposto_ve.csv`.

### Scripts de Análise

* **`analise_secao_3_2_rodovia.py`**: Análise de cenários para corredores rodoviários. Utiliza o simulador como biblioteca e substitui o perfil urbano por um perfil de tráfego rodoviário.
* **`analise_fronteira_viabilidade.py`**: Análise de sensibilidade e fronteira de viabilidade (Seção 5.4 do artigo). Mapeia os limites de viabilidade econômica varrendo diferentes parâmetros.

---

## Arquivos de Dados (.dat, .json)

> 📄 Documentação detalhada de todos os campos do `.dat` em [`docs/dados_exemplo.md`](docs/dados_exemplo.md).

* **`data.dat` / `dados_exemplo.dat`**: Dados de entrada gerais e exemplos.
* **`dados_cenarios_brasil.dat`**: Dados calibrados para cenários brasileiros.
* **`dados_dutra_abstract_completo.dat` / `entrada_recorte_empirico_dutra_abstract.dat`**: Dados calibrados especificamente para o corredor da Rodovia Presidente Dutra (BR-116).
* **`recorte_empirico_dutra.json`**: Dados empíricos do corredor Dutra (média de 246 chegadas diárias, jan/2025 – fev/2026).

---

## Estrutura de Diretórios

* **`Alternativa dados/`**: Scripts alternativos de entrada e explorações da API do Gurobi.
* **`CALIBRAÇÃO BRASIL/`**: Validação do mercado brasileiro, benchmarks e geração de gráficos para a publicação final.
* **`TESTES - Gurobi chat/`**: Experimentos com analisadores de investimento em microrredes (possivelmente derivados de sessões de IA/Gurobi Chat).
* **`saida_fronteira_viabilidade/`**: Resultados gerados pela análise de fronteira.

---

## Documentação de Apoio

* **`hipoteses_metodologia_calibracao_dutra.md`**: Documenta as hipóteses de calibração para a Dutra (demanda de energia por sessão, fatores de crescimento anual, etc.).
* **`referencias_parametros_dutra.md`**: Lista de fontes para os parâmetros utilizados.
* **`article_extracted_text.txt`**: Texto completo do artigo de referência para consulta rápida.

---

## Fluxo de Trabalho da Pesquisa

1.  **Dados Empíricos** (Corredor Dutra)
2.  **`simulacao_eletroposto_ve.py`** → Geração de perfis de demanda de VE (estocásticos).
3.  **Pyomo AbstractModel** (`main.py` / `modelo_abstract_artigo_*.py`) → Definição do problema matemático.
4.  **Gurobi Solver** → Otimização dos resultados.
5.  **Relatórios e Análises** → Geração de CSVs, TXTs e análise de fronteira de viabilidade.
6.  **`CALIBRAÇÃO BRASIL/`** → Validação final e geração das figuras do artigo.

> **Resumo**: Este repositório implementa a espinha dorsal computacional para um estudo de pesquisa operacional sobre como dimensionar e operar de forma otimizada um eletroposto de carregamento rápido em rodovias brasileiras, considerando incertezas de demanda, confiabilidade técnica e viabilidade econômica.

> # **Entradas e saídas**

 Arquivos de entrada (`.dat`) e saída (relatórios, CSVs, JSONs) estavam todos no diretório raiz, sem separação clara de propósito.

## Estrutura de diretórios

- **`entrada/`** — arquivos `.dat` consumidos pelos scripts (`data.dat`, `dados_exemplo.dat`, `dados_cenarios_brasil.dat`, `dados_dutra_abstract_completo.dat`)
- **`saida/`** — todos os artefatos gerados: `.txt`, `.csv`, `.json`, `.md`, e `fronteira_viabilidade/` (renomeado de `saida_fronteira_viabilidade/`)

## Scripts atualizados

Todos os caminhos hardcoded foram ajustados nos cinco scripts principais:

| Script | Entrada | Saída |
|---|---|---|
| `main.py` | `entrada/dados_exemplo.dat` | `saida/relatorio_saida.txt` |
| `main2.py` | `entrada/data.dat` | `saida/relatorio1.txt` |
| `simulacao_eletroposto_ve.py` | — | `saida/resultado_eletroposto_ve.{csv,txt}` |
| `analise_secao_3_2_rodovia.py` | — | `saida/*.{csv,txt,json,md,dat}` |
| `analise_fronteira_viabilidade.py` | `entrada/dados_exemplo.dat` (default) | `saida/fronteira_viabilidade` (default) |

Adicionado `mkdir(parents=True, exist_ok=True)` nos scripts que escrevem em `saida/`, garantindo que o diretório seja criado automaticamente na primeira execução.
