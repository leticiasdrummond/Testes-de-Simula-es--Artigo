import pandas as pd
import numpy as np

print("=" * 80)
print("EXPLORANDO DADOS DOS EXEMPLOS GUROBI")
print("=" * 80)

# 1. DADOS DE DEMANDA - Power Generation Example
print("\n1. DADOS DE DEMANDA (Power Generation Example)")
print("-" * 80)

url_demand = 'https://github.com/Gurobi/modeling-examples/blob/master/power_generation/demand.csv?raw=true'
df_demand = pd.read_csv(url_demand)

print(f"Shape: {df_demand.shape}")
print(f"Colunas: {df_demand.columns.tolist()}")
print(f"\nPrimeiras linhas:")
print(df_demand.head(10))

print(f"\nPeríodo dos dados:")
print(f"Anos: {df_demand['YEAR'].min()} - {df_demand['YEAR'].max()}")
print(f"Meses disponíveis: {df_demand['MONTH'].unique()}")
print(f"Total de dias: {len(df_demand.groupby(['YEAR', 'MONTH', 'DAY']))}")

# Estatísticas da demanda
print(f"\nEstatísticas de Demanda (LOAD em MWh):")
print(df_demand['LOAD'].describe())

# Exemplo de dias típicos
print("\n" + "-" * 80)
print("EXEMPLO: Perfil de Demanda - 01 de Julho de 2011 (Verão)")
print("-" * 80)
df_summer = df_demand[(df_demand['YEAR']==2011) & (df_demand['MONTH']==7) & (df_demand['DAY']==1)]
print(df_summer[['HOUR', 'LOAD']])

print("\n" + "-" * 80)
print("EXEMPLO: Perfil de Demanda - 01 de Janeiro de 2011 (Inverno)")
print("-" * 80)
df_winter = df_demand[(df_demand['YEAR']==2011) & (df_demand['MONTH']==1) & (df_demand['DAY']==1)]
print(df_winter[['HOUR', 'LOAD']])

# 2. Calcular perfis agregados para uso no modelo
print("\n" + "=" * 80)
print("2. PERFIS AGREGADOS PARA O MODELO")
print("-" * 80)

# Perfil médio por hora do dia (verão vs inverno)
df_demand['SEASON'] = df_demand['MONTH'].apply(lambda x: 'Verao' if x == 7 else 'Inverno')

perfil_medio = df_demand.groupby(['SEASON', 'HOUR'])['LOAD'].mean().reset_index()
print("\nPerfil médio de demanda por estação:")
pivot_table = perfil_medio.pivot(index='HOUR', columns='SEASON', values='LOAD')
print(pivot_table)

# Salvar perfis para uso posterior
perfil_verao = df_demand[df_demand['MONTH']==7].groupby('HOUR')['LOAD'].mean()
perfil_inverno = df_demand[df_demand['MONTH']==1].groupby('HOUR')['LOAD'].mean()

print(f"\nDemanda total diária:")
print(f"  Verão: {perfil_verao.sum():.2f} MWh/dia")
print(f"  Inverno: {perfil_inverno.sum():.2f} MWh/dia")

print(f"\nPicos de demanda:")
print(f"  Verão: {perfil_verao.max():.2f} MWh (hora {perfil_verao.idxmax()})")
print(f"  Inverno: {perfil_inverno.max():.2f} MWh (hora {perfil_inverno.idxmax()})")

# 3. SIMULAÇÃO DE TARIFAS (Time-of-Use)
print("\n" + "=" * 80)
print("3. ESTRUTURA DE TARIFAS (Simulação Time-of-Use)")
print("-" * 80)

# Criar estrutura típica de tarifa Time-of-Use (TOU)
tarifas_data = []
for h in range(1, 25):
    if 18 <= h <= 21:  # Ponta (pico)
        tarifa = 0.25
        periodo = 'Ponta'
    elif (7 <= h < 18) or (21 < h <= 23):  # Intermediário
        tarifa = 0.15
        periodo = 'Intermediario'
    else:  # Fora-ponta
        tarifa = 0.08
        periodo = 'Fora-Ponta'
    tarifas_data.append({'hora': h, 'tarifa_usd_kwh': tarifa, 'periodo': periodo})

df_tarifas = pd.DataFrame(tarifas_data)
print("\nEstrutura de Tarifas Time-of-Use (USD/kWh):")
print(df_tarifas)

print(f"\nTarifa média ponderada: ${df_tarifas['tarifa_usd_kwh'].mean():.3f}/kWh")

# 4. DADOS SOLARES (Simulação baseada em padrões típicos)
print("\n" + "=" * 80)
print("4. GERAÇÃO SOLAR PV (Simulação)")
print("-" * 80)

# Perfil solar típico (normalizado 0-1, multiplicar por capacidade instalada)
solar_data = []
for h in range(1, 25):
    if 6 <= h <= 18:
        # Curva senoidal entre 6h e 18h
        angulo = np.pi * (h - 6) / 12
        irrad = np.sin(angulo) ** 2  # Forma de sino
    else:
        irrad = 0
    solar_data.append({'hora': h, 'irradiancia_norm': irrad})

