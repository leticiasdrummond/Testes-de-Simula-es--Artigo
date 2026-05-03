---
Se quiser avançar corretamente para nível publicação, posso te entregar:

# ==========================================================
# GERADOR DE PERFIL DE DEMANDA - ELETROPOSTO RODOVIÁRIO
# Nível: Dissertação / Artigo
# Saída: CSV compatível com HOMER Grid (8760 ou 15-min)
# ==========================================================

import numpy as np
import pandas as pd

# =========================
# 1. CONFIGURAÇÃO DO CENÁRIO
# =========================

SCENARIOS = {
    "baixo": {
        "lambda_profile": [1,1,1,1,1,2,4,6,8,7,6,5,5,5,5,6,8,10,12,10,8,6,4,2],
        "n_chargers": 4,
        "P_charger": 60,  # kW
        "E_mean": 30      # kWh
    },
    "medio": {
        "lambda_profile": [2,2,2,2,2,4,8,12,15,12,10,8,8,8,10,12,15,18,20,18,15,10,6,4],
        "n_chargers": 8,
        "P_charger": 120,
        "E_mean": 40
    },
    "alto": {
        "lambda_profile": [3,3,3,3,3,6,12,18,25,20,18,15,15,15,18,20,25,30,35,30,25,18,10,6],
        "n_chargers": 16,
        "P_charger": 150,
        "E_mean": 50
    }
}

# =========================
# 2. PARÂMETROS GLOBAIS
# =========================

TIME_STEP_MIN = 15
STEPS_PER_HOUR = int(60 / TIME_STEP_MIN)
TOTAL_STEPS = 8760 * STEPS_PER_HOUR

EFFICIENCY = 0.92

# =========================
# 3. FUNÇÃO PRINCIPAL
# =========================

def generate_profile(scenario_name="medio", seed=42):

    np.random.seed(seed)
    scenario = SCENARIOS[scenario_name]

    lambda_hourly = scenario["lambda_profile"]
    n_chargers = scenario["n_chargers"]
    P_charger = scenario["P_charger"]
    E_mean = scenario["E_mean"]

    power_series = np.zeros(TOTAL_STEPS)

    active_sessions = []

    for t in range(TOTAL_STEPS):

        hour = (t // STEPS_PER_HOUR) % 24

        # Taxa de chegada (Poisson)
        lambda_t = lambda_hourly[hour] / STEPS_PER_HOUR
        arrivals = np.random.poisson(lambda_t)

        # Adiciona novos EVs
        for _ in range(arrivals):

            if len(active_sessions) < n_chargers:

                E = np.random.normal(E_mean, 0.2 * E_mean)
                E = max(E, 5)  # mínimo físico

                duration = (E / P_charger) / EFFICIENCY
                duration_steps = int(duration * STEPS_PER_HOUR)

                active_sessions.append(duration_steps)

        # Atualiza sessões
        current_power = 0
        updated_sessions = []

        for s in active_sessions:

            if s > 0:
                current_power += P_charger
                updated_sessions.append(s - 1)

        active_sessions = updated_sessions

        power_series[t] = current_power

    return power_series


# =========================
# 4. GERAR E EXPORTAR
# =========================

scenario = "medio"

profile = generate_profile(scenario)

time_index = pd.date_range(start="2025-01-01", periods=len(profile), freq=f"{TIME_STEP_MIN}min")

df = pd.DataFrame({
    "Time": time_index,
    "Load_kW": profile
})

# Exportar CSV
file_name = f"load_eletroposto_{scenario}.csv"
df.to_csv(file_name, index=False)

print(f"Arquivo gerado: {file_name}")
print(f"Demanda média: {df['Load_kW'].mean():.2f} kW")
print(f"Pico máximo: {df['Load_kW'].max():.2f} kW")

name:
description:
---

# My Agent

Describe what your agent does here.
