# Repository Overview

"Testes-de-Simulações-Artigo" is a research repository supporting an academic article about the simultaneous capacity configuration and scheduling optimization of an integrated EV (Electric Vehicle) charging station combining photovoltaic (PV) solar generation, battery energy storage systems (BESS), and grid connection. The article title is included as a PDF in the repo.

Key Technologies
Technology	Role
Python	All modeling and simulation
Pyomo	Mathematical optimization framework (AbstractModel-based MIP)
Gurobi (gurobipy)	Commercial solver for the optimization problems
Pandas / NumPy	Data manipulation and analysis
Matplotlib	Plotting and visualization
PyPSA	Power Systems Analysis library (referenced but used in early notebooks)
Code Organization
Core Optimization Models
main.py — The primary Pyomo AbstractModel for the EV charging station (eletroposto) microgrid. 
  Models a 24-hour horizon with PV, BESS, and grid dispatch. Objective: maximize operational profit minus annualized CAPEX. 
Key features:

Binary variable for BESS charge/discharge exclusion (no-simultaneity constraint via Big-M)
Selectable objective: simplified profit vs. annualized with CRF + O&M
Load shedding variable forced to zero (uninterruptible supply)
main2.py — A second Pyomo model variant.

modelo_abstract_artigo_itens_322_323_4_5_6.py — Extended multi-scenario AbstractModel covering article sections 3.2.2, 3.2.3, 4, 5, 6. Adds:

Multi-scenario support (set SC with probabilities prob_sc)
Technical performance indices (energy-not-served ratio, self-sufficiency, grid import ratio)
Investment decisions shared across scenarios (P_pv_cap, E_bess_cap, P_trafo_cap)
1_2_1_caso_referencia_min_custo_energ.py / .ipynb — Early reference case notebook: a simpler 24h cost-minimization model (commerce + EV charging demand, PV generation), exported from Jupyter.

Simulation
simulacao_eletroposto_ve.py — Monte Carlo / stochastic simulation of EV arrivals at a Brazilian charging station. Implements:
Chinese traffic profile methodology adapted for Brazil
Deterministic vs. stochastic arrival comparison
15-minute time slots, multiple vehicle technology types (VehicleTech dataclass)
Output: relatorio_eletroposto_ve.txt, resultado_eletroposto_ve.csv
Analysis Scripts
analise_secao_3_2_rodovia.py — Scenario analysis for highway (rodovia) corridors. Uses simulacao_eletroposto_ve.py as a library; replaces the urban reference profile with a highway traffic profile. Outputs CSV + report.

analise_fronteira_viabilidade.py — Sensitivity/feasibility frontier analysis in the spirit of article Section 5.4. Uses the main.py model to sweep parameters and map the feasibility boundary.

Data Files (.dat)
Pyomo AbstractModel data files:

data.dat, dados_exemplo.dat — General/example input data
dados_cenarios_brasil.dat — Brazilian scenario data
dados_dutra_abstract_completo.dat, entrada_recorte_empirico_dutra_abstract.dat — Data calibrated to the Dutra highway corridor (BR-116, Brazil's busiest freight/EV corridor)
recorte_empirico_dutra.json — Empirical data from the Dutra corridor (246 avg daily arrivals, Jan 2025–Feb 2026)
Output Files
relatorio_*.txt — Human-readable operation reports
resultado_*.csv — Tabular results
saida_fronteira_viabilidade/ — Feasibility frontier outputs
curva_carregamento_comparacao.png — Load curve comparison chart
Subdirectories
Alternativa dados/ — Alternative data input scripts including a Gurobi API exploration script
CALIBRAÇÃO BRASIL/ — Brazilian market calibration: validation scripts, benchmark comparisons, article material generation, and charts for publication
TESTES - Gurobi chat/ — Microgrid investment analyzer experiments (likely from a Gurobi AI chat session), with a standalone analyzer and report
Documentation
hipoteses_metodologia_calibracao_dutra.md — Documents calibration hypotheses for the Dutra corridor (stochastic CV, energy demand per session, yearly growth factors)
referencias_parametros_dutra.md — Parameter reference source list
article_extracted_text.txt — Full text of the reference article
relatorio1.txt, relatorio_saida.txt — Intermediate solver output logs
Research Workflow
Code
Empirical data (Dutra corridor)
        ↓
simulacao_eletroposto_ve.py  →  EV demand profiles (stochastic/deterministic)
        ↓
Pyomo AbstractModel (main.py / modelo_abstract_artigo_*.py)
        ↓
Gurobi solver
        ↓
Reports (CSV + TXT) + sensitivity / feasibility analysis
        ↓
CALIBRAÇÃO BRASIL/ → validation vs. market benchmarks → article figures
The repository essentially implements the computational backbone for an operations research paper studying how to optimally size and schedule a Brazilian highway EV fast-charging station (with solar + battery + grid) while accounting for stochastic EV demand, technical reliability constraints, and economic viability.