df_solar = pd.DataFrame(solar_data)

print("\nPerfil de Irradiância Solar Normalizado (0-1):")
print(df_solar)
print(f"\nFator de capacidade diário: {df_solar['irradiancia_norm'].mean():.2%}")
print(f"Pico de irradiância (hora {df_solar.loc[df_solar['irradiancia_norm'].idxmax(), 'hora']}): {df_solar['irradiancia_norm'].max():.3f}")

# 5. EXEMPLO DE ESCALONAMENTO PARA ELETROPOSTO
print("\n" + "=" * 80)
print("5. EXEMPLO: ESCALONAMENTO PARA ELETROPOSTO")
print("=" * 80)

# Escalar demanda da Geórgia (18,000 MWh/dia) para eletroposto (ex: 5 MWh/dia)
fator_escala = 5.0 / perfil_verao.sum()  # Escalar para 5 MWh/dia

print(f"\nCenário exemplo: Eletroposto com demanda diária de 5 MWh")
print(f"Fator de escala: {fator_escala:.6f}")

demanda_eletroposto = perfil_verao * fator_escala * 1000  # Converter para kWh

print(f"\nDemanda do Eletroposto (kWh por hora):")
print(pd.DataFrame({
    'Hora': range(1, 25),
    'Demanda_kWh': demanda_eletroposto.values
}).to_string(index=False))

print(f"\nTotal diário: {demanda_eletroposto.sum():.2f} kWh")
print(f"Pico: {demanda_eletroposto.max():.2f} kWh (hora {demanda_eletroposto.idxmax()})")
print(f"Mínimo: {demanda_eletroposto.min():.2f} kWh (hora {demanda_eletroposto.idxmin()})")

# Capacidade PV exemplo (500 kWp)
capacidade_pv = 500  # kWp
geracao_pv = df_solar['irradiancia_norm'] * capacidade_pv

print(f"\nGeração PV com {capacidade_pv} kWp instalado:")
print(pd.DataFrame({
    'Hora': range(1, 25),
    'Geracao_kW': geracao_pv.values
}).to_string(index=False))

print(f"\nTotal gerado: {geracao_pv.sum():.2f} kWh/dia")
print(f"Fator de capacidade: {(geracao_pv.sum()/(capacidade_pv*24)):.2%}")

# 6. RESUMO DOS DADOS DISPONÍVEIS
print("\n" + "=" * 80)
print("6. RESUMO - DADOS PARA O MODELO DE ELETROPOSTO")
print("=" * 80)

print("""
DADOS HISTÓRICOS DISPONÍVEIS:

1. DEMANDA (Power Generation Example)
   - Período: 2004-2013, meses de Janeiro (inverno) e Julho (verão)
   - Resolução: Horária (24h por dia, 31 dias por mês)
   - Formato: YEAR, MONTH, DAY, HOUR, LOAD (MWh)
   - Uso: Escalar proporcionalmente para demanda do eletroposto
   
2. TARIFAS (Time-of-Use simulada)
   - Ponta (18-21h): $0.25/kWh
   - Intermediário (7-18h, 21-23h): $0.15/kWh
   - Fora-ponta (0-7h): $0.08/kWh
   - Uso: Receita por kWh carregado (pode ser ajustado para BRL)
   
3. GERAÇÃO SOLAR PV (Perfil normalizado)
   - Curva senoidal 6h-18h
   - Fator de capacidade: ~21%
   - Uso: Multiplicar por capacidade PV instalada (kWp)

ADAPTAÇÃO PARA ELETROPOSTO:
- Definir demanda alvo diária (ex: 5 MWh/dia)
- Escalar perfis horários proporcionalmente
- Manter padrões relativos de demanda por hora
- Considerar sazonalidade (verão vs inverno)
""")

# Salvar dados processados
print("\nSalvando dados processados...")
perfil_verao.to_csv('perfil_demanda_verao.csv')
perfil_inverno.to_csv('perfil_demanda_inverno.csv')
df_tarifas.to_csv('tarifas_tou.csv', index=False)
df_solar.to_csv('perfil_solar_norm.csv', index=False)

# Exemplo de demanda escalonada
demanda_exemplo = pd.DataFrame({
    'hora': range(1, 25),
    'demanda_kWh': demanda_eletroposto.values,
    'geracao_pv_kW': geracao_pv.values
})
demanda_exemplo.to_csv('exemplo_eletroposto.csv', index=False)

print("Arquivos salvos:")
print("  - perfil_demanda_verao.csv")
print("  - perfil_demanda_inverno.csv")
print("  - tarifas_tou.csv")
print("  - perfil_solar_norm.csv")
print("  - exemplo_eletroposto.csv")

print("\n" + "=" * 80)
print("EXPLORAÇÃO CONCLUÍDA!")
print("=" * 80)
