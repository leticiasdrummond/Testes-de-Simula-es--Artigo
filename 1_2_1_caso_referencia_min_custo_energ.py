# -*- coding: utf-8 -*-
# Arquivo gerado a partir do notebook 1_2_1_caso_referencia_min_custo_energ.ipynb


import pyomo.environ as pyo
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# %%
# ============================================================
# 3. DEFINIÃ‡ÃƒO DO HORIZONTE TEMPORAL
# ============================================================

HORIZONTE = 24
T = range(HORIZONTE)  # discretizaÃ§Ã£o horÃ¡ria

# %%
# ============================================================
# 4. DADOS DE ENTRADA
# ============================================================

# ---------------------------
# 4.1 Demandas (kW)
# ---------------------------

# Demanda do comÃ©rcio (kW)
# Os valores correspondentes da imagem do Guilherme representam +/- 17kWmÃ©dios
# Ajustado com coeficiente 1,74 para que os valores da imagem referencial do Guilherme tenham 30kWmÃ©dios
# - Esta adequaÃ§Ã£o para aumentar da demanda mÃ©dida fez com que a demanda do comÃ©rcio fosse quase sempre superior a geraÃ§Ã£o FV, ao contrÃ¡rio da imagem do Guilherme
# MÃ©dia da demanda do comÃ©rcio (kW)
demanda_comercio_med = 15

# Perfil de demanda / demanda mÃ©dia
demanda_comercio_pu = np.array([
    0.47, 0.47, 0.47, 0.47, 0.57, 0.70,
    0.93, 1.17, 1.63, 1.87, 1.87, 1.63,
    1.57, 1.50, 1.40, 1.33, 1.33, 1.17,
    1.00, 0.70, 0.47, 0.40, 0.47, 0.47
])

# Perfil de demanda do comÃ©rcio em kW
demanda_comercio = demanda_comercio_pu * demanda_comercio_med
# Demanda do eletroposto (kW)
# Considera 2 carregadores de 50kW (Max 100kW) com dois picos de uso
# Plotado conferindo a imagem de referencia do Guilherme
demanda_ev = [
    0, 0, 0, 0, 0, 0,            # 00h - 05h
    0, 0, 0, 0, 0, 0,      # 06h - 11h (Pico ManhÃ£ ~09h)
    72, 96, 72, 0, 0, 00,     # 12h - 17h (Carga leve tarde -> InÃ­cio Pico)
    76, 100, 76, 0, 0, 0         # 18h - 23h (Pico Noite ~18h e fim)
]

# ---------------------------
# 4.2 Geracao Fotovoltaica (kW)
# ---------------------------

# GeraÃ§Ã£o fotovoltaica (kW)
# CompatÃ­vel com sistema de 50 kWp (Pico ao meio-dia)
geracao_pv = [
    0, 0, 0, 0, 0, 0,            # 00h - 05h (Sem sol)
    2, 12, 28, 42, 48, 50,       # 06h - 11h (Amanhecer atÃ© pico)
    50, 48, 42, 28, 12, 2,       # 12h - 17h (Pico atÃ© anoitecer)
    0, 0, 0, 0, 0, 0             # 18h - 23h (Sem sol)
]


# ---------------------------
# 4.3 ParÃ¢metros EconÃ´micos
# ---------------------------

custo_compra = 0.75          # R$/kWh
preco_venda = 0.0           # R$/kWh
custo_degradacao = 0.08      # R$/kWh throughput

# ---------------------------
# 4.4 ParÃ¢metros do BESS
# ---------------------------

capacidade_bess = 50.0       # kWh
potencia_max_bess = 15.0     # kW

soc_min = 0.20 * capacidade_bess
soc_max = 0.95 * capacidade_bess
soc_inicial = 0.50 * capacidade_bess

eta_c = 0.955                # eficiÃªncia de carga
eta_d = 0.955                # eficiÃªncia de descarga

# %%
# ============================================================
# 5. VISUALIZAÃ‡ÃƒO DOS PERFIS
# ============================================================

plt.figure(figsize=(12, 6))
plt.plot(T, demanda_comercio, label="Demanda ComÃ©rcio")
plt.plot(T, demanda_ev, label="Demanda EV")
plt.plot(T, geracao_pv, label="GeraÃ§Ã£o FV")
plt.xlabel("Hora")
plt.ylabel("PotÃªncia (kW)")
plt.title("Perfis EnergÃ©ticos")
plt.xticks(T)
plt.grid(True)
plt.legend()
plt.show()

# %%
# =========================================================
# 6. CRIAÃ‡ÃƒO DO MODELO DE OTIMIZAÃ‡ÃƒO
# =========================================================

model = pyo.ConcreteModel()
model.T = pyo.Set(initialize=T)

# %%
# ------------------------------------------------------------
# 6.1 VariÃ¡veis de decisÃ£o
# ------------------------------------------------------------

# -  P_grid : Corresponde a comprar e venda para rede elÃ©trica
model.P_grid = pyo.Var(model.T, domain=pyo.NonNegativeReals)
model.P_export = pyo.Var(model.T, domain=pyo.NonNegativeReals)

# - P_dis/charge : Corresponde ao carregamento da bateria ou pela bateria
model.P_charge = pyo.Var(model.T, domain=pyo.NonNegativeReals)
model.P_discharge = pyo.Var(model.T, domain=pyo.NonNegativeReals)

# - SOC : Estado da bateria
model.SOC = pyo.Var(model.T, domain=pyo.NonNegativeReals)

