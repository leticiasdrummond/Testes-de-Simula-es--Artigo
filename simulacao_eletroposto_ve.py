"""
Simulacao de carregamento de veiculos eletricos (VE) em eletroposto no Brasil.

Objetivo:
- Combinar uma metodologia inspirada em estudos chineses de perfil de trafego
  (curvas horarias de chegada com picos) com tecnologias de recarga comuns no Brasil.
- Comparar analises deterministicas e estocasticas.
- Avaliar cenarios de dia tipico, anti-tipico e casos aleatorios para contraste.

Saidas:
- Relatorio textual em "relatorio_eletroposto_ve.txt"
- Tabela CSV em "resultado_eletroposto_ve.csv"

Uso:
    python simulacao_eletroposto_ve.py

Referencias metodologicas e de calibracao:
- Xi, X.; Sioshansi, R.; Marano, V. (2013).
    Simulation-optimization model for a station-level electric vehicle charging
    infrastructure operation problem. Transportation Research Part D,
    22, 60-69.
- Zhao, H.; Zhang, C.; Hu, Z.; Song, Y.; Wang, J.; Lin, X. (2016).
    A review of electric vehicle charging station capacity planning and location
    optimization from the perspective of queuing theory and transportation
    network models. IEEE Access, 4, 8635-8648.
- ABVE. Associacao Brasileira do Veiculo Eletrico (2025).
    Relatorio anual de eletromobilidade e infraestrutura de recarga no Brasil.
- EPE. Empresa de Pesquisa Energetica (2025).
    Plano Decenal de Expansao de Energia 2035 - Caderno de Eletromobilidade.
- Shell Recharge (2024/2025). Informacoes publicas de operacao de hubs de
    recarga rapida (Brasil e internacional).
- EDP Brasil (2024/2025). Dados publicos de operacao de recarga e tempos
    medios de sessao.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import math
import random
from typing import Dict, Iterable, List, Tuple


MIN_PER_DAY = 24 * 60
SLOT_MIN = 15
SLOTS_PER_DAY = MIN_PER_DAY // SLOT_MIN


@dataclass(frozen=True)
class VehicleTech:
    name: str
    battery_kwh: float
    ac_limit_kw: float
    dc_limit_kw: float
    target_soc: float


@dataclass(frozen=True)
class ChargerTech:
    name: str
    power_kw: float
    is_dc: bool


@dataclass
class ChargerUnit:
    id_name: str
    power_kw: float
    is_dc: bool
    available_at_min: float = 0.0


@dataclass
class Session:
    arrival_min: float
    start_min: float
    end_min: float
    energy_kwh: float
    charger_power_kw: float
    wait_min: float


@dataclass
class Metrics:
    total_arrivals: int
    served: int
    total_energy_kwh: float
    mean_wait_min: float
    p95_wait_min: float
    peak_kw: float
    load_factor: float
    utilization: float


def base_vehicle_mix_brasil(year: int) -> Dict[VehicleTech, float]:
    """
    Mix simplificado de tecnologias VE no Brasil e tendencia de evolucao.
    Valores representam participacao aproximada da frota que utiliza o eletroposto.
    """

    compact = VehicleTech("BEV_compacto", 42.0, 7.4, 70.0, 0.85)
    suv = VehicleTech("BEV_suv", 68.0, 11.0, 120.0, 0.85)
    utilitario = VehicleTech("BEV_utilitario_leve", 78.0, 11.0, 90.0, 0.9)

    if year <= 2026:
        return {compact: 0.52, suv: 0.36, utilitario: 0.12}
    if year <= 2030:
        return {compact: 0.40, suv: 0.43, utilitario: 0.17}
    return {compact: 0.31, suv: 0.48, utilitario: 0.21}


def charger_park_by_year(year: int) -> Dict[ChargerTech, int]:
    """
    Tecnologias de recarga reconhecidas no Brasil e sua evolucao esperada.
    - AC tipo 2: uso em estadias mais longas.
    - DC CCS2: recarga rapida, principal vetor de expansao.
    """

    ac_7 = ChargerTech("AC_7kW", 7.4, False)
    ac_22 = ChargerTech("AC_22kW", 22.0, False)
    dc_60 = ChargerTech("DC_60kW", 60.0, True)
    dc_120 = ChargerTech("DC_120kW", 120.0, True)

    # Calibracao orientada por mercado brasileiro (ABVE 2025): ~84% AC e ~16% DC.
    if year <= 2026:
        return {ac_7: 7, ac_22: 3, dc_60: 1, dc_120: 1}
    if year <= 2030:
        return {ac_7: 8, ac_22: 5, dc_60: 1, dc_120: 1}
    return {ac_7: 8, ac_22: 6, dc_60: 2, dc_120: 1}


def normalize_profile(values: Iterable[float]) -> List[float]:
    vals = [max(0.0, float(v)) for v in values]
    s = sum(vals)
    if s <= 0:
        return [1.0 / len(vals)] * len(vals)
    return [v / s for v in vals]


def hourly_profile_typical() -> List[float]:
    """
    Dia tipico urbano com dois picos (manha e fim de tarde),
    inspirado em curvas de trafego usadas em estudos chineses.
    """

    raw = [
        0.20,
        0.15,
        0.12,
        0.10,
        0.12,
        0.30,
        0.65,
        0.95,
        0.85,
        0.58,
        0.45,
        0.42,
        0.46,
        0.55,
        0.66,
        0.83,
        1.00,
        0.94,
        0.80,
        0.62,
        0.47,
        0.36,
        0.30,
        0.25,
    ]
    return normalize_profile(raw)


def hourly_profile_anti_typical() -> List[float]:
    """
    Dia anti-tipico: deslocamento reduzido no horario comercial e
    reforco relativo no fim da noite/madrugada (ex.: clima severo,
    interrupcoes urbanas, comportamento nao padrao).
    """

    raw = [
        0.38,
        0.30,
        0.24,
        0.20,
        0.18,
        0.22,
        0.32,
        0.36,
        0.34,
        0.30,
        0.28,
        0.27,
        0.30,
        0.34,
        0.40,
        0.52,
        0.64,
        0.70,
        0.74,
        0.79,
        0.83,
        0.88,
        0.80,
        0.58,
    ]
    return normalize_profile(raw)


def expand_hourly_to_slots(hourly_profile: List[float]) -> List[float]:
    slot_profile = []
    for hour_weight in hourly_profile:
        for _ in range(60 // SLOT_MIN):
            slot_profile.append(hour_weight)
    return normalize_profile(slot_profile)


def build_charger_units(park: Dict[ChargerTech, int]) -> List[ChargerUnit]:
    units: List[ChargerUnit] = []
    for charger, qty in park.items():
        for i in range(qty):
            units.append(
                ChargerUnit(
                    id_name=f"{charger.name}_{i + 1}",
                    power_kw=charger.power_kw,
                    is_dc=charger.is_dc,
                )
            )
    return units


def weighted_choice(rng: random.Random, weighted_items: Dict[object, float]) -> object:
    x = rng.random()
    cumulative = 0.0
    selected = None
    for item, w in weighted_items.items():
        cumulative += w
        if x <= cumulative:
            selected = item
            break
    if selected is None:
        selected = list(weighted_items.keys())[-1]
    return selected


def sampled_arrival_soc(rng: random.Random, anti_typical: bool) -> float:
    """
    SOC de chegada: em anti-tipico, assume-se maior dispersao e menor SOC medio.
    """

    if anti_typical:
        soc = rng.betavariate(2.0, 5.3)
    else:
        soc = rng.betavariate(2.7, 4.8)
    return min(0.75, max(0.08, soc))


def sample_energy_need_kwh(tech: VehicleTech, arrival_soc: float, rng: random.Random) -> float:
    target_soc = tech.target_soc
    if arrival_soc >= target_soc:
        return 4.0 + 6.0 * rng.random()
    return (target_soc - arrival_soc) * tech.battery_kwh


def effective_charging_power(tech: VehicleTech, charger: ChargerUnit) -> float:
    if charger.is_dc:
        return min(tech.dc_limit_kw, charger.power_kw)
    return min(tech.ac_limit_kw, charger.power_kw)


def realistic_charging_power(soc_current: float, max_power_kw: float, is_dc: bool) -> float:
    """
    Curva simplificada nao-linear para refletir tapering de potencia por SOC.
    DC tem reducao mais acentuada apos 80% SOC; AC apresenta tapering mais suave.
    """
    if soc_current < 0.20:
        return max_power_kw * (0.85 if is_dc else 0.90)
    if soc_current < 0.80:
        return max_power_kw

    reduction_end = 0.30 if is_dc else 0.50
    reduction_factor = 1.0 - ((soc_current - 0.80) / 0.20) * (1.0 - reduction_end)
    return max(0.05 * max_power_kw, max_power_kw * reduction_factor)


def charging_duration_min_nonlinear(
    energy_need_kwh: float,
    battery_kwh: float,
    arrival_soc: float,
    target_soc: float,
    max_power_kw: float,
    is_dc: bool,
    efficiency: float,
) -> float:
    """
    Estima o tempo de recarga por integracao em passos de 1 minuto.
    """
    soc_current = max(0.0, min(1.0, arrival_soc))
    soc_limit = max(soc_current, min(1.0, target_soc))

    charged = 0.0
    minutes = 0.0

    while charged < energy_need_kwh and soc_current < soc_limit:
        power_kw = realistic_charging_power(soc_current, max_power_kw=max_power_kw, is_dc=is_dc)
        energy_step = (power_kw * efficiency) / 60.0
        charged += energy_step
        soc_current = min(1.0, soc_current + energy_step / battery_kwh)
        minutes += 1.0

        if minutes >= 240.0:
            break

    return max(1.0, minutes)


def preferred_charger_pool(energy_need_kwh: float, chargers: List[ChargerUnit]) -> List[ChargerUnit]:
    if energy_need_kwh <= 16.0:
        ac = [c for c in chargers if not c.is_dc]
        if ac:
            return ac
    dc = [c for c in chargers if c.is_dc]
    if dc:
        return dc
    return chargers


def assign_vehicle(
    arrival_min: float,
    energy_need_kwh: float,
    arrival_soc: float,
    tech: VehicleTech,
    chargers: List[ChargerUnit],
    charging_efficiency: float,
) -> Session:
    preferred = preferred_charger_pool(energy_need_kwh, chargers)

    best_finish = float("inf")
    best_idx = -1
    best_start = 0.0
    best_power = 0.0

    for idx, charger in enumerate(chargers):
        if charger not in preferred:
            continue
        power_kw = effective_charging_power(tech, charger)
        if power_kw <= 0.1:
            continue
        start_min = max(arrival_min, charger.available_at_min)
        duration_min = charging_duration_min_nonlinear(
            energy_need_kwh=energy_need_kwh,
            battery_kwh=tech.battery_kwh,
            arrival_soc=arrival_soc,
            target_soc=tech.target_soc,
            max_power_kw=power_kw,
            is_dc=charger.is_dc,
            efficiency=charging_efficiency,
        )
        finish_min = start_min + duration_min
        if finish_min < best_finish:
            best_finish = finish_min
            best_idx = idx
            best_start = start_min
            best_power = power_kw

    if best_idx < 0:
        # Fallback extremo: usar qualquer carregador disponivel.
        for idx, charger in enumerate(chargers):
            power_kw = max(0.1, effective_charging_power(tech, charger))
            start_min = max(arrival_min, charger.available_at_min)
            duration_min = charging_duration_min_nonlinear(
                energy_need_kwh=energy_need_kwh,
                battery_kwh=tech.battery_kwh,
                arrival_soc=arrival_soc,
                target_soc=tech.target_soc,
                max_power_kw=power_kw,
                is_dc=charger.is_dc,
                efficiency=charging_efficiency,
            )
            finish_min = start_min + duration_min
            if finish_min < best_finish:
                best_finish = finish_min
                best_idx = idx
                best_start = start_min
                best_power = power_kw

    chosen = chargers[best_idx]
    chosen.available_at_min = best_finish

    return Session(
        arrival_min=arrival_min,
        start_min=best_start,
        end_min=best_finish,
        energy_kwh=energy_need_kwh,
        charger_power_kw=best_power,
        wait_min=max(0.0, best_start - arrival_min),
    )


def poisson_draw(rng: random.Random, mean: float) -> int:
    if mean <= 0.0:
        return 0
    if mean < 30.0:
        l = math.exp(-mean)
        k = 0
        p = 1.0
        while p > l:
            k += 1
            p *= rng.random()
        return max(0, k - 1)
    # Aproximacao normal para medias maiores.
    return max(0, int(round(rng.gauss(mean, math.sqrt(mean)))))


def load_series_from_sessions(sessions: List[Session]) -> List[float]:
    series = [0.0] * SLOTS_PER_DAY
    for s in sessions:
        for i in range(SLOTS_PER_DAY):
            slot_start = i * SLOT_MIN
            slot_end = slot_start + SLOT_MIN
            overlap = max(0.0, min(s.end_min, slot_end) - max(s.start_min, slot_start))
            if overlap > 0.0:
                # Potencia media no slot em kW.
                series[i] += s.charger_power_kw * (overlap / SLOT_MIN)
    return series


def summarize(sessions: List[Session], n_arrivals: int, n_chargers: int) -> Metrics:
    if not sessions:
        return Metrics(n_arrivals, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    waits = sorted(s.wait_min for s in sessions)
    p95_idx = int(0.95 * (len(waits) - 1))
    p95_wait = waits[p95_idx]
    total_energy = sum(s.energy_kwh for s in sessions)

    load = load_series_from_sessions(sessions)
    peak_kw = max(load)
    avg_kw = sum(load) / len(load)
    load_factor = avg_kw / peak_kw if peak_kw > 1e-9 else 0.0

    busy_minutes = sum(max(0.0, s.end_min - s.start_min) for s in sessions)
    utilization = busy_minutes / (n_chargers * MIN_PER_DAY)

    return Metrics(
        total_arrivals=n_arrivals,
        served=len(sessions),
        total_energy_kwh=total_energy,
        mean_wait_min=sum(waits) / len(waits),
        p95_wait_min=p95_wait,
        peak_kw=peak_kw,
        load_factor=load_factor,
        utilization=utilization,
    )


def deterministic_arrivals(total_daily_arrivals: int, slot_profile: List[float]) -> List[float]:
    arrivals: List[float] = []
    residue = 0.0
    for slot_idx, slot_weight in enumerate(slot_profile):
        expected = total_daily_arrivals * slot_weight + residue
        n = int(expected)
        residue = expected - n
        slot_start = slot_idx * SLOT_MIN
        slot_mid = slot_start + SLOT_MIN / 2.0
        arrivals.extend([slot_mid] * n)
    return arrivals


def stochastic_arrivals(
    rng: random.Random,
    total_daily_arrivals: float,
    slot_profile: List[float],
    perturbation: float,
) -> List[float]:
    arrivals: List[float] = []
    for slot_idx, slot_weight in enumerate(slot_profile):
        mean = total_daily_arrivals * slot_weight
        mean *= max(0.3, 1.0 + rng.uniform(-perturbation, perturbation))
        n = poisson_draw(rng, mean)
        slot_start = slot_idx * SLOT_MIN
        for _ in range(n):
            arrivals.append(slot_start + rng.random() * SLOT_MIN)
    arrivals.sort()
    return arrivals


def run_single_simulation(
    year: int,
    day_profile_name: str,
    deterministic: bool,
    total_daily_arrivals: int,
    rng_seed: int,
    perturbation: float,
) -> Metrics:
    rng = random.Random(rng_seed)
    anti_typical = day_profile_name == "anti_tipico"

    hourly = hourly_profile_anti_typical() if anti_typical else hourly_profile_typical()
    slot_profile = expand_hourly_to_slots(hourly)

    if deterministic:
        arrivals = deterministic_arrivals(total_daily_arrivals, slot_profile)
    else:
        arrivals = stochastic_arrivals(rng, float(total_daily_arrivals), slot_profile, perturbation=perturbation)

    vehicle_mix = base_vehicle_mix_brasil(year)
    chargers = build_charger_units(charger_park_by_year(year))

    sessions: List[Session] = []
    charging_efficiency = 0.93

    for arrival_min in arrivals:
        tech: VehicleTech = weighted_choice(rng, vehicle_mix)  # type: ignore[assignment]
        arrival_soc = sampled_arrival_soc(rng, anti_typical=anti_typical)
        energy_need = sample_energy_need_kwh(tech=tech, arrival_soc=arrival_soc, rng=rng)
        s = assign_vehicle(
            arrival_min=arrival_min,
            energy_need_kwh=energy_need,
            arrival_soc=arrival_soc,
            tech=tech,
            chargers=chargers,
            charging_efficiency=charging_efficiency,
        )
        sessions.append(s)

    return summarize(sessions=sessions, n_arrivals=len(arrivals), n_chargers=len(chargers))


def mean_metrics(metrics_list: List[Metrics]) -> Metrics:
    if not metrics_list:
        return Metrics(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n = len(metrics_list)
    return Metrics(
        total_arrivals=int(round(sum(m.total_arrivals for m in metrics_list) / n)),
        served=int(round(sum(m.served for m in metrics_list) / n)),
        total_energy_kwh=sum(m.total_energy_kwh for m in metrics_list) / n,
        mean_wait_min=sum(m.mean_wait_min for m in metrics_list) / n,
        p95_wait_min=sum(m.p95_wait_min for m in metrics_list) / n,
        peak_kw=sum(m.peak_kw for m in metrics_list) / n,
        load_factor=sum(m.load_factor for m in metrics_list) / n,
        utilization=sum(m.utilization for m in metrics_list) / n,
    )


def format_metrics_row(case_name: str, year: int, mode: str, m: Metrics) -> Dict[str, str]:
    return {
        "caso": case_name,
        "ano": str(year),
        "modo": mode,
        "chegadas": f"{m.total_arrivals}",
        "atendidos": f"{m.served}",
        "energia_kwh": f"{m.total_energy_kwh:.2f}",
        "espera_media_min": f"{m.mean_wait_min:.2f}",
        "espera_p95_min": f"{m.p95_wait_min:.2f}",
        "pico_kw": f"{m.peak_kw:.2f}",
        "fator_carga": f"{m.load_factor:.4f}",
        "utilizacao": f"{m.utilization:.4f}",
    }


def run_study() -> List[Dict[str, str]]:
    years = [2026, 2030, 2035]

    # Intensidade de trafego (chegadas diarias esperadas) por tipo de dia.
    demand_by_profile = {
        "tipico": 160,
        "anti_tipico": 115,
    }

    rows: List[Dict[str, str]] = []
    monte_carlo_samples = 80

    # Casos aleatorios para comparacao: cada caso altera variabilidade/choque de demanda.
    random_cases = {
        "aleatorio_base": 0.20,
        "aleatorio_chuva_evento": 0.35,
        "aleatorio_sobressalto_local": 0.50,
    }

    for year in years:
        for profile_name, daily_demand in demand_by_profile.items():
            det = run_single_simulation(
                year=year,
                day_profile_name=profile_name,
                deterministic=True,
                total_daily_arrivals=daily_demand,
                rng_seed=1100 + year,
                perturbation=0.0,
            )
            rows.append(format_metrics_row(profile_name, year, "deterministico", det))

            metrics_stochastic: List[Metrics] = []
            for s in range(monte_carlo_samples):
                metrics_stochastic.append(
                    run_single_simulation(
                        year=year,
                        day_profile_name=profile_name,
                        deterministic=False,
                        total_daily_arrivals=daily_demand,
                        rng_seed=7000 + year * 10 + s,
                        perturbation=0.20,
                    )
                )
            rows.append(
                format_metrics_row(
                    profile_name,
                    year,
                    f"estocastico_mc{monte_carlo_samples}",
                    mean_metrics(metrics_stochastic),
                )
            )

        for case_name, perturb in random_cases.items():
            metrics_case: List[Metrics] = []
            for s in range(monte_carlo_samples):
                # Caso aleatorio usando perfil tipico como base de comparacao.
                metrics_case.append(
                    run_single_simulation(
                        year=year,
                        day_profile_name="tipico",
                        deterministic=False,
                        total_daily_arrivals=demand_by_profile["tipico"],
                        rng_seed=9000 + year * 20 + s,
                        perturbation=perturb,
                    )
                )
            rows.append(
                format_metrics_row(
                    case_name,
                    year,
                    f"estocastico_mc{monte_carlo_samples}",
                    mean_metrics(metrics_case),
                )
            )

    return rows


def save_csv(rows: List[Dict[str, str]], csv_path: Path) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_report(rows: List[Dict[str, str]], report_path: Path) -> None:
    lines: List[str] = []
    lines.append("ANALISE DE ELETROPOSTO - BRASIL (Deterministico x Estocastico)")
    lines.append("Metodologia: perfis de trafego inspirados em referencias chinesas + tecnologias locais")
    lines.append("")
    lines.append("Colunas: caso; ano; modo; chegadas; atendidos; energia_kwh; espera_media_min; espera_p95_min; pico_kw; fator_carga; utilizacao")

    for r in rows:
        lines.append(
            "; ".join(
                [
                    r["caso"],
                    r["ano"],
                    r["modo"],
                    r["chegadas"],
                    r["atendidos"],
                    r["energia_kwh"],
                    r["espera_media_min"],
                    r["espera_p95_min"],
                    r["pico_kw"],
                    r["fator_carga"],
                    r["utilizacao"],
                ]
            )
        )

    lines.append("")
    lines.append("Leitura rapida:")
    lines.append("- Compare tipico/anti_tipico em cada ano para robustez operacional.")
    lines.append("- Compare deterministico com estocastico para risco de filas e pico de demanda.")
    lines.append("- Casos aleatorios medem sensibilidade a choques de trafego.")

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    csv_path = base_dir / "saida" / "resultado_eletroposto_ve.csv"
    report_path = base_dir / "saida" / "relatorio_eletroposto_ve.txt"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows = run_study()
    save_csv(rows, csv_path)
    save_report(rows, report_path)

    print("Analise concluida.")
    print(f"CSV salvo em: {csv_path}")
    print(f"Relatorio salvo em: {report_path}")


if __name__ == "__main__":
    main()
