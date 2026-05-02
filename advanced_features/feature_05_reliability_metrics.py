"""
Feature 5 — Análise de Confiabilidade com Métricas SAIDI/EENS
==============================================================

Objetivo
--------
Calcular métricas de confiabilidade de fornecimento reconhecidas internacionalmente
a partir da solução otimizada do modelo de eletroposto, superando o índice
agregado atual (w_ens, max_ens_ratio).

Métricas implementadas
----------------------

EENS — Expected Energy Not Served [kWh/ano]
    EENS = Σ_s prob_s * Σ_t LoadShedding[s,t] * delta_t * operational_days
    Interpretação: energia esperada não entregue à frota VE por ano.
    Referência: IEEE Std 493 (Gold Book), NBR 5410.

LOLP — Loss of Load Probability [-]
    LOLP = Σ_s prob_s * I(LoadShedding_s > 0)
    onde I(·) é a função indicadora (1 se há shed, 0 caso contrário).
    Interpretação: probabilidade de que o sistema não atenda toda a demanda no dia.

LOLE — Loss of Load Expectation [horas/ano]
    LOLE = Σ_s prob_s * Σ_t I(LoadShedding[s,t] > 0) * operational_days
    Interpretação: horas esperadas de indisponibilidade por ano.

SAIDI equivalente [horas/ano por cliente]
    Adaptação para eletroposto (cliente = sessão de recarga VE):
    SAIDI_equiv = LOLE / N_sessoes_ano
    onde N_sessoes_ano é o número médio de sessões diárias × operational_days.

SAIFI equivalente [interrupções/ano por cliente]
    SAIFI_equiv = LOLP * operational_days / N_sessoes_ano

Índice de Autossuficiência [%]
    Fracão da demanda atendida por fontes locais (PV + BESS):
    AutoSuf = Σ_s prob_s * (PV_s + BESS_discharge_s - BESS_charge_s) / Carga_s

Índice de Dependência da Rede [%]
    1 - AutoSuf (complementar).

Referências
-----------
- IEEE Std 1366 (2012) "Guide for Electric Power Distribution Reliability Indices."
- IEEE Std 493 (2007) "Design of Reliable Industrial and Commercial Power Systems."
- ANEEL Resolução Normativa 414/2010 — Indicadores de qualidade do serviço (DEC, FEC).
- Billinton & Allan (1996) "Reliability Evaluation of Power Systems." 2nd ed.

Uso
---
    from advanced_features.feature_05_reliability_metrics import (
        compute_reliability_metrics, ReliabilityReport, plot_pareto_capex_eens
    )

    # Após resolver o modelo multi-cenário:
    report = compute_reliability_metrics(instance, scenarios, operational_days=365)
    report.print_summary()
    plot_pareto_capex_eens(pareto_points)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pyomo.environ import value


# ---------------------------------------------------------------------------
# Estruturas de dados de resultado
# ---------------------------------------------------------------------------

@dataclass
class ScenarioReliability:
    """Métricas de confiabilidade para um único cenário."""

    scenario_name: str
    probability: float
    total_load_kwh: float             # energia total demandada [kWh/dia]
    total_shed_kwh: float             # energia não entregue [kWh/dia]
    hours_with_shed: int              # horas com shed > threshold [h/dia]
    ens_ratio: float                  # ENS / demanda total [-]
    self_sufficiency: float           # fração atendida por PV+BESS [-]
    grid_dependency: float            # fração importada da rede [-]
    peak_shed_kw: float               # shed máximo em uma hora [kW]


@dataclass
class ReliabilityReport:
    """Relatório completo de confiabilidade multi-cenário."""

    # Métricas ANEEL/IEEE por cenário
    scenario_metrics: List[ScenarioReliability]

    # Métricas esperadas (ponderadas por probabilidade)
    eens_kwh_dia: float               # EENS [kWh/dia]
    eens_kwh_ano: float               # EENS [kWh/ano]
    lolp: float                       # Loss of Load Probability [-]
    lole_horas_ano: float             # LOLE [h/ano]
    saidi_equiv_horas_ano: float      # SAIDI equivalente [h/ano/cliente]
    saifi_equiv_ano: float            # SAIFI equivalente [interrupções/ano/cliente]
    eens_ratio: float                 # EENS / demanda total esperada [-]

    # Métricas de recurso local
    expected_self_sufficiency: float  # autossuficiência esperada [-]
    expected_grid_dependency: float   # dependência esperada da rede [-]

    # Parâmetros
    operational_days: float
    n_sessoes_dia: float

    def print_summary(self) -> None:
        """Imprime relatório de confiabilidade formatado."""
        print("\n" + "=" * 65)
        print("RELATÓRIO DE CONFIABILIDADE — ELETROPOSTO PV-BESS")
        print("=" * 65)
        print(f"\n{'Métrica':<40} {'Valor':>15} {'Unidade':<10}")
        print("-" * 65)
        print(f"{'EENS':<40} {self.eens_kwh_ano:>15.2f} {'kWh/ano':<10}")
        print(f"{'EENS (diário)':<40} {self.eens_kwh_dia:>15.4f} {'kWh/dia':<10}")
        print(f"{'EENS ratio':<40} {self.eens_ratio*100:>15.3f} {'%':<10}")
        print(f"{'LOLP':<40} {self.lolp:>15.4f} {'-':<10}")
        print(f"{'LOLE':<40} {self.lole_horas_ano:>15.2f} {'h/ano':<10}")
        print(f"{'SAIDI equiv.':<40} {self.saidi_equiv_horas_ano:>15.4f} {'h/ano/cliente':<10}")
        print(f"{'SAIFI equiv.':<40} {self.saifi_equiv_ano:>15.4f} {'int./ano/cliente':<10}")
        print(f"{'Autossuficiência esperada':<40} {self.expected_self_sufficiency*100:>15.1f} {'%':<10}")
        print(f"{'Dependência da rede esperada':<40} {self.expected_grid_dependency*100:>15.1f} {'%':<10}")
        print("-" * 65)

        if self.scenario_metrics:
            print(f"\nDetalhamento por cenário:")
            print(f"{'Cenário':<20} {'prob':>6} {'ENS%':>8} {'AutoSuf%':>10} {'Horas_shed':>12}")
            print("-" * 60)
            for sc in self.scenario_metrics:
                print(
                    f"{sc.scenario_name:<20} {sc.probability:>6.3f} "
                    f"{sc.ens_ratio*100:>8.2f} {sc.self_sufficiency*100:>10.1f} "
                    f"{sc.hours_with_shed:>12}"
                )

    def to_dict(self) -> Dict[str, float]:
        """Exporta métricas agregadas como dicionário."""
        return {
            "eens_kwh_ano": self.eens_kwh_ano,
            "eens_kwh_dia": self.eens_kwh_dia,
            "lolp": self.lolp,
            "lole_horas_ano": self.lole_horas_ano,
            "saidi_equiv": self.saidi_equiv_horas_ano,
            "saifi_equiv": self.saifi_equiv_ano,
            "eens_ratio": self.eens_ratio,
            "autossuficiencia": self.expected_self_sufficiency,
            "dependencia_rede": self.expected_grid_dependency,
        }


# ---------------------------------------------------------------------------
# Função principal de cálculo
# ---------------------------------------------------------------------------

def compute_reliability_metrics(
    instance,
    scenario_names: List[str],
    probabilities: Dict[str, float],
    operational_days: float = 365.0,
    n_sessoes_dia: float = 50.0,
    shed_threshold_kw: float = 0.01,
    delta_t: float = 1.0,
) -> ReliabilityReport:
    """
    Calcula métricas de confiabilidade a partir de uma instância Pyomo resolvida
    do modelo multi-cenário (modelo_abstract_artigo_itens_322_323_4_5_6.py).

    Args:
        instance: instância Pyomo concreta pós-resolução.
        scenario_names: lista de nomes de cenários (corresponde ao conjunto SC).
        probabilities: dict {nome_cenário: probabilidade}.
        operational_days: dias de operação por ano (padrão: 365).
        n_sessoes_dia: número médio de sessões de recarga por dia (para SAIDI/SAIFI).
        shed_threshold_kw: limiar mínimo para considerar hour com shed [kW].
        delta_t: duração de cada intervalo temporal [h].

    Returns:
        ReliabilityReport com todas as métricas calculadas.
    """
    T = list(instance.T)
    scenario_results: List[ScenarioReliability] = []

    total_expected_load = 0.0
    total_expected_shed = 0.0
    lolp = 0.0
    lole_horas_dia = 0.0
    expected_self_suf = 0.0
    expected_grid_dep = 0.0

    for sc in scenario_names:
        prob = probabilities.get(sc, 1.0 / len(scenario_names))

        # Energia total demandada e cortada no cenário
        load_sc = sum(value(instance.P_EV_load[sc, t]) * delta_t for t in T)
        shed_sc = sum(value(instance.LoadShedding[sc, t]) * delta_t for t in T)

        # Horas com shed
        hours_shed = sum(
            1 for t in T if value(instance.LoadShedding[sc, t]) > shed_threshold_kw
        )

        # Shed máximo horário
        peak_shed = max(value(instance.LoadShedding[sc, t]) for t in T)

        # Autossuficiência: (PV + BESS_discharge - BESS_charge) / carga atendida
        pv_local = sum(value(instance.P_pv_gen[sc, t]) * delta_t for t in T)
        bess_dis = sum(value(instance.P_bess_discharge[sc, t]) * delta_t for t in T)
        bess_chg = sum(value(instance.P_bess_charge[sc, t]) * delta_t for t in T)
        grid_imp = sum(value(instance.P_grid_import[sc, t]) * delta_t for t in T)
        served_load = load_sc - shed_sc

        local_supply = max(0.0, pv_local + bess_dis - bess_chg)
        self_suf = local_supply / max(served_load, 1e-9)
        grid_dep = grid_imp / max(served_load, 1e-9)

        ens_ratio = shed_sc / max(load_sc, 1e-9)

        scenario_results.append(ScenarioReliability(
            scenario_name=sc,
            probability=prob,
            total_load_kwh=load_sc,
            total_shed_kwh=shed_sc,
            hours_with_shed=hours_shed,
            ens_ratio=ens_ratio,
            self_sufficiency=min(1.0, self_suf),
            grid_dependency=min(1.0, grid_dep),
            peak_shed_kw=peak_shed,
        ))

        # Acumulação ponderada
        total_expected_load += prob * load_sc
        total_expected_shed += prob * shed_sc
        lolp += prob * (1.0 if hours_shed > 0 else 0.0)
        lole_horas_dia += prob * hours_shed
        expected_self_suf += prob * min(1.0, self_suf)
        expected_grid_dep += prob * min(1.0, grid_dep)

    eens_kwh_dia = total_expected_shed
    eens_kwh_ano = eens_kwh_dia * operational_days
    lole_horas_ano = lole_horas_dia * operational_days
    n_sessoes_ano = n_sessoes_dia * operational_days

    # SAIDI/SAIFI adaptados (interrupções por cliente = por sessão de recarga)
    saidi_equiv = lole_horas_ano / max(n_sessoes_ano, 1)
    saifi_equiv = lolp * operational_days / max(n_sessoes_ano, 1)
    eens_ratio = total_expected_shed / max(total_expected_load, 1e-9)

    return ReliabilityReport(
        scenario_metrics=scenario_results,
        eens_kwh_dia=eens_kwh_dia,
        eens_kwh_ano=eens_kwh_ano,
        lolp=lolp,
        lole_horas_ano=lole_horas_ano,
        saidi_equiv_horas_ano=saidi_equiv,
        saifi_equiv_ano=saifi_equiv,
        eens_ratio=eens_ratio,
        expected_self_sufficiency=expected_self_suf,
        expected_grid_dependency=expected_grid_dep,
        operational_days=operational_days,
        n_sessoes_dia=n_sessoes_dia,
    )


def compute_reliability_from_profiles(
    load_profiles: Dict[str, Dict[int, float]],
    shed_profiles: Dict[str, Dict[int, float]],
    pv_profiles: Dict[str, Dict[int, float]],
    bess_discharge_profiles: Dict[str, Dict[int, float]],
    bess_charge_profiles: Dict[str, Dict[int, float]],
    grid_import_profiles: Dict[str, Dict[int, float]],
    probabilities: Dict[str, float],
    operational_days: float = 365.0,
    n_sessoes_dia: float = 50.0,
    shed_threshold_kw: float = 0.01,
    delta_t: float = 1.0,
) -> ReliabilityReport:
    """
    Versão alternativa: aceita perfis como dicionários (sem instância Pyomo).
    Útil para análise pós-otimização com dados importados de CSV.

    Args:
        load_profiles: {cenário: {hora: kW}} — demanda nominal.
        shed_profiles: {cenário: {hora: kW}} — energia cortada.
        pv_profiles, bess_discharge_profiles, bess_charge_profiles,
        grid_import_profiles: perfis operacionais por cenário e hora.
        probabilities: {cenário: probabilidade}.
        Demais: parâmetros de confiabilidade.
    """
    scenario_results: List[ScenarioReliability] = []
    total_expected_load = 0.0
    total_expected_shed = 0.0
    lolp = 0.0
    lole_horas_dia = 0.0
    expected_self_suf = 0.0
    expected_grid_dep = 0.0

    for sc, prob in probabilities.items():
        load_sc = sum(load_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        shed_sc = sum(shed_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        hours_shed = sum(1 for t in range(1, 25) if shed_profiles[sc].get(t, 0.0) > shed_threshold_kw)
        peak_shed = max(shed_profiles[sc].get(t, 0.0) for t in range(1, 25))

        pv_local = sum(pv_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        bess_dis = sum(bess_discharge_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        bess_chg = sum(bess_charge_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        grid_imp = sum(grid_import_profiles[sc].get(t, 0.0) * delta_t for t in range(1, 25))
        served_load = load_sc - shed_sc

        local_supply = max(0.0, pv_local + bess_dis - bess_chg)
        self_suf = local_supply / max(served_load, 1e-9)
        grid_dep = grid_imp / max(served_load, 1e-9)
        ens_ratio = shed_sc / max(load_sc, 1e-9)

        scenario_results.append(ScenarioReliability(
            scenario_name=sc,
            probability=prob,
            total_load_kwh=load_sc,
            total_shed_kwh=shed_sc,
            hours_with_shed=hours_shed,
            ens_ratio=ens_ratio,
            self_sufficiency=min(1.0, self_suf),
            grid_dependency=min(1.0, grid_dep),
            peak_shed_kw=peak_shed,
        ))

        total_expected_load += prob * load_sc
        total_expected_shed += prob * shed_sc
        lolp += prob * (1.0 if hours_shed > 0 else 0.0)
        lole_horas_dia += prob * hours_shed
        expected_self_suf += prob * min(1.0, self_suf)
        expected_grid_dep += prob * min(1.0, grid_dep)

    eens_kwh_dia = total_expected_shed
    eens_kwh_ano = eens_kwh_dia * operational_days
    lole_horas_ano = lole_horas_dia * operational_days
    n_sessoes_ano = n_sessoes_dia * operational_days
    saidi_equiv = lole_horas_ano / max(n_sessoes_ano, 1)
    saifi_equiv = lolp * operational_days / max(n_sessoes_ano, 1)
    eens_ratio = total_expected_shed / max(total_expected_load, 1e-9)

    return ReliabilityReport(
        scenario_metrics=scenario_results,
        eens_kwh_dia=eens_kwh_dia,
        eens_kwh_ano=eens_kwh_ano,
        lolp=lolp,
        lole_horas_ano=lole_horas_ano,
        saidi_equiv_horas_ano=saidi_equiv,
        saifi_equiv_ano=saifi_equiv,
        eens_ratio=eens_ratio,
        expected_self_sufficiency=expected_self_suf,
        expected_grid_dependency=expected_grid_dep,
        operational_days=operational_days,
        n_sessoes_dia=n_sessoes_dia,
    )


# ---------------------------------------------------------------------------
# Visualização: Fronteira de Pareto CAPEX × EENS
# ---------------------------------------------------------------------------

@dataclass
class ParetoPoint:
    """Ponto na fronteira de Pareto CAPEX × EENS."""
    epsilon: float          # restrição EENS usada [kWh/ano]
    capex_anual_brl: float  # CAPEX anualizado [BRL/ano]
    eens_kwh_ano: float     # EENS realizada [kWh/ano]
    P_pv_cap: float
    E_bess_cap: float
    P_trafo_cap: float
    self_sufficiency: float
    status: str


def plot_pareto_capex_eens(
    pareto_points: List[ParetoPoint],
    save_path: Optional[str] = None,
    title: str = "Fronteira de Pareto: CAPEX Anualizado × EENS",
) -> None:
    """
    Plota a fronteira de Pareto entre CAPEX anualizado e EENS.

    Args:
        pareto_points: lista de pontos na fronteira (gerada por feature_07).
        save_path: caminho para salvar figura (None = exibir).
        title: título do gráfico.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np
    except ImportError:
        print("matplotlib e numpy necessários. pip install matplotlib numpy")
        return

    valid = [p for p in pareto_points if p.status == "optimal"]
    if not valid:
        print("Nenhum ponto ótimo disponível para plotagem.")
        return

    eens_vals = [p.eens_kwh_ano for p in valid]
    capex_vals = [p.capex_anual_brl / 1000 for p in valid]  # kBRL
    suf_vals = [p.self_sufficiency * 100 for p in valid]
    pv_vals = [p.P_pv_cap for p in valid]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: CAPEX × EENS com coloração por autossuficiência
    sc = axes[0].scatter(eens_vals, capex_vals, c=suf_vals, cmap="RdYlGn",
                          s=100, edgecolors="black", linewidths=0.5, zorder=5)
    axes[0].plot(eens_vals, capex_vals, "b--", alpha=0.5, linewidth=1, label="Fronteira Pareto")
    cbar = plt.colorbar(sc, ax=axes[0])
    cbar.set_label("Autossuficiência (%)")
    axes[0].set_xlabel("EENS [kWh/ano]")
    axes[0].set_ylabel("CAPEX Anualizado [kBRL/ano]")
    axes[0].set_title(title)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    # Plot 2: Dimensionamento ao longo da fronteira
    axes[1].plot(eens_vals, pv_vals, "o-", color="orange", linewidth=2, label="P_PV [kW]")
    ax2 = axes[1].twinx()
    bess_vals = [p.E_bess_cap for p in valid]
    ax2.plot(eens_vals, bess_vals, "s-", color="blue", linewidth=2, label="E_BESS [kWh]")
    axes[1].set_xlabel("EENS [kWh/ano]")
    axes[1].set_ylabel("Capacidade PV [kW]", color="orange")
    ax2.set_ylabel("Capacidade BESS [kWh]", color="blue")
    axes[1].set_title("Dimensionamento ao longo da Fronteira Pareto")
    axes[1].grid(True, alpha=0.3)

    lines1, labels1 = axes[1].get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    axes[1].legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Figura salva em: {save_path}")
    else:
        plt.show()
    plt.close()


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 5 — Métricas de Confiabilidade SAIDI/EENS")
    print("=" * 60)

    # Exemplo com dados sintéticos (sem solver)
    load = {t: 80.0 for t in range(1, 25)}
    shed_base = {t: 0.0 for t in range(1, 25)}
    shed_falha = {t: (5.0 if 17 <= t <= 20 else 0.0) for t in range(1, 25)}
    pv = {t: max(0, (t - 6) * 12.0) if 6 <= t <= 12 else max(0, (18 - t) * 12.0) if 12 < t <= 18 else 0 for t in range(1, 25)}
    bess_dis = {t: (15.0 if 17 <= t <= 21 else 0.0) for t in range(1, 25)}
    bess_chg = {t: (10.0 if 9 <= t <= 13 else 0.0) for t in range(1, 25)}
    grid_imp = {t: max(0.0, load[t] - pv.get(t, 0) - bess_dis.get(t, 0) + bess_chg.get(t, 0)) for t in range(1, 25)}

    scenarios = {
        "normal": 0.85,
        "falha_rede": 0.15,
    }
    report = compute_reliability_from_profiles(
        load_profiles={"normal": load, "falha_rede": load},
        shed_profiles={"normal": shed_base, "falha_rede": shed_falha},
        pv_profiles={"normal": pv, "falha_rede": pv},
        bess_discharge_profiles={"normal": bess_dis, "falha_rede": bess_dis},
        bess_charge_profiles={"normal": bess_chg, "falha_rede": bess_chg},
        grid_import_profiles={"normal": grid_imp, "falha_rede": grid_imp},
        probabilities=scenarios,
        operational_days=365.0,
        n_sessoes_dia=50.0,
    )
    report.print_summary()
