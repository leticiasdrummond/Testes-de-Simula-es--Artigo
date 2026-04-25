"""
Modelo de Otimização e Análise de Investimento em Microrrede com PV-BESS-Rede
para Eletroposto em Rodovia

Objetivo: Induzir decisões de investimento através de análise comparativa de cenários
variando CAPEX, horizonte de avaliação e diferenciais tarifários.

Métricas de análise:
- Lucratividade: ROI, Payback, Margem de Lucro, VPL
- Mercado: Sensibilidade a preços, Competitividade tarifária, Exposição à volatilidade
- Operações: Utilização de ativos, Autossuficiência energética, Eficiência BESS
"""

from pathlib import Path
from typing import Dict, List, Tuple
import gurobipy as gp
from gurobipy import GRB


class MicroGridOptimizer:
    """Otimizador de microrrede PV-BESS-Rede para eletroposto."""
    
    def __init__(self, env: gp.Env):
        """Inicializa otimizador com ambiente Gurobi."""
        self.env = env
        self.model = None
        
        # Parâmetros do modelo
        self.T = 24  # Horizonte horário
        self.delta_t = 1.0  # horas
        
        # Parâmetros econômicos
        self.operational_days = 365.0
        self.tariff_ev = 0.0
        self.export_price_factor = 0.7
        self.discount_rate = 0.10  # Taxa de desconto para VPL
        
        # CAPEX (BRL por unidade)
        self.capex_pv_kw = 0.0
        self.capex_bess_kwh = 0.0
        self.capex_trafo_kw = 0.0
        
        # Parâmetros técnicos BESS
        self.eta_charge = 0.95
        self.eta_discharge = 0.95
        self.soc_min_frac = 0.20
        self.soc_max_frac = 0.90
        self.soc_initial_frac = 0.50
        self.c_rate_charge = 0.5
        self.c_rate_discharge = 0.5
        
        # Séries horárias
        self.irradiance_cf = []
        self.grid_price = []
        self.p_ev_load = []
        
        # Variáveis e resultados
        self.vars = {}
        self.results = {}
    
    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager e dispose model."""
        if self.model is not None:
            self.model.dispose()
        return False
    
    def set_data(self, data: Dict):
        """Define dados do problema."""
        # Parâmetros econômicos
        self.operational_days = data.get('operational_days', 365.0)
        self.tariff_ev = data['tariff_ev']
        self.export_price_factor = data.get('export_price_factor', 0.7)
        self.discount_rate = data.get('discount_rate', 0.10)
        
        # CAPEX
        self.capex_pv_kw = data['capex_pv_kw']
        self.capex_bess_kwh = data['capex_bess_kwh']
        self.capex_trafo_kw = data['capex_trafo_kw']
        
        # Parâmetros técnicos
        self.eta_charge = data.get('eta_charge', 0.95)
        self.eta_discharge = data.get('eta_discharge', 0.95)
        self.soc_min_frac = data.get('soc_min_frac', 0.20)
        self.soc_max_frac = data.get('soc_max_frac', 0.90)
        self.soc_initial_frac = data.get('soc_initial_frac', 0.50)
        self.c_rate_charge = data.get('c_rate_charge', 0.5)
        self.c_rate_discharge = data.get('c_rate_discharge', 0.5)
        
        # Séries horárias
        self.irradiance_cf = data['irradiance_cf']
        self.grid_price = data['grid_price']
        self.p_ev_load = data['p_ev_load']
        
        self.T = len(self.irradiance_cf)
    
    def build_model(self):
        """Constrói modelo de otimização."""
        self.model = gp.Model("MicroGridOptimization", env=self.env)
        
        self._create_variables()
        self._add_constraints()
        self._set_objective()
    
    def _create_variables(self):
        """Cria variáveis de decisão."""
        m = self.model
        
        # Variáveis de investimento (capacidades)
        self.vars['P_pv_cap'] = m.addVar(name="P_pv_cap", lb=0)
        self.vars['E_bess_cap'] = m.addVar(name="E_bess_cap", lb=0)
        self.vars['P_trafo_cap'] = m.addVar(name="P_trafo_cap", lb=0)
        
        # Variáveis operacionais horárias
        self.vars['P_pv_gen'] = m.addVars(self.T, name="P_pv_gen", lb=0)
        self.vars['P_grid_import'] = m.addVars(self.T, name="P_grid_import", lb=0)
        self.vars['P_grid_export'] = m.addVars(self.T, name="P_grid_export", lb=0)
        self.vars['P_bess_charge'] = m.addVars(self.T, name="P_bess_charge", lb=0)
        self.vars['P_bess_discharge'] = m.addVars(self.T, name="P_bess_discharge", lb=0)
        self.vars['SOC'] = m.addVars(self.T, name="SOC", lb=0)
        
        m.update()
    
    def _add_constraints(self):
        """Adiciona restrições ao modelo."""
        m = self.model
        
        # Limites de geração PV
        for t in range(self.T):
            m.addConstr(
                self.vars['P_pv_gen'][t] <= self.vars['P_pv_cap'] * self.irradiance_cf[t],
                name=f"PV_limit_{t}"
            )
        
        # Limites do transformador
        for t in range(self.T):
            m.addConstr(
                self.vars['P_grid_import'][t] <= self.vars['P_trafo_cap'],
                name=f"Trafo_import_{t}"
            )
            m.addConstr(
                self.vars['P_grid_export'][t] <= self.vars['P_trafo_cap'],
                name=f"Trafo_export_{t}"
            )
        
        # Limites de potência do BESS
        for t in range(self.T):
            m.addConstr(
                self.vars['P_bess_charge'][t] <= self.c_rate_charge * self.vars['E_bess_cap'],
                name=f"BESS_charge_limit_{t}"
            )
            m.addConstr(
                self.vars['P_bess_discharge'][t] <= self.c_rate_discharge * self.vars['E_bess_cap'],
                name=f"BESS_discharge_limit_{t}"
            )
        
        # Limites de SOC
        for t in range(self.T):
            m.addConstr(
                self.vars['SOC'][t] >= self.soc_min_frac * self.vars['E_bess_cap'],
                name=f"SOC_min_{t}"
            )
            m.addConstr(
                self.vars['SOC'][t] <= self.soc_max_frac * self.vars['E_bess_cap'],
                name=f"SOC_max_{t}"
            )
        
        # Dinâmica do SOC
        for t in range(self.T):
            if t == 0:
                m.addConstr(
                    self.vars['SOC'][t] == self.soc_initial_frac * self.vars['E_bess_cap'] +
                    self.delta_t * (
                        self.eta_charge * self.vars['P_bess_charge'][t] -
                        self.vars['P_bess_discharge'][t] / self.eta_discharge
                    ),
                    name=f"SOC_balance_{t}"
                )
            else:
                m.addConstr(
                    self.vars['SOC'][t] == self.vars['SOC'][t-1] +
                    self.delta_t * (
                        self.eta_charge * self.vars['P_bess_charge'][t] -
                        self.vars['P_bess_discharge'][t] / self.eta_discharge
                    ),
                    name=f"SOC_balance_{t}"
                )
        
        # Condição cíclica: SOC final = SOC inicial
        m.addConstr(
            self.vars['SOC'][self.T-1] == self.soc_initial_frac * self.vars['E_bess_cap'],
            name="SOC_cyclic"
        )
        
        # Balanço de energia: Fontes = Demanda + Armazenamento + Exportação
        for t in range(self.T):
            m.addConstr(
                self.vars['P_pv_gen'][t] + self.vars['P_grid_import'][t] + 
                self.vars['P_bess_discharge'][t] ==
                self.p_ev_load[t] + self.vars['P_bess_charge'][t] + 
                self.vars['P_grid_export'][t],
                name=f"Energy_balance_{t}"
            )
    
    def _set_objective(self):
        """Define função objetivo: maximizar lucro líquido."""
        m = self.model
        
        # Receita com recarga de VE
        daily_revenue_ev = gp.quicksum(
            self.tariff_ev * self.p_ev_load[t] * self.delta_t
            for t in range(self.T)
        )
        
        # Receita com exportação para rede
        daily_revenue_export = gp.quicksum(
            self.export_price_factor * self.grid_price[t] * 
            self.vars['P_grid_export'][t] * self.delta_t
            for t in range(self.T)
        )
        
        # Custo de importação da rede
        daily_cost_import = gp.quicksum(
            self.grid_price[t] * self.vars['P_grid_import'][t] * self.delta_t
            for t in range(self.T)
        )
        
        # Lucro operacional diário
        daily_profit = daily_revenue_ev + daily_revenue_export - daily_cost_import
        
        # Lucro operacional anualizado
        annual_profit = self.operational_days * daily_profit
        
        # CAPEX total
        capex_total = (
            self.capex_pv_kw * self.vars['P_pv_cap'] +
            self.capex_bess_kwh * self.vars['E_bess_cap'] +
            self.capex_trafo_kw * self.vars['P_trafo_cap']
        )
        
        # Objetivo: maximizar lucro líquido (lucro anual - CAPEX)
        m.setObjective(annual_profit - capex_total, GRB.MAXIMIZE)
    
    def solve(self) -> str:
        """Resolve o modelo e retorna status."""
        self.model.optimize()
        
        if self.model.status == GRB.OPTIMAL:
            self._extract_solution()
            return "OPTIMAL"
        elif self.model.status == GRB.INFEASIBLE:
            return "INFEASIBLE"
        elif self.model.status == GRB.UNBOUNDED:
            return "UNBOUNDED"
        else:
            return f"OTHER: {self.model.status}"
    
    def _extract_solution(self):
        """Extrai solução do modelo."""
        # Capacidades otimizadas
        self.results['P_pv_cap'] = self.vars['P_pv_cap'].X
        self.results['E_bess_cap'] = self.vars['E_bess_cap'].X
        self.results['P_trafo_cap'] = self.vars['P_trafo_cap'].X
        
        # Valor objetivo
        self.results['obj_value'] = self.model.ObjVal
        
        # Séries operacionais
        self.results['P_pv_gen'] = [self.vars['P_pv_gen'][t].X for t in range(self.T)]
        self.results['P_grid_import'] = [self.vars['P_grid_import'][t].X for t in range(self.T)]
        self.results['P_grid_export'] = [self.vars['P_grid_export'][t].X for t in range(self.T)]
        self.results['P_bess_charge'] = [self.vars['P_bess_charge'][t].X for t in range(self.T)]
        self.results['P_bess_discharge'] = [self.vars['P_bess_discharge'][t].X for t in range(self.T)]
        self.results['SOC'] = [self.vars['SOC'][t].X for t in range(self.T)]
        
        # Calcula métricas derivadas
        self._calculate_metrics()
    
    def _calculate_metrics(self):
        """Calcula métricas de performance e mercado."""
        # CAPEX total
        capex_total = (
            self.capex_pv_kw * self.results['P_pv_cap'] +
            self.capex_bess_kwh * self.results['E_bess_cap'] +
            self.capex_trafo_kw * self.results['P_trafo_cap']
        )
        self.results['capex_total'] = capex_total
        
        # Receitas e custos diários
        daily_revenue_ev = sum(
            self.tariff_ev * self.p_ev_load[t] * self.delta_t
            for t in range(self.T)
        )
        
        daily_revenue_export = sum(
            self.export_price_factor * self.grid_price[t] * 
            self.results['P_grid_export'][t] * self.delta_t
            for t in range(self.T)
        )
        
        daily_cost_import = sum(
            self.grid_price[t] * self.results['P_grid_import'][t] * self.delta_t
            for t in range(self.T)
        )
        
        daily_profit = daily_revenue_ev + daily_revenue_export - daily_cost_import
        
        self.results['daily_revenue_ev'] = daily_revenue_ev
        self.results['daily_revenue_export'] = daily_revenue_export
        self.results['daily_cost_import'] = daily_cost_import
        self.results['daily_profit'] = daily_profit
        
        # Métricas anualizadas
        annual_profit = self.operational_days * daily_profit
        self.results['annual_profit'] = annual_profit
        
        annual_revenue = self.operational_days * (daily_revenue_ev + daily_revenue_export)
        self.results['annual_revenue'] = annual_revenue
        
        # Métricas de lucratividade
        if capex_total > 0:
            self.results['roi'] = (annual_profit / capex_total) * 100  # %
            self.results['payback_years'] = capex_total / annual_profit if annual_profit > 0 else float('inf')
        else:
            self.results['roi'] = 0.0
            self.results['payback_years'] = 0.0
        
        if annual_revenue > 0:
            self.results['profit_margin'] = (annual_profit / annual_revenue) * 100  # %
        else:
            self.results['profit_margin'] = 0.0
        
        # VPL simplificado (horizonte = payback * 1.5, ou 10 anos)
        horizon = min(10, max(5, int(self.results['payback_years'] * 1.5)))
        discount_factors = [(1 + self.discount_rate) ** -i for i in range(1, horizon + 1)]
        vpn = sum(annual_profit * df for df in discount_factors) - capex_total
        self.results['vpn'] = vpn
        
        # Métricas de mercado
        total_energy_demand = sum(self.p_ev_load[t] * self.delta_t for t in range(self.T))
        total_energy_import = sum(self.results['P_grid_import'][t] * self.delta_t for t in range(self.T))
        total_energy_export = sum(self.results['P_grid_export'][t] * self.delta_t for t in range(self.T))
        total_energy_pv = sum(self.results['P_pv_gen'][t] * self.delta_t for t in range(self.T))
        
        # Exposição à rede (%)
        if total_energy_demand > 0:
            self.results['grid_exposure'] = (total_energy_import / total_energy_demand) * 100
        else:
            self.results['grid_exposure'] = 0.0
        
        # Autossuficiência (%)
        if total_energy_demand > 0:
            self.results['self_sufficiency'] = ((total_energy_demand - total_energy_import) / total_energy_demand) * 100
        else:
            self.results['self_sufficiency'] = 0.0
        
        # Taxa de exportação (%)
        if total_energy_pv > 0:
            self.results['export_rate'] = (total_energy_export / total_energy_pv) * 100
        else:
            self.results['export_rate'] = 0.0
        
        # Fator de capacidade PV (%)
        if self.results['P_pv_cap'] > 0:
            max_pv_generation = self.results['P_pv_cap'] * self.T * self.delta_t
            self.results['pv_capacity_factor'] = (total_energy_pv / max_pv_generation) * 100
        else:
            self.results['pv_capacity_factor'] = 0.0
        
        # Utilização do transformador (%)
        if self.results['P_trafo_cap'] > 0:
            max_trafo_usage = max(
                max(self.results['P_grid_import']),
                max(self.results['P_grid_export'])
            )
            self.results['trafo_utilization'] = (max_trafo_usage / self.results['P_trafo_cap']) * 100
        else:
            self.results['trafo_utilization'] = 0.0
        
        # Ciclos de bateria (ciclos/dia)
        total_discharge = sum(self.results['P_bess_discharge'][t] * self.delta_t for t in range(self.T))
        if self.results['E_bess_cap'] > 0:
            self.results['bess_cycles_per_day'] = total_discharge / self.results['E_bess_cap']
        else:
            self.results['bess_cycles_per_day'] = 0.0
        
        # Perdas no BESS (%)
        total_charge = sum(self.results['P_bess_charge'][t] * self.delta_t for t in range(self.T))
        if total_charge > 0:
            self.results['bess_losses'] = ((total_charge - total_discharge) / total_charge) * 100
        else:
            self.results['bess_losses'] = 0.0
        
        # Preço médio da rede
        self.results['avg_grid_price'] = sum(self.grid_price) / len(self.grid_price)
        
        # Diferencial tarifário (tarifa VE - preço médio rede)
        self.results['tariff_differential'] = self.tariff_ev - self.results['avg_grid_price']
        
        # Competitividade tarifária (%)
        if self.results['avg_grid_price'] > 0:
            self.results['tariff_competitiveness'] = (
                (self.tariff_ev - self.results['avg_grid_price']) / 
                self.results['avg_grid_price']
            ) * 100
        else:
            self.results['tariff_competitiveness'] = 0.0
    
    def get_results(self) -> Dict:
        """Retorna resultados da otimização."""
        return self.results


def run_scenario_analysis(base_data: Dict, output_dir: Path) -> List[Dict]:
    """
    Executa análise de múltiplos cenários variando:
    - CAPEX (redução de custos)
    - Dias operacionais equivalentes (horizonte de avaliação)
    - Diferencial tarifário (tarifa VE vs. preço da rede)
    """
    scenarios = []
    
    # Cenário Base
    scenarios.append({
        'name': 'Base',
        'capex_multiplier': 1.0,
        'operational_days': base_data['operational_days'],
        'tariff_multiplier': 1.0
    })
    
    # Cenários de CAPEX (redução de custos)
    for capex_mult in [0.7, 0.85, 1.15]:
        scenarios.append({
            'name': f'CAPEX_{int(capex_mult*100)}%',
            'capex_multiplier': capex_mult,
            'operational_days': base_data['operational_days'],
            'tariff_multiplier': 1.0
        })
    
    # Cenários de horizonte de avaliação
    for days in [180, 730]:  # 6 meses, 2 anos
        scenarios.append({
            'name': f'Horizonte_{days}dias',
            'capex_multiplier': 1.0,
            'operational_days': days,
            'tariff_multiplier': 1.0
        })
    
    # Cenários de diferencial tarifário
    for tariff_mult in [0.9, 1.1, 1.2]:
        scenarios.append({
            'name': f'TarifaVE_{int(tariff_mult*100)}%',
            'capex_multiplier': 1.0,
            'operational_days': base_data['operational_days'],
            'tariff_multiplier': tariff_mult
        })
    
    results_list = []
    
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag', 0)  # Desabilita log do solver
        env.start()
        
        for scenario in scenarios:
            print(f"Executando cenário: {scenario['name']}...")
            
            # Prepara dados do cenário
            scenario_data = base_data.copy()
            scenario_data['capex_pv_kw'] *= scenario['capex_multiplier']
            scenario_data['capex_bess_kwh'] *= scenario['capex_multiplier']
            scenario_data['capex_trafo_kw'] *= scenario['capex_multiplier']
            scenario_data['operational_days'] = scenario['operational_days']
            scenario_data['tariff_ev'] *= scenario['tariff_multiplier']
            
            # Otimiza
            with MicroGridOptimizer(env) as optimizer:
                optimizer.set_data(scenario_data)
                optimizer.build_model()
                status = optimizer.solve()
                
                if status == "OPTIMAL":
                    results = optimizer.get_results()
                    results['scenario_name'] = scenario['name']
                    results['scenario_params'] = scenario
                    results_list.append(results)
                else:
                    print(f"  AVISO: Cenário {scenario['name']} não encontrou solução ótima (status: {status})")
    
    return results_list


def write_comparative_report(results_list: List[Dict], output_path: Path):
    """Gera relatório comparativo de cenários."""
    with output_path.open('w', encoding='utf-8') as f:
        f.write("=" * 100 + "\n")
        f.write("ANÁLISE COMPARATIVA DE INVESTIMENTO EM MICRORREDE PV-BESS\n")
        f.write("Objetivo: Induzir Decisão de Investimento Otimizado\n")
        f.write("=" * 100 + "\n\n")
        
        # Tabela resumo de capacidades
        f.write("\n" + "=" * 100 + "\n")
        f.write("1. CAPACIDADES OTIMIZADAS POR CENÁRIO\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Cenário':<25} {'PV (kW)':>12} {'BESS (kWh)':>12} {'Trafo (kW)':>12} {'CAPEX (BRL)':>15}\n")
        f.write("-" * 100 + "\n")
        
        for res in results_list:
            f.write(
                f"{res['scenario_name']:<25} "
                f"{res['P_pv_cap']:>12.2f} "
                f"{res['E_bess_cap']:>12.2f} "
                f"{res['P_trafo_cap']:>12.2f} "
                f"{res['capex_total']:>15,.0f}\n"
            )
        
        # Tabela de lucratividade
        f.write("\n" + "=" * 100 + "\n")
        f.write("2. INDICADORES DE LUCRATIVIDADE\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Cenário':<25} {'Lucro Anual':>15} {'ROI (%)':>10} {'Payback (anos)':>15} {'VPL (BRL)':>15}\n")
        f.write("-" * 100 + "\n")
        
        for res in results_list:
            f.write(
                f"{res['scenario_name']:<25} "
                f"{res['annual_profit']:>15,.0f} "
                f"{res['roi']:>10.1f} "
                f"{res['payback_years']:>15.2f} "
                f"{res['vpn']:>15,.0f}\n"
            )
        
        # Tabela de mercado
        f.write("\n" + "=" * 100 + "\n")
        f.write("3. INDICADORES DE MERCADO\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Cenário':<25} {'Exp. Rede (%)':>14} {'Autossuf. (%)':>14} {'Compet. Tarif.(%)':>18} {'Dif. Tarif.(BRL/kWh)':>22}\n")
        f.write("-" * 100 + "\n")
        
        for res in results_list:
            f.write(
                f"{res['scenario_name']:<25} "
                f"{res['grid_exposure']:>14.1f} "
                f"{res['self_sufficiency']:>14.1f} "
                f"{res['tariff_competitiveness']:>18.1f} "
                f"{res['tariff_differential']:>22.3f}\n"
            )
        
        # Tabela de operações
        f.write("\n" + "=" * 100 + "\n")
        f.write("4. INDICADORES OPERACIONAIS\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'Cenário':<25} {'FC PV (%)':>12} {'Util. Trafo(%)':>15} {'Ciclos BESS/dia':>17} {'Perdas BESS(%)':>16}\n")
        f.write("-" * 100 + "\n")
        
        for res in results_list:
            f.write(
                f"{res['scenario_name']:<25} "
                f"{res['pv_capacity_factor']:>12.1f} "
                f"{res['trafo_utilization']:>15.1f} "
                f"{res['bess_cycles_per_day']:>17.2f} "
                f"{res['bess_losses']:>16.1f}\n"
            )
        
        # Análise de sensibilidade
        f.write("\n" + "=" * 100 + "\n")
        f.write("5. ANÁLISE DE SENSIBILIDADE E RECOMENDAÇÕES\n")
        f.write("=" * 100 + "\n\n")
        
        # Ordena por ROI
        sorted_by_roi = sorted(results_list, key=lambda x: x['roi'], reverse=True)
        f.write("5.1 Cenários Ordenados por ROI (Retorno sobre Investimento):\n")
        f.write("-" * 100 + "\n")
        for i, res in enumerate(sorted_by_roi[:5], 1):
            f.write(f"  {i}. {res['scenario_name']:<20} ROI: {res['roi']:>6.1f}%  Payback: {res['payback_years']:>5.2f} anos\n")
        
        # Ordena por Payback
        sorted_by_payback = sorted(
            [r for r in results_list if r['payback_years'] < float('inf')],
            key=lambda x: x['payback_years']
        )
        f.write("\n5.2 Cenários com Menor Payback:\n")
        f.write("-" * 100 + "\n")
        for i, res in enumerate(sorted_by_payback[:5], 1):
            f.write(f"  {i}. {res['scenario_name']:<20} Payback: {res['payback_years']:>5.2f} anos  ROI: {res['roi']:>6.1f}%\n")
        
        # Ordena por VPL
        sorted_by_vpn = sorted(results_list, key=lambda x: x['vpn'], reverse=True)
        f.write("\n5.3 Cenários com Maior Valor Presente Líquido (VPL):\n")
        f.write("-" * 100 + "\n")
        for i, res in enumerate(sorted_by_vpn[:5], 1):
            f.write(f"  {i}. {res['scenario_name']:<20} VPL: {res['vpn']:>12,.0f} BRL\n")
        
        # Análise de sensibilidade ao CAPEX
        f.write("\n5.4 Impacto da Redução de CAPEX:\n")
        f.write("-" * 100 + "\n")
        base_result = next((r for r in results_list if r['scenario_name'] == 'Base'), None)
        if base_result:
            capex_scenarios = [r for r in results_list if 'CAPEX' in r['scenario_name']]
            for res in sorted(capex_scenarios, key=lambda x: x['scenario_params']['capex_multiplier']):
                delta_roi = res['roi'] - base_result['roi']
                delta_payback = res['payback_years'] - base_result['payback_years']
                capex_mult = res['scenario_params']['capex_multiplier']
                f.write(
                    f"  CAPEX {capex_mult*100:.0f}%: "
                    f"ROI = {res['roi']:.1f}% (Δ{delta_roi:+.1f}%), "
                    f"Payback = {res['payback_years']:.2f} anos (Δ{delta_payback:+.2f})\n"
                )
        
        # Análise de sensibilidade ao horizonte
        f.write("\n5.5 Impacto do Horizonte de Avaliação:\n")
        f.write("-" * 100 + "\n")
        if base_result:
            horizon_scenarios = [r for r in results_list if 'Horizonte' in r['scenario_name']]
            for res in sorted(horizon_scenarios, key=lambda x: x['scenario_params']['operational_days']):
                delta_roi = res['roi'] - base_result['roi']
                days = res['scenario_params']['operational_days']
                f.write(
                    f"  {days} dias: "
                    f"ROI = {res['roi']:.1f}% (Δ{delta_roi:+.1f}%), "
                    f"Lucro Anual = {res['annual_profit']:,.0f} BRL\n"
                )
        
        # Análise de sensibilidade tarifária
        f.write("\n5.6 Impacto do Diferencial Tarifário (Tarifa VE):\n")
        f.write("-" * 100 + "\n")
        if base_result:
            tariff_scenarios = [r for r in results_list if 'TarifaVE' in r['scenario_name']]
            for res in sorted(tariff_scenarios, key=lambda x: x['scenario_params']['tariff_multiplier']):
                delta_roi = res['roi'] - base_result['roi']
                tariff_mult = res['scenario_params']['tariff_multiplier']
                f.write(
                    f"  Tarifa {tariff_mult*100:.0f}%: "
                    f"ROI = {res['roi']:.1f}% (Δ{delta_roi:+.1f}%), "
                    f"Competitividade = {res['tariff_competitiveness']:.1f}%\n"
                )
        
        # Recomendações
        f.write("\n" + "=" * 100 + "\n")
        f.write("6. RECOMENDAÇÕES PARA OTIMIZAÇÃO DO INVESTIMENTO\n")
        f.write("=" * 100 + "\n\n")
        
        best_roi = sorted_by_roi[0]
        best_payback = sorted_by_payback[0] if sorted_by_payback else best_roi
        best_vpn = sorted_by_vpn[0]
        
        f.write(f"A. CENÁRIO RECOMENDADO (Melhor ROI): {best_roi['scenario_name']}\n")
        f.write(f"   - ROI: {best_roi['roi']:.1f}%\n")
        f.write(f"   - Payback: {best_roi['payback_years']:.2f} anos\n")
        f.write(f"   - VPL: {best_roi['vpn']:,.0f} BRL\n")
        f.write(f"   - Capacidades: PV={best_roi['P_pv_cap']:.1f} kW, BESS={best_roi['E_bess_cap']:.1f} kWh\n\n")
        
        f.write("B. ESTRATÉGIAS PARA MAXIMIZAR RETORNO:\n")
        f.write("   1. REDUÇÃO DE CAPEX:\n")
        if any('CAPEX_70' in r['scenario_name'] for r in results_list):
            capex_70 = next(r for r in results_list if 'CAPEX_70' in r['scenario_name'])
            improvement = capex_70['roi'] - base_result['roi'] if base_result else 0
            f.write(f"      - Reduzir CAPEX em 30% aumenta ROI em {improvement:.1f} pontos percentuais\n")
            f.write(f"      - Buscar fornecedores competitivos, compras em volume, incentivos fiscais\n")
        
        f.write("\n   2. OTIMIZAÇÃO TARIFÁRIA:\n")
        if any('TarifaVE_120' in r['scenario_name'] for r in results_list):
            tariff_120 = next(r for r in results_list if 'TarifaVE_120' in r['scenario_name'])
            improvement = tariff_120['roi'] - base_result['roi'] if base_result else 0
            f.write(f"      - Aumentar tarifa VE em 20% aumenta ROI em {improvement:.1f} pontos percentuais\n")
            f.write(f"      - Análise de competitividade de mercado é fundamental\n")
        
        f.write("\n   3. HORIZONTE DE AVALIAÇÃO:\n")
        f.write(f"      - Horizonte mais longo permite amortizar melhor o CAPEX\n")
        f.write(f"      - Considerar vida útil dos equipamentos (PV: 25 anos, BESS: 10-15 anos)\n")
        
        f.write("\n   4. AUTOSSUFICIÊNCIA ENERGÉTICA:\n")
        if base_result:
            f.write(f"      - Autossuficiência atual: {base_result['self_sufficiency']:.1f}%\n")
            f.write(f"      - Exposição à rede: {base_result['grid_exposure']:.1f}%\n")
            f.write(f"      - Maior investimento em PV/BESS reduz exposição à volatilidade de preços\n")
        
        f.write("\n" + "=" * 100 + "\n")
        f.write("FIM DO RELATÓRIO\n")
        f.write("=" * 100 + "\n")


def main():
    """Função principal."""
    # Diretório de saída
    output_dir = Path(__file__).parent
    report_path = output_dir / "relatorio_analise_investimento.txt"
    
    # Dados de exemplo (substitua pelos seus dados reais)
    base_data = {
        # Parâmetros econômicos
        'operational_days': 365.0,
        'tariff_ev': 0.85,  # BRL/kWh
        'export_price_factor': 0.7,
        'discount_rate': 0.10,
        
        # CAPEX (BRL por unidade)
        'capex_pv_kw': 3500.0,
        'capex_bess_kwh': 2500.0,
        'capex_trafo_kw': 500.0,
        
        # Parâmetros técnicos BESS
        'eta_charge': 0.95,
        'eta_discharge': 0.95,
        'soc_min_frac': 0.20,
        'soc_max_frac': 0.90,
        'soc_initial_frac': 0.50,
        'c_rate_charge': 0.5,
        'c_rate_discharge': 0.5,
        
        # Séries horárias (24h) - exemplo simplificado
        'irradiance_cf': [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.05,  # 0-5h
            0.15, 0.35, 0.55, 0.75, 0.85, 0.95,  # 6-11h
            0.90, 0.85, 0.75, 0.60, 0.40, 0.15,  # 12-17h
            0.05, 0.0, 0.0, 0.0, 0.0, 0.0  # 18-23h
        ],
        'grid_price': [
            0.45, 0.45, 0.45, 0.45, 0.45, 0.50,  # 0-5h
            0.55, 0.65, 0.70, 0.75, 0.75, 0.70,  # 6-11h (pico manhã)
            0.70, 0.70, 0.75, 0.80, 0.85, 0.90,  # 12-17h (pico tarde)
            0.85, 0.75, 0.65, 0.55, 0.50, 0.45  # 18-23h
        ],
        'p_ev_load': [
            5.0, 3.0, 2.0, 2.0, 3.0, 5.0,  # 0-5h (madrugada)
            15.0, 30.0, 45.0, 50.0, 45.0, 40.0,  # 6-11h (manhã)
            35.0, 40.0, 50.0, 60.0, 65.0, 70.0,  # 12-17h (tarde/pico)
            60.0, 45.0, 30.0, 20.0, 10.0, 7.0  # 18-23h (noite)
        ]
    }
    
    print("=" * 80)
    print("ANÁLISE DE INVESTIMENTO EM MICRORREDE PV-BESS")
    print("=" * 80)
    print("\nExecutando análise de múltiplos cenários...\n")
    
    # Executa análise de cenários
    results = run_scenario_analysis(base_data, output_dir)
    
    # Gera relatório comparativo
    print(f"\nGerando relatório comparativo...")
    write_comparative_report(results, report_path)
    
    print(f"\n{'=' * 80}")
    print(f"ANÁLISE CONCLUÍDA!")
    print(f"Relatório gerado em: {report_path}")
    print(f"Total de cenários analisados: {len(results)}")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
