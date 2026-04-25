import json
import pandas as pd
import gurobipy as gp

# Carregar dados
with open('dados_eletroposto.json', 'r') as f:
    dados = json.load(f)

df_series = pd.read_csv('series_temporais_horarias.csv')

# Extrair parâmetros
demanda_verao = df_series[df_series['cenario']=='verao']['demanda_kwh'].values
irrad_verao = df_series[df_series['cenario']=='verao']['irradiacao_kwh_m2'].values
CAPEX_PV = dados['parametros_tecnicos']['sistema_fotovoltaico']['capex_usd_kwp']

# Construir modelo Gurobi
modelo = gp.Model('Eletroposto')
# ... (ver exemplo_uso_dados_gurobi.py)
