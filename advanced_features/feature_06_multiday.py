"""
Feature 6 — Horizonte Multi-dia com Sazonalidade
=================================================

Objetivo
--------
Estender o horizonte de planejamento de 24 horas (um dia representativo) para
múltiplos dias com continuidade de SOC entre dias e redução de cenários via
k-means, capturando variações sazonais e dia-útil/fim-de-semana.

Formulação matemática
---------------------

Conjuntos:
    T = {1, ..., H}   — horas do horizonte total (H = n_days × 24)
    D = {1, ..., n_days}  — dias no horizonte
    H_d = {(d-1)*24+1, ..., d*24}  — horas do dia d

Indexação: t = (d-1)*24 + h  onde h ∈ {1,...,24} e d ∈ D

Variáveis adicionais:
    SOC[t] agora cobre todo o horizonte (n_days × 24 períodos)

Continuidade de SOC entre dias:
    SOC[d*24] → SOC[d*24+1]  mantida pela equação de balanço padrão
    (não há restrição terminal por dia, apenas ao final do horizonte)

Restrição terminal cíclica (apenas no último dia):
    SOC[T_last] == soc_initial_frac * E_bess_cap

Perfis multi-dia (parâmetros indexados por (d, h)):
    irradiance_cf[d, h], grid_price[d, h], P_EV_load[d, h]

Redução de cenários (k-means)
------------------------------
Para um conjunto de N perfis diários históricos, aplica k-means com K clusters
(K = número de dias representativos), retornando:
    - K centróides (perfis representativos)
    - Pesos (fração de dias cobertos por cada centróide)

Os perfis representativos são então usados para construir o horizonte multi-dia.

Referências
-----------
- Kaut & Wallace (2007) "Evaluation of Scenario-Generation Methods for Stochastic
  Programming." Pacific Journal of Optimization.
- Morales et al. (2009) "Scenario Reduction for Futures Market Trading in Electricity
  Markets." IEEE Trans. Power Syst.
- Domínguez-Muñoz et al. (2011) "Optimization of building energy systems using
  weather file generation." Applied Energy.

Uso
---
    from advanced_features.feature_06_multiday import (
        MultiDayModel, reduce_scenarios_kmeans, build_model_multiday
    )

    representative_days, weights = reduce_scenarios_kmeans(
        irradiance_profiles, ev_load_profiles, n_clusters=7
    )
    model = build_model_multiday(representative_days, weights)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pyomo.environ import (
    AbstractModel,
    Binary,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    SolverFactory,
    Var,
    maximize,
    value,
)


# ---------------------------------------------------------------------------
# Estrutura de dia representativo
# ---------------------------------------------------------------------------

@dataclass
class RepresentativeDay:
    """Perfil de um dia representativo com peso de ocorrência."""

    day_id: int
    day_type: str                        # "weekday", "weekend", "holiday", etc.
    weight: float                        # fração do ano representada (0 a 1)
    irradiance_cf: Dict[int, float]      # h -> fator de capacidade FV [0,1]
    grid_price: Dict[int, float]         # h -> BRL/kWh
    ev_load: Dict[int, float]            # h -> kW

    def total_ev_energy(self) -> float:
        return sum(self.ev_load.values())

    def peak_ev_load(self) -> float:
        return max(self.ev_load.values())

    def total_solar_energy(self, pv_cap_kw: float = 1.0) -> float:
        return pv_cap_kw * sum(self.irradiance_cf.values())


# ---------------------------------------------------------------------------
# Redução de cenários via k-means
# ---------------------------------------------------------------------------

def reduce_scenarios_kmeans(
    irradiance_histories: List[Dict[int, float]],
    ev_load_histories: List[Dict[int, float]],
    grid_price_histories: Optional[List[Dict[int, float]]] = None,
    n_clusters: int = 7,
    random_state: int = 42,
    day_types: Optional[List[str]] = None,
) -> Tuple[List[RepresentativeDay], List[float]]:
    """
    Reduz um conjunto de perfis diários históricos a K dias representativos via k-means.

    Algoritmo:
    1. Concatenar perfis [irr[1..24], ev[1..24]] em vetor de features por dia.
    2. Normalizar features (zero-mean, unit-variance por feature).
    3. Aplicar k-means com K clusters.
    4. Centróide de cada cluster → dia representativo.
    5. Peso de cada cluster = proporção de dias atribuídos ao cluster.

    Args:
        irradiance_histories: lista de perfis históricos de irradiância (um por dia).
        ev_load_histories: lista de perfis históricos de carga VE (um por dia).
        grid_price_histories: perfis de preço (opcional; se None, usa preço padrão).
        n_clusters: número de dias representativos K.
        random_state: semente para reprodutibilidade.
        day_types: tipo de dia para cada entrada histórica (opcional).

    Returns:
        (representative_days, weights) — lista de RepresentativeDay e pesos normalizados.

    Requer:
        scikit-learn: pip install scikit-learn
    """
    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise ImportError(
            "scikit-learn e numpy são necessários para redução de cenários. "
            "Instale com: pip install scikit-learn numpy"
        )

    n_days = len(irradiance_histories)
    hours = sorted(irradiance_histories[0].keys())
    n_hours = len(hours)

    # Construir matriz de features (n_days × 2*n_hours)
    features = []
    for i in range(n_days):
        irr_vec = [irradiance_histories[i].get(h, 0.0) for h in hours]
        ev_vec = [ev_load_histories[i].get(h, 0.0) for h in hours]
        features.append(irr_vec + ev_vec)

    X = np.array(features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Aplicar k-means
    n_clusters_eff = min(n_clusters, n_days)
    kmeans = KMeans(n_clusters=n_clusters_eff, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    # Extrair centróides e desnormalizar
    centers_scaled = kmeans.cluster_centers_
    centers = scaler.inverse_transform(centers_scaled)

    representative_days = []
    weights = []

    for k in range(n_clusters_eff):
        center = centers[k]
        irr_center = {hours[h]: max(0.0, min(1.0, center[h])) for h in range(n_hours)}
        ev_center = {hours[h]: max(0.0, center[n_hours + h]) for h in range(n_hours)}

        # Peso = fração de dias no cluster
        n_in_cluster = (labels == k).sum()
        weight = n_in_cluster / n_days

        # Preço: média dos dias no cluster, ou padrão
        if grid_price_histories is not None:
            cluster_indices = [i for i, l in enumerate(labels) if l == k]
            price_center = {}
            for h in hours:
                price_center[h] = sum(
                    grid_price_histories[i].get(h, 0.5) for i in cluster_indices
                ) / len(cluster_indices)
        else:
            price_center = {h: 0.54 for h in hours}  # padrão fora-ponta

        # Tipo de dia dominante no cluster
        if day_types is not None:
            cluster_day_types = [day_types[i] for i in range(n_days) if labels[i] == k]
            from collections import Counter
            dominant_type = Counter(cluster_day_types).most_common(1)[0][0]
        else:
            dominant_type = "mixed"

        representative_days.append(RepresentativeDay(
            day_id=k + 1,
            day_type=dominant_type,
            weight=weight,
            irradiance_cf=irr_center,
            grid_price=price_center,
            ev_load=ev_center,
        ))
        weights.append(weight)

    # Normalizar pesos (devem somar 1.0)
    total_w = sum(weights)
    weights_norm = [w / total_w for w in weights]
    for i, rd in enumerate(representative_days):
        rd.weight = weights_norm[i]

    return representative_days, weights_norm


# ---------------------------------------------------------------------------
# Construção do modelo multi-dia
# ---------------------------------------------------------------------------

def build_model_multiday(
    representative_days: List[RepresentativeDay],
    *,
    capex_pv_kw: float = 1200.0,
    capex_bess_kwh: float = 700.0,
    capex_trafo_kw: float = 1000.0,
    crf_pv: float = 0.10,
    crf_bess: float = 0.12,
    crf_trafo: float = 0.08,
    om_pv_kw_year: float = 30.0,
    om_bess_kwh_year: float = 25.0,
    om_trafo_kw_year: float = 20.0,
    tariff_ev: float = 1.60,
    operational_days: float = 365.0,
    eta_charge: float = 0.91,
    eta_discharge: float = 0.91,
    soc_min_frac: float = 0.05,
    soc_max_frac: float = 0.95,
    soc_initial_frac: float = 0.50,
    c_rate_charge: float = 1.0,
    c_rate_discharge: float = 1.0,
    E_bess_cap_max: float = 2000.0,
    P_pv_cap_max: float = 1000.0,
    P_trafo_cap_max: float = 500.0,
) -> AbstractModel:
    """
    Constrói modelo Pyomo multi-dia a partir de dias representativos.

    O horizonte total é n_days × 24 horas. O SOC é contínuo entre dias,
    e a restrição terminal cíclica é aplicada apenas ao final do último dia.

    Cada dia representativo tem peso w_d que pondera sua contribuição na
    função objetivo anualizada.

    Args:
        representative_days: lista de dias representativos (gerados por k-means).
        Demais: parâmetros técnico-econômicos.

    Returns:
        AbstractModel Pyomo com índice temporal expandido.
    """
    n_days = len(representative_days)
    n_hours_total = n_days * 24

    # Construir dicionários de parâmetros indexados por t = 1..n_hours_total
    irr_dict: Dict[int, float] = {}
    price_dict: Dict[int, float] = {}
    ev_dict: Dict[int, float] = {}
    day_weight_per_t: Dict[int, float] = {}

    for d_idx, day in enumerate(representative_days):
        for h in range(1, 25):
            t = d_idx * 24 + h
            irr_dict[t] = day.irradiance_cf.get(h, 0.0)
            price_dict[t] = day.grid_price.get(h, 0.5)
            ev_dict[t] = day.ev_load.get(h, 0.0)
            day_weight_per_t[t] = day.weight

    m = AbstractModel()
    m.T = RangeSet(1, n_hours_total)

    # Parâmetros escalares
    m.capex_pv_kw = Param(initialize=capex_pv_kw, within=NonNegativeReals)
    m.capex_bess_kwh = Param(initialize=capex_bess_kwh, within=NonNegativeReals)
    m.capex_trafo_kw = Param(initialize=capex_trafo_kw, within=NonNegativeReals)
    m.crf_pv = Param(initialize=crf_pv, within=NonNegativeReals)
    m.crf_bess = Param(initialize=crf_bess, within=NonNegativeReals)
    m.crf_trafo = Param(initialize=crf_trafo, within=NonNegativeReals)
    m.om_pv_kw_year = Param(initialize=om_pv_kw_year, within=NonNegativeReals)
    m.om_bess_kwh_year = Param(initialize=om_bess_kwh_year, within=NonNegativeReals)
    m.om_trafo_kw_year = Param(initialize=om_trafo_kw_year, within=NonNegativeReals)
    m.tariff_ev = Param(initialize=tariff_ev, within=NonNegativeReals)
    m.operational_days = Param(initialize=operational_days, within=NonNegativeReals)
    m.n_days = Param(initialize=n_days, within=NonNegativeReals)
    m.eta_charge = Param(initialize=eta_charge, within=NonNegativeReals)
    m.eta_discharge = Param(initialize=eta_discharge, within=NonNegativeReals)
    m.soc_min_frac = Param(initialize=soc_min_frac, within=NonNegativeReals)
    m.soc_max_frac = Param(initialize=soc_max_frac, within=NonNegativeReals)
    m.soc_initial_frac = Param(initialize=soc_initial_frac, within=NonNegativeReals)
    m.c_rate_charge = Param(initialize=c_rate_charge, within=NonNegativeReals)
    m.c_rate_discharge = Param(initialize=c_rate_discharge, within=NonNegativeReals)
    m.E_bess_cap_max = Param(initialize=E_bess_cap_max, within=NonNegativeReals)
    m.P_pv_cap_max = Param(initialize=P_pv_cap_max, within=NonNegativeReals)
    m.P_trafo_cap_max = Param(initialize=P_trafo_cap_max, within=NonNegativeReals)

    # Séries temporais expandidas (n_days × 24)
    m.irradiance_cf = Param(m.T, initialize=irr_dict, within=NonNegativeReals)
    m.grid_price = Param(m.T, initialize=price_dict, within=NonNegativeReals)
    m.P_EV_load = Param(m.T, initialize=ev_dict, within=NonNegativeReals)
    m.day_weight = Param(m.T, initialize=day_weight_per_t, within=NonNegativeReals)

    # Variáveis de investimento
    m.P_pv_cap = Var(within=NonNegativeReals, bounds=(0, P_pv_cap_max))
    m.E_bess_cap = Var(within=NonNegativeReals, bounds=(0, E_bess_cap_max))
    m.P_trafo_cap = Var(within=NonNegativeReals, bounds=(0, P_trafo_cap_max))

    # Variáveis operacionais (horizonte completo)
    m.P_pv_gen = Var(m.T, within=NonNegativeReals)
    m.P_grid_import = Var(m.T, within=NonNegativeReals)
    m.P_grid_export = Var(m.T, within=NonNegativeReals)
    m.P_bess_charge = Var(m.T, within=NonNegativeReals)
    m.P_bess_discharge = Var(m.T, within=NonNegativeReals)
    m.SOC = Var(m.T, within=NonNegativeReals)
    m.LoadShedding = Var(m.T, within=NonNegativeReals)
    m.y_bess = Var(m.T, within=Binary)

    # Restrições
    def pv_limit(model, t):
        return model.P_pv_gen[t] <= model.P_pv_cap * model.irradiance_cf[t]
    m.PVLimit = Constraint(m.T, rule=pv_limit)

    def import_limit(model, t):
        return model.P_grid_import[t] <= model.P_trafo_cap
    m.ImportLimit = Constraint(m.T, rule=import_limit)

    def charge_power(model, t):
        return model.P_bess_charge[t] <= model.c_rate_charge * model.E_bess_cap
    m.ChargePower = Constraint(m.T, rule=charge_power)

    def discharge_power(model, t):
        return model.P_bess_discharge[t] <= model.c_rate_discharge * model.E_bess_cap
    m.DischargePower = Constraint(m.T, rule=discharge_power)

    def charge_mode(model, t):
        return model.P_bess_charge[t] <= model.c_rate_charge * model.E_bess_cap_max * model.y_bess[t]
    m.ChargeMode = Constraint(m.T, rule=charge_mode)

    def discharge_mode(model, t):
        return model.P_bess_discharge[t] <= model.c_rate_discharge * model.E_bess_cap_max * (1 - model.y_bess[t])
    m.DischargeMode = Constraint(m.T, rule=discharge_mode)

    def soc_min_b(model, t):
        return model.SOC[t] >= model.soc_min_frac * model.E_bess_cap
    m.SOCMinBound = Constraint(m.T, rule=soc_min_b)

    def soc_max_b(model, t):
        return model.SOC[t] <= model.soc_max_frac * model.E_bess_cap
    m.SOCMaxBound = Constraint(m.T, rule=soc_max_b)

    # SOC dinâmico — contínuo entre dias (sem reset inter-dia)
    def soc_balance(model, t):
        cn = model.eta_charge * model.P_bess_charge[t] - model.P_bess_discharge[t] / model.eta_discharge
        if t == model.T.first():
            return model.SOC[t] == model.soc_initial_frac * model.E_bess_cap + cn
        return model.SOC[t] == model.SOC[model.T.prev(t)] + cn
    m.SOCBalance = Constraint(m.T, rule=soc_balance)

    # Restrição cíclica apenas no final do horizonte completo
    def terminal_soc(model):
        return model.SOC[model.T.last()] == model.soc_initial_frac * model.E_bess_cap
    m.TerminalSOC = Constraint(rule=terminal_soc)

    def energy_balance(model, t):
        return (
            model.P_pv_gen[t] + model.P_grid_import[t] + model.P_bess_discharge[t]
            == model.P_EV_load[t] - model.LoadShedding[t] + model.P_bess_charge[t] + model.P_grid_export[t]
        )
    m.EnergyBalance = Constraint(m.T, rule=energy_balance)

    def no_shedding(model, t):
        return model.LoadShedding[t] == 0.0
    m.NoShedding = Constraint(m.T, rule=no_shedding)

    # Função objetivo: lucro ponderado pelos pesos dos dias representativos
    def objective_rule(model):
        annual_operational = operational_days * sum(
            model.day_weight[t] * (
                model.tariff_ev * model.P_EV_load[t]
                - model.grid_price[t] * model.P_grid_import[t]
            )
            for t in model.T
        )
        annual_investment = (
            (model.crf_pv * model.capex_pv_kw + model.om_pv_kw_year) * model.P_pv_cap
            + (model.crf_bess * model.capex_bess_kwh + model.om_bess_kwh_year) * model.E_bess_cap
            + (model.crf_trafo * model.capex_trafo_kw + model.om_trafo_kw_year) * model.P_trafo_cap
        )
        return annual_operational - annual_investment

    m.Obj = Objective(rule=objective_rule, sense=maximize)
    return m


# ---------------------------------------------------------------------------
# Gerador de dias representativos sintéticos (sem dados reais)
# ---------------------------------------------------------------------------

def generate_synthetic_representative_days(
    n_weekdays: int = 5,
    n_weekends: int = 2,
    with_seasonal_variation: bool = True,
    seed: int = 42,
) -> List[RepresentativeDay]:
    """
    Gera dias representativos sintéticos para semana (5 úteis + 2 fins de semana).

    Args:
        n_weekdays: dias úteis por semana (padrão: 5).
        n_weekends: dias de fim de semana (padrão: 2).
        with_seasonal_variation: se True, aplica variação sazonal na irradiância.
        seed: semente aleatória.

    Returns:
        Lista de RepresentativeDay com pesos proporcionais.
    """
    import random
    rng = random.Random(seed)

    irr_base = {
        1: 0.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.10, 6: 0.30,
        7: 0.55, 8: 0.75, 9: 0.90, 10: 1.00, 11: 0.95, 12: 0.90,
        13: 0.85, 14: 0.80, 15: 0.70, 16: 0.50, 17: 0.30, 18: 0.10,
        19: 0.00, 20: 0.00, 21: 0.00, 22: 0.00, 23: 0.00, 24: 0.00,
    }
    price_base = {
        1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25, 5: 0.25, 6: 0.25,
        7: 0.54, 8: 0.88, 9: 0.88, 10: 0.88, 11: 0.88, 12: 0.54,
        13: 0.54, 14: 0.54, 15: 0.54, 16: 0.54, 17: 0.88, 18: 1.10,
        19: 1.10, 20: 1.10, 21: 0.88, 22: 0.54, 23: 0.25, 24: 0.25,
    }
    ev_weekday = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
        9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
        16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
        22: 72, 23: 54, 24: 42,
    }
    ev_weekend = {h: max(0.0, ev_weekday[h] * 0.65) for h in range(1, 25)}

    total_days = n_weekdays + n_weekends
    days = []

    for i in range(n_weekdays):
        factor = (1.0 + rng.uniform(-0.05, 0.05)) if with_seasonal_variation else 1.0
        days.append(RepresentativeDay(
            day_id=i + 1,
            day_type="weekday",
            weight=n_weekdays / total_days,
            irradiance_cf={h: min(1.0, max(0.0, v * factor)) for h, v in irr_base.items()},
            grid_price=dict(price_base),
            ev_load=dict(ev_weekday),
        ))

    for i in range(n_weekends):
        factor = (1.0 + rng.uniform(-0.10, 0.05)) if with_seasonal_variation else 1.0
        days.append(RepresentativeDay(
            day_id=n_weekdays + i + 1,
            day_type="weekend",
            weight=n_weekends / total_days,
            irradiance_cf={h: min(1.0, max(0.0, v * factor)) for h, v in irr_base.items()},
            grid_price=dict(price_base),
            ev_load=dict(ev_weekend),
        ))

    return days


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 6 — Horizonte Multi-dia")
    print("=" * 60)

    days = generate_synthetic_representative_days(n_weekdays=5, n_weekends=2, seed=42)

    print(f"\n{len(days)} dias representativos gerados:")
    print(f"{'ID':>4} | {'Tipo':<10} | {'Peso':>6} | {'E_EV (kWh)':>12} | {'Pico_EV (kW)':>14}")
    print("-" * 55)
    for d in days:
        print(
            f"{d.day_id:>4} | {d.day_type:<10} | {d.weight:>6.3f} | "
            f"{d.total_ev_energy():>12.1f} | {d.peak_ev_load():>14.1f}"
        )

    print(f"\nConstruindo modelo multi-dia ({len(days)} dias × 24h = {len(days)*24} períodos)...")
    model = build_model_multiday(days)
    print(f"  Horizonte total: {len(days)*24} períodos")
    print(f"  Variáveis de investimento: P_pv_cap, E_bess_cap, P_trafo_cap")
    print(f"  SOC contínuo entre dias (sem reset inter-dia)")
    print(f"  Restrição cíclica: SOC[{len(days)*24}] == soc_initial * E_bess_cap")

    print("\nTentando redução k-means (requer scikit-learn)...")
    try:
        irr_hist = [
            {h: max(0, min(1, 0.8 * days[0].irradiance_cf.get(h, 0) + 0.1 * (i % 3))) for h in range(1, 25)}
            for i in range(30)
        ]
        ev_hist = [
            {h: days[0].ev_load.get(h, 0) * (0.8 + 0.2 * ((i * 7 + h) % 5) / 4) for h in range(1, 25)}
            for i in range(30)
        ]
        rep_days, weights = reduce_scenarios_kmeans(irr_hist, ev_hist, n_clusters=3, random_state=0)
        print(f"  Redução de 30 → {len(rep_days)} dias representativos")
        for rd, w in zip(rep_days, weights):
            print(f"    Cluster {rd.day_id}: peso={w:.3f} | E_EV={rd.total_ev_energy():.1f} kWh/dia")
    except ImportError as e:
        print(f"  [AVISO] {e}")