# - u_charge : VariÃ¡veis binÃ¡rias (bloqueio simultÃ¢neo)

model.u_charge = pyo.Var(model.T, domain=pyo.Binary)
model.u_discharge = pyo.Var(model.T, domain=pyo.Binary)

# %%
# ------------------------------------------------------------
# 6.2 FunÃ§Ã£o Objetivo original:
# MinimizaÃ§Ã£o do custo total de energia
# ------------------------------------------------------------

def objective_rule(m):
    custo_energia = sum(custo_compra * m.P_grid[t] for t in m.T)
    receita_export = sum(preco_venda * m.P_export[t] for t in m.T)
    custo_deg = sum(custo_degradacao *
                    (m.P_charge[t] + m.P_discharge[t])
                    for t in m.T)
    return custo_energia + custo_deg - receita_export

model.OBJ = pyo.Objective(rule=objective_rule, sense=pyo.minimize)

# %%
# ------------------------------------------------------------
# 6.3 RestriÃ§Ãµes
# ------------------------------------------------------------

# BalanÃ§o de potÃªncia horÃ¡rio
def energy_balance_rule(m, t):
    demanda_total = demanda_comercio[t] + demanda_ev[t]
    return (
        m.P_grid[t]
        + geracao_pv[t]
        + m.P_discharge[t]
        ==
        demanda_total
        + m.P_charge[t]
        + m.P_export[t]
    )

model.energy_balance = pyo.Constraint(model.T, rule=energy_balance_rule)

# DinÃ¢mica do SOC
def soc_rule(m, t):
    if t == 0:
        return m.SOC[t] == (
            soc_inicial
            + eta_c * m.P_charge[t]
            - (m.P_discharge[t] / eta_d)
        )
    return m.SOC[t] == (
        m.SOC[t-1]
        + eta_c * m.P_charge[t]
        - (m.P_discharge[t] / eta_d)
    )

model.soc_dyn = pyo.Constraint(model.T, rule=soc_rule)

# Limites operacionais
model.soc_min = pyo.Constraint(model.T,
    rule=lambda m, t: m.SOC[t] >= soc_min)

model.soc_max = pyo.Constraint(model.T,
    rule=lambda m, t: m.SOC[t] <= soc_max)

model.soc_terminal = pyo.Constraint(
    expr=model.SOC[HORIZONTE-1] >= soc_inicial
)

model.charge_limit = pyo.Constraint(
    model.T,
    rule=lambda m, t:
        m.P_charge[t] <= potencia_max_bess * m.u_charge[t]
)

model.discharge_limit = pyo.Constraint(
    model.T,
    rule=lambda m, t:
        m.P_discharge[t] <= potencia_max_bess * m.u_discharge[t]
)

model.no_simultaneous = pyo.Constraint(
    model.T,
    rule=lambda m, t:
        m.u_charge[t] + m.u_discharge[t] <= 1
)

# %%
# ============================================================
# 7. RESOLUÃ‡ÃƒO
# ============================================================

solver = pyo.SolverFactory("gurobi")
if not solver.available(False):
    raise RuntimeError(
        "Solver gurobi_direct indisponivel. Instale o pacote gurobipy no ambiente pyomoenv."
    )

results = solver.solve(model, tee=False)

if results.solver.termination_condition != pyo.TerminationCondition.optimal:
    raise RuntimeError(
        f"Otimizacao nao encontrou solucao otima. Status={results.solver.status}, "
        f"Termination={results.solver.termination_condition}"
    )

# %%
# ============================================================
# 8. ORGANIZAÃ‡ÃƒO DOS RESULTADOS
# ============================================================

df = pd.DataFrame({
    "Hora": list(T),
    "Demanda_Comercio": demanda_comercio,
    "Demanda_EV": demanda_ev,
    "PV": geracao_pv,
    "Grid": [pyo.value(model.P_grid[t]) for t in T],
    "Export": [pyo.value(model.P_export[t]) for t in T],
    "Carga_BESS": [pyo.value(model.P_charge[t]) for t in T],
    "Descarga_BESS": [pyo.value(model.P_discharge[t]) for t in T],
    "SOC": [pyo.value(model.SOC[t]) for t in T],
})

print(df)
print(f"\nCusto Total: R$ {pyo.value(model.OBJ):.2f}")

# %%
# ============================================================
# 9. VISUALIZAÃ‡ÃƒO DOS RESULTADOS
# ============================================================

# SOC
plt.figure()
plt.plot(df["Hora"], df["SOC"])
plt.xlabel("Hora")
plt.ylabel("SOC (kWh)")
plt.title("Estado de Carga da Bateria")
plt.grid(True)
plt.show()

# Fluxo energÃ©tico
plt.figure(figsize=(14, 8))

plt.plot(df["Hora"], df["Demanda_Comercio"], label="Demanda ComÃ©rcio")
plt.plot(df["Hora"], df["Demanda_EV"], label="Demanda EV")

plt.plot(df["Hora"], df["PV"], label="GeraÃ§Ã£o FV")
plt.plot(df["Hora"], df["Grid"], label="Compra da Rede")
plt.plot(df["Hora"], df["Descarga_BESS"], label="Descarga BESS")
plt.plot(df["Hora"], df["Carga_BESS"], label="Carga BESS")
plt.plot(df["Hora"], df["Export"], label="ExportaÃ§Ã£o")

plt.xlabel("Hora")
plt.ylabel("PotÃªncia (kW)")
plt.title("Fluxo EnergÃ©tico da Microrrede")
plt.xticks(df["Hora"])
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

