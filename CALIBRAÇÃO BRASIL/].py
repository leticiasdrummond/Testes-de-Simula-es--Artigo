"""
Validação e Melhorias da Simulação de Eletroposto
Baseado em dados reais do mercado brasileiro (ABVE, EPE, operadores)

Este módulo complementa o código original com:
1. Ajuste da proporção AC/DC para refletir mercado real (84% AC, 16% DC)
2. Curva de carregamento não-linear (realística)
3. Validação analítica usando modelo M/M/s (teoria de filas)
4. Comparação com benchmarks de mercado
5. Análise econômica baseada em dados reais

Referências:
- ABVE (2025): Dados de infraestrutura e frota brasileira
- EPE PDE 2035: Projeções oficiais
- Shell Recharge, EDP, CPFL: Dados operacionais
- Zhao et al. (2016), Xi et al. (2013): Teoria de filas para VE
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import numpy as np


# ============================================================================
# 1. AJUSTE: Proporção AC/DC baseada em mercado real
# ============================================================================

def charger_park_by_year_adjusted(year: int) -> Dict[str, int]:
    """
    Proporção ajustada para refletir mercado brasileiro real:
    - 84% AC (lentos)
    - 16% DC (rápidos)
    
    Fonte: ABVE (fev/2025) - 14.827 eletropostos no Brasil
    """
    # Classe auxiliar para tecnologias
    @dataclass(frozen=True)
    class ChargerTech:
        name: str
        power_kw: float
        is_dc: bool
    
    ac_7 = ChargerTech("AC_7kW", 7.4, False)
    ac_22 = ChargerTech("AC_22kW", 22.0, False)
    dc_60 = ChargerTech("DC_60kW", 60.0, True)
    dc_120 = ChargerTech("DC_120kW", 120.0, True)
    
    if year <= 2026:
        # Ajustado: 84% AC, 16% DC
        return {
            ac_7: 7,     # 58%
            ac_22: 3,    # 25%
            dc_60: 1,    # 8%
            dc_120: 1    # 8%
        }  # Total: 12 carregadores
    
    if year <= 2030:
        return {
            ac_7: 8,     # 53%
            ac_22: 5,    # 33%
            dc_60: 1,    # 7%
            dc_120: 1    # 7%
        }  # Total: 15 carregadores
    
    return {
        ac_7: 8,     # 47%
        ac_22: 6,    # 35%
        dc_60: 2,    # 12%
        dc_120: 1    # 6%
    }  # Total: 17 carregadores


# ============================================================================
# 2. MELHORIA: Curva de carregamento não-linear
# ============================================================================

def realistic_charging_power(
    soc_current: float,
    soc_target: float,
    max_power_kw: float,
    is_dc: bool
) -> float:
    """
    Potência de carregamento realística (não-linear).
    
    Comportamento real de baterias:
    - 0-20%: Potência reduzida (proteção bateria fria/baixa)
    - 20-80%: Potência máxima
    - 80-100%: Redução progressiva (proteção bateria cheia)
    
    Referências:
    - Dados técnicos fabricantes (Tesla, BYD, etc.)
    - Estudos CPFL EMotive (2013-2018)
    """
    if soc_current < 0.20:
        # Fase inicial: 85% da potência máxima
        return max_power_kw * 0.85
    
    elif soc_current < 0.80:
        # Fase rápida: potência máxima
        return max_power_kw
    
    else:
        # Fase final: redução linear
        # 80% → 100%: potência cai de 100% → 30%
        reduction_factor = 1.0 - ((soc_current - 0.80) / 0.20) * 0.70
        return max_power_kw * reduction_factor


def calculate_charging_time_realistic(
    energy_need_kwh: float,
    battery_kwh: float,
    soc_arrival: float,
    max_power_kw: float,
    is_dc: bool,
    efficiency: float = 0.93
) -> float:
    """
    Calcula tempo de carregamento considerando curva não-linear.
    
    Retorna tempo em minutos.
    """
    soc_current = soc_arrival
    soc_target = soc_arrival + (energy_need_kwh / battery_kwh)
    soc_target = min(1.0, soc_target)
    
    energy_charged = 0.0
    time_minutes = 0.0
    dt_minutes = 1.0  # Passo de simulação: 1 minuto
    
    while energy_charged < energy_need_kwh and soc_current < soc_target:
        # Potência instantânea
        power_kw = realistic_charging_power(soc_current, soc_target, max_power_kw, is_dc)
        
        # Energia carregada neste passo
        energy_step = (power_kw * efficiency) * (dt_minutes / 60.0)
        energy_charged += energy_step
        
        # Atualiza SOC
        soc_current += energy_step / battery_kwh
        soc_current = min(1.0, soc_current)
        
        time_minutes += dt_minutes
        
        # Segurança: máximo 4 horas
        if time_minutes > 240:
            break
    
    return time_minutes


# ============================================================================
# 3. VALIDAÇÃO ANALÍTICA: Modelo M/M/s (Teoria de Filas)
# ============================================================================

def erlang_c(lambda_rate: float, mu_rate: float, s: int) -> float:
    """
    Fórmula de Erlang C: probabilidade de espera em fila M/M/s
    
    Parâmetros:
    - lambda_rate: taxa de chegada (veículos/hora)
    - mu_rate: taxa de serviço (veículos/hora)
    - s: número de servidores (carregadores)
    
    Referência: Zhao et al. (2016), Xi et al. (2013)
    """
    rho = lambda_rate / (s * mu_rate)
    
    if rho >= 1.0:
        return 1.0  # Sistema instável
    
    # Termo A = (λ/μ)^s / s!
    a = lambda_rate / mu_rate
    term_s = (a ** s) / math.factorial(s)
    
    # Soma dos termos n=0 até s-1
    sum_terms = sum((a ** n) / math.factorial(n) for n in range(s))
    
    # P0 (probabilidade de sistema vazio)
    p0 = 1.0 / (sum_terms + term_s / (1 - rho))
    
    # Erlang C: P(espera > 0)
    erlang_c = (term_s / (1 - rho)) * p0
    
    return erlang_c


def mm_s_queue_metrics(
    lambda_rate: float,
    avg_service_time_hours: float,
    n_servers: int
) -> Dict[str, float]:
    """
    Métricas analíticas do modelo M/M/s.
    
    Retorna:
    - utilization: ρ (fator de utilização)
    - prob_wait: P(espera > 0) [Erlang C]
    - avg_queue_length: L_q (comprimento médio da fila)
    - avg_wait_time_min: W_q (tempo médio de espera em minutos)
    - avg_system_time_min: W (tempo total no sistema)
    
    Referência:
    - Kendall notation: M/M/s/∞/∞/FIFO
    - Zhao, H. et al. (2016): "Queueing models for EV charging"
    """
    mu_rate = 1.0 / avg_service_time_hours
    rho = lambda_rate / (n_servers * mu_rate)
    
    if rho >= 1.0:
        return {
            "utilization": rho,
            "prob_wait": 1.0,
            "avg_queue_length": float('inf'),
            "avg_wait_time_min": float('inf'),
            "avg_system_time_min": float('inf'),
            "status": "UNSTABLE"
        }
    
    # Erlang C
    prob_wait = erlang_c(lambda_rate, mu_rate, n_servers)
    
    # Comprimento médio da fila
    L_q = prob_wait * rho / (1 - rho)
    
    # Tempo médio de espera (horas)
    W_q = L_q / lambda_rate
    
    # Tempo total no sistema
    W = W_q + avg_service_time_hours
    
    return {
        "utilization": rho,
        "prob_wait": prob_wait,
        "avg_queue_length": L_q,
        "avg_wait_time_min": W_q * 60.0,
        "avg_system_time_min": W * 60.0,
        "status": "STABLE"
    }


# ============================================================================
# 4. BENCHMARKS DE MERCADO
# ============================================================================

@dataclass
class MarketBenchmark:
    """Dados reais de operadores brasileiros e internacionais"""
    
    # Brasil (ABVE 2025)
    total_chargers_brazil: int = 14827
    chargers_ac_percent: float = 0.84
    chargers_dc_percent: float = 0.16
    
    # Frota (ABVE 2025)
    fleet_bev: int = 93082
    fleet_phev: int = 115262
    vehicles_per_charger: float = 14.0
    vehicles_per_charger_bev_only: float = 6.0
    
    # Shell Recharge China (maior eletroposto)
    shell_china_chargers: int = 258
    shell_china_vehicles_per_day: int = 3300
    shell_china_vehicles_per_charger_per_day: float = 12.8
    
    # Shell Recharge Brasil
    shell_br_price_per_kwh: float = 2.40
    shell_br_dc_power_kw: float = 180.0
    
    # EDP Brasil (Espírito Santo)
    edp_avg_charging_time_min: float = 90.0
    
    # Mercado geral Brasil
    price_range_kwh: Tuple[float, float] = (0.30, 2.40)
    avg_price_kwh: float = 1.80
    
    # EPE PDE 2035
    epe_fleet_2035: int = 3_700_000
    epe_ev_market_share_2035: float = 0.23


def compare_with_benchmarks(
    simulation_results: Dict,
    n_chargers: int,
    daily_arrivals: int
) -> Dict[str, any]:
    """
    Compara resultados da simulação com benchmarks de mercado.
    """
    bench = MarketBenchmark()
    
    vehicles_per_charger_per_day = daily_arrivals / n_chargers
    
    # Desvio percentual
    deviation_shell = abs(
        vehicles_per_charger_per_day - bench.shell_china_vehicles_per_charger_per_day
    ) / bench.shell_china_vehicles_per_charger_per_day
    
    return {
        "simulation_vehicles_per_charger_day": vehicles_per_charger_per_day,
        "benchmark_shell_china": bench.shell_china_vehicles_per_charger_per_day,
        "deviation_percent": deviation_shell * 100,
        "status": "REALISTIC" if deviation_shell < 0.30 else "REVIEW_NEEDED",
        
        "chargers_ac_percent_sim": sum(1 for c in simulation_results.get('chargers', []) 
                                       if not c.get('is_dc', False)) / n_chargers,
        "chargers_ac_percent_market": bench.chargers_ac_percent,
        
        "avg_charging_time_sim": simulation_results.get('avg_charging_time_min', 0),
        "benchmark_edp": bench.edp_avg_charging_time_min,
    }


# ============================================================================
# 5. ANÁLISE ECONÔMICA (dados reais Brasil)
# ============================================================================

@dataclass
class EconomicData:
    """
    Custos reais de implantação no Brasil.
    Fonte: Estudos USP/Lactec (2024), Evowatt
    """
    # CAPEX (investimento inicial)
    capex_ac_per_charger: Tuple[float, float] = (12500, 20000)  # R$ por carregador AC
    capex_dc_per_charger: Tuple[float, float] = (135000, 370000)  # R$ por carregador DC
    
    # OPEX (operacional anual)
    opex_software_annual: Tuple[float, float] = (2000, 8000)
    opex_maintenance_percent: float = 0.05  # 5% do CAPEX/ano
    
    # Receita
    price_per_kwh: float = 1.80  # R$/kWh (média mercado)
    avg_energy_per_session_kwh: float = 25.0
    
    # Amortização
    amortization_years: int = 10


def economic_analysis(
    total_energy_kwh: float,
    n_chargers_ac: int,
    n_chargers_dc: int,
    daily_sessions: int,
    price_per_kwh: float = 1.80
) -> Dict[str, float]:
    """
    Análise de viabilidade econômica baseada em dados reais.
    """
    econ = EconomicData()
    
    # CAPEX
    capex_ac = n_chargers_ac * sum(econ.capex_ac_per_charger) / 2
    capex_dc = n_chargers_dc * sum(econ.capex_dc_per_charger) / 2
    total_capex = capex_ac + capex_dc
    
    # OPEX diário
    opex_annual = (
        sum(econ.opex_software_annual) / 2 +
        total_capex * econ.opex_maintenance_percent
    )
    opex_daily = opex_annual / 365
    
    # Receita diária
    revenue_daily = total_energy_kwh * price_per_kwh
    
    # Lucro
    profit_daily = revenue_daily - opex_daily
    profit_annual = profit_daily * 365
    
    # ROI
    roi_years = total_capex / profit_annual if profit_annual > 0 else float('inf')
    
    # Ponto de equilíbrio
    breakeven_energy_kwh = opex_daily / price_per_kwh
    breakeven_sessions = breakeven_energy_kwh / econ.avg_energy_per_session_kwh
    
    return {
        "capex_total_brl": total_capex,
        "opex_annual_brl": opex_annual,
        "opex_daily_brl": opex_daily,
        "revenue_daily_brl": revenue_daily,
        "profit_daily_brl": profit_daily,
        "profit_annual_brl": profit_annual,
        "roi_years": roi_years,
        "breakeven_sessions_per_day": breakeven_sessions,
        "revenue_per_charger_brl": revenue_daily / (n_chargers_ac + n_chargers_dc),
        "status": "VIABLE" if roi_years <= 5 else "REVIEW_NEEDED"
    }


# ============================================================================
# 6. VISUALIZAÇÕES COMPARATIVAS
# ============================================================================

def plot_charging_curve_comparison():
    """
    Compara curva linear (original) vs. realística (não-linear)
    """
    soc_range = np.linspace(0.0, 1.0, 100)
    max_power = 120.0  # kW
    
    # Curva linear (original)
    power_linear = [max_power] * len(soc_range)
    
    # Curva realística
    power_realistic = [
        realistic_charging_power(soc, 1.0, max_power, is_dc=True)
        for soc in soc_range
    ]
    
    plt.figure(figsize=(10, 6))
    plt.plot(soc_range * 100, power_linear, 'r--', 
             label='Linear (original)', linewidth=2)
    plt.plot(soc_range * 100, power_realistic, 'b-', 
             label='Realística (melhorada)', linewidth=2)
    plt.xlabel('Estado de Carga (SOC) [%]', fontsize=12)
    plt.ylabel('Potência de Carregamento [kW]', fontsize=12)
    plt.title('Comparação: Curva de Carregamento Linear vs. Realística', 
              fontsize=14, fontweight='bold')
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.xlim(0, 100)
    plt.ylim(0, max_power * 1.1)
    
    # Destacar zonas
    plt.axvspan(0, 20, alpha=0.1, color='orange', label='Proteção inicial')
    plt.axvspan(20, 80, alpha=0.1, color='green', label='Carregamento rápido')
    plt.axvspan(80, 100, alpha=0.1, color='red', label='Proteção final')
    
    plt.tight_layout()
    plt.savefig('curva_carregamento_comparacao.png', dpi=300)
    print("✓ Gráfico salvo: curva_carregamento_comparacao.png")


def plot_market_comparison(sim_data: Dict, market_data: Dict):
    """
    Gráfico comparativo: Simulação vs. Mercado Real
    """
    categories = ['Veículos/Carregador/Dia', 'AC %', 'Tempo Médio (min)']
    
    sim_values = [
        sim_data['vehicles_per_charger_day'],
        sim_data['ac_percent'] * 100,
        sim_data['avg_charging_time_min']
    ]
    
    market_values = [
        market_data['shell_china_benchmark'],
        market_data['ac_percent_market'] * 100,
        market_data['edp_avg_time']
    ]
    
    x = np.arange(len(categories))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(12, 6))
    bars1 = ax.bar(x - width/2, sim_values, width, label='Simulação', color='steelblue')
    bars2 = ax.bar(x + width/2, market_values, width, label='Mercado Real', color='coral')
    
    ax.set_ylabel('Valor', fontsize=12)
    ax.set_title('Comparação: Simulação vs. Dados Reais de Mercado (Brasil)', 
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    
    # Anotações
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.1f}',
                   ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    plt.savefig('comparacao_mercado.png', dpi=300)
    print("✓ Gráfico salvo: comparacao_mercado.png")


# ============================================================================
# 7. EXEMPLO DE USO
# ============================================================================

def main_validation_example():
    """
    Exemplo de uso das funções de validação
    """
    print("=" * 70)
    print("VALIDAÇÃO DA SIMULAÇÃO COM DADOS DE MERCADO BRASILEIRO")
    print("=" * 70)
    print()
    
    # 1. Validação analítica M/M/s
    print("1. VALIDAÇÃO ANALÍTICA (Modelo M/M/s)")
    print("-" * 70)
    
    lambda_rate = 160 / 24  # 160 veículos/dia = 6.67 veículos/hora
    avg_service_time = 1.5  # 1.5 horas (90 minutos médio)
    n_servers = 12
    
    metrics = mm_s_queue_metrics(lambda_rate, avg_service_time, n_servers)
    
    print(f"Taxa de chegada: {lambda_rate:.2f} veículos/hora")
    print(f"Tempo médio de serviço: {avg_service_time:.2f} horas")
    print(f"Número de carregadores: {n_servers}")
    print(f"Status: {metrics['status']}")
    print(f"Utilização (ρ): {metrics['utilization']:.2%}")
    print(f"Prob. de espera: {metrics['prob_wait']:.2%}")
    print(f"Fila média: {metrics['avg_queue_length']:.2f} veículos")
    print(f"Tempo médio de espera: {metrics['avg_wait_time_min']:.1f} minutos")
    print()
    
    # 2. Comparação com benchmarks
    print("2. COMPARAÇÃO COM BENCHMARKS DE MERCADO")
    print("-" * 70)
    
    bench = MarketBenchmark()
    print(f"Shell Recharge China: {bench.shell_china_vehicles_per_charger_per_day:.1f} veículos/carregador/dia")
    print(f"Simulação (160 chegadas / 12 carregadores): {160/12:.1f} veículos/carregador/dia")
    print(f"Desvio: {abs(160/12 - bench.shell_china_vehicles_per_charger_per_day)/bench.shell_china_vehicles_per_charger_per_day * 100:.1f}%")
    print()
    print(f"Proporção AC/DC mercado: {bench.chargers_ac_percent:.0%} AC / {bench.chargers_dc_percent:.0%} DC")
    print(f"Proporção ajustada simulação: 83% AC / 17% DC ✓")
    print()
    
    # 3. Análise econômica
    print("3. ANÁLISE DE VIABILIDADE ECONÔMICA")
    print("-" * 70)
    
    total_energy = 160 * 25  # 160 sessões × 25 kWh médio
    econ = economic_analysis(
        total_energy_kwh=total_energy,
        n_chargers_ac=10,
        n_chargers_dc=2,
        daily_sessions=160
    )
    
    print(f"CAPEX total: R$ {econ['capex_total_brl']:,.2f}")
    print(f"OPEX anual: R$ {econ['opex_annual_brl']:,.2f}")
    print(f"Receita diária: R$ {econ['revenue_daily_brl']:,.2f}")
    print(f"Lucro diário: R$ {econ['profit_daily_brl']:,.2f}")
    print(f"ROI: {econ['roi_years']:.1f} anos")
    print(f"Ponto de equilíbrio: {econ['breakeven_sessions_per_day']:.0f} sessões/dia")
    print(f"Status: {econ['status']}")
    print()
    
    # 4. Exemplo de curva realística
    print("4. EXEMPLO: CURVA DE CARREGAMENTO REALÍSTICA")
    print("-" * 70)
    
    battery_kwh = 68.0
    soc_arrival = 0.25
    energy_need = 40.0  # kWh
    max_power = 120.0  # kW
    
    time_linear = (energy_need / (max_power * 0.93)) * 60
    time_realistic = calculate_charging_time_realistic(
        energy_need, battery_kwh, soc_arrival, max_power, is_dc=True
    )
    
    print(f"Necessidade: {energy_need:.1f} kWh")
    print(f"SOC inicial: {soc_arrival:.0%}")
    print(f"Potência máxima: {max_power:.0f} kW")
    print(f"Tempo (linear): {time_linear:.1f} minutos")
    print(f"Tempo (realístico): {time_realistic:.1f} minutos")
    print(f"Diferença: {time_realistic - time_linear:.1f} minutos (+{(time_realistic/time_linear - 1)*100:.1f}%)")
    print()
    
    # 5. Gerar visualizações
    print("5. GERANDO VISUALIZAÇÕES")
    print("-" * 70)
    plot_charging_curve_comparison()
    print()
    
    print("=" * 70)
    print("VALIDAÇÃO CONCLUÍDA!")
    print("=" * 70)


if __name__ == "__main__":
    main_validation_example()
