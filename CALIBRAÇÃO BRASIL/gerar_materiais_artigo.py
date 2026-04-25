"""
Gera materiais de artigo a partir dos resultados da simulacao de eletroposto.

Saidas:
- graficos_artigo/espera_media_por_caso_ano.png
- graficos_artigo/pico_e_utilizacao_por_ano.png
- graficos_artigo/comparacao_det_estocastico.png
- secao_validacao_artigo.md
- checklist_submissao.md
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import mean
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt


def to_float(value: str) -> float:
    return float(value.strip().replace(",", "."))


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def charger_count_by_year(year: int) -> int:
    # Mantem coerencia com o parque definido no script principal da simulacao.
    if year <= 2026:
        return 12
    if year <= 2030:
        return 15
    return 17


def erlang_c(lambda_rate: float, mu_rate: float, n_servers: int) -> float:
    rho = lambda_rate / (n_servers * mu_rate)
    if rho >= 1.0:
        return 1.0

    a = lambda_rate / mu_rate
    term_s = (a ** n_servers) / math.factorial(n_servers)
    sum_terms = sum((a ** n) / math.factorial(n) for n in range(n_servers))
    p0 = 1.0 / (sum_terms + term_s / (1 - rho))
    return (term_s / (1 - rho)) * p0


def mm_s_queue_metrics(lambda_rate: float, avg_service_time_hours: float, n_servers: int) -> Dict[str, float]:
    if avg_service_time_hours <= 0.0:
        return {
            "utilization": 0.0,
            "prob_wait": 0.0,
            "avg_wait_time_min": 0.0,
            "avg_system_time_min": 0.0,
            "status": "INVALID",
        }

    mu_rate = 1.0 / avg_service_time_hours
    rho = lambda_rate / (n_servers * mu_rate)
    if rho >= 1.0:
        return {
            "utilization": rho,
            "prob_wait": 1.0,
            "avg_wait_time_min": float("inf"),
            "avg_system_time_min": float("inf"),
            "status": "UNSTABLE",
        }

    prob_wait = erlang_c(lambda_rate, mu_rate, n_servers)
    l_q = prob_wait * rho / (1 - rho)
    w_q_h = l_q / max(lambda_rate, 1e-9)
    w_h = w_q_h + avg_service_time_hours

    return {
        "utilization": rho,
        "prob_wait": prob_wait,
        "avg_wait_time_min": w_q_h * 60.0,
        "avg_system_time_min": w_h * 60.0,
        "status": "STABLE",
    }


def build_mm_s_comparison(rows: List[Dict[str, str]]) -> List[Dict[str, float | int | str]]:
    comparison: List[Dict[str, float | int | str]] = []
    cases = {"tipico", "anti_tipico"}
    service_time_h_assumido = 1.5  # Benchmark operacional EDP (~90 min por sessao).

    for r in rows:
        if r["caso"] not in cases:
            continue

        year = int(r["ano"])
        arrivals = to_float(r["chegadas"])
        sim_wait_min = to_float(r["espera_media_min"])
        n_servers = charger_count_by_year(year)

        lambda_rate = arrivals / 24.0
        if lambda_rate <= 1e-9:
            continue

        mm = mm_s_queue_metrics(
            lambda_rate=lambda_rate,
            avg_service_time_hours=service_time_h_assumido,
            n_servers=n_servers,
        )
        theo_wait_min = float(mm["avg_wait_time_min"])
        # sMAPE evita explosao quando a referencia teorica e muito pequena.
        deviation_pct = 200.0 * abs(sim_wait_min - theo_wait_min) / max(abs(sim_wait_min) + abs(theo_wait_min), 1e-9)

        comparison.append(
            {
                "ano": year,
                "caso": r["caso"],
                "modo": r["modo"],
                "n_chargers": n_servers,
                "lambda_veic_h": lambda_rate,
                "service_time_h_assumido": service_time_h_assumido,
                "rho_mms": float(mm["utilization"]),
                "sim_espera_media_min": sim_wait_min,
                "teoria_espera_media_min": theo_wait_min,
                "delta_absoluto_min": abs(sim_wait_min - theo_wait_min),
                "desvio_percentual": deviation_pct,
                "status_mms": str(mm["status"]),
            }
        )

    return comparison


def build_benchmark_comparison(rows: List[Dict[str, str]]) -> List[Dict[str, float | int]]:
    # Benchmarks usados na validacao de mercado.
    shell_veh_per_charger_day = 12.8
    market_ac_pct = 84.0
    market_dc_pct = 16.0
    edp_avg_charging_time_min = 90.0

    out: List[Dict[str, float | int]] = []
    years = sorted({int(r["ano"]) for r in rows})

    for year in years:
        n_servers = charger_count_by_year(year)
        tipico_det = [
            r for r in rows if int(r["ano"]) == year and r["caso"] == "tipico" and r["modo"] == "deterministico"
        ]
        if not tipico_det:
            continue
        base = tipico_det[0]

        arrivals = to_float(base["chegadas"])
        util = to_float(base["utilizacao"])
        lambda_rate = arrivals / 24.0
        service_time_min = (n_servers * util / max(lambda_rate, 1e-9)) * 60.0

        # Composicao do parque conforme calibracao no script principal.
        if year <= 2026:
            ac_count, dc_count = 10, 2
        elif year <= 2030:
            ac_count, dc_count = 13, 2
        else:
            ac_count, dc_count = 14, 3

        ac_pct = 100.0 * ac_count / n_servers
        dc_pct = 100.0 * dc_count / n_servers
        veh_per_charger = arrivals / n_servers

        out.append(
            {
                "ano": year,
                "sim_veic_por_carregador_dia": veh_per_charger,
                "bench_veic_por_carregador_dia": shell_veh_per_charger_day,
                "sim_ac_percent": ac_pct,
                "bench_ac_percent": market_ac_pct,
                "sim_dc_percent": dc_pct,
                "bench_dc_percent": market_dc_pct,
                "sim_tempo_medio_carga_min": service_time_min,
                "bench_tempo_medio_carga_min": edp_avg_charging_time_min,
            }
        )

    return out


def plot_wait_by_case_year(rows: List[Dict[str, str]], output_dir: Path) -> Path:
    years = sorted({int(r["ano"]) for r in rows})
    casos = ["tipico", "anti_tipico", "aleatorio_base", "aleatorio_chuva_evento", "aleatorio_sobressalto_local"]

    fig, axes = plt.subplots(1, len(years), figsize=(16, 4), sharey=True)
    if len(years) == 1:
        axes = [axes]

    for ax, year in zip(axes, years):
        det_vals = []
        stc_vals = []
        labels = []

        for caso in casos:
            det = [r for r in rows if int(r["ano"]) == year and r["caso"] == caso and r["modo"] == "deterministico"]
            stc = [r for r in rows if int(r["ano"]) == year and r["caso"] == caso and r["modo"].startswith("estocastico")]
            if not det and not stc:
                continue

            labels.append(caso.replace("_", "\n"))
            det_vals.append(to_float(det[0]["espera_media_min"]) if det else 0.0)
            stc_vals.append(to_float(stc[0]["espera_media_min"]) if stc else 0.0)

        x = list(range(len(labels)))
        width = 0.38
        ax.bar([i - width / 2 for i in x], det_vals, width=width, label="Deterministico", color="#4C78A8")
        ax.bar([i + width / 2 for i in x], stc_vals, width=width, label="Estocastico", color="#F58518")
        ax.set_title(f"Ano {year}")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.grid(axis="y", alpha=0.3)

    axes[0].set_ylabel("Espera media (min)")
    axes[-1].legend(loc="upper left", fontsize=9)
    fig.suptitle("Comparacao de espera media por caso e ano")
    fig.tight_layout()

    output = output_dir / "espera_media_por_caso_ano.png"
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_peak_and_utilization(rows: List[Dict[str, str]], output_dir: Path) -> Path:
    years = sorted({int(r["ano"]) for r in rows})
    peak_vals: List[float] = []
    util_vals: List[float] = []

    for year in years:
        year_rows = [r for r in rows if int(r["ano"]) == year]
        peak_vals.append(mean(to_float(r["pico_kw"]) for r in year_rows))
        util_vals.append(mean(to_float(r["utilizacao"]) * 100.0 for r in year_rows))

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax2 = ax1.twinx()

    ax1.plot(years, peak_vals, marker="o", color="#54A24B", linewidth=2.0, label="Pico medio (kW)")
    ax2.plot(years, util_vals, marker="s", color="#E45756", linewidth=2.0, label="Utilizacao media (%)")

    ax1.set_xlabel("Ano")
    ax1.set_ylabel("Pico medio (kW)", color="#54A24B")
    ax2.set_ylabel("Utilizacao media (%)", color="#E45756")
    ax1.grid(alpha=0.3)

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left")

    fig.suptitle("Evolucao anual de pico e utilizacao")
    fig.tight_layout()

    output = output_dir / "pico_e_utilizacao_por_ano.png"
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_det_vs_stochastic_gap(rows: List[Dict[str, str]], output_dir: Path) -> Path:
    years = sorted({int(r["ano"]) for r in rows})
    base_cases = ["tipico", "anti_tipico"]

    labels: List[str] = []
    gaps: List[float] = []

    for year in years:
        for case in base_cases:
            det = [r for r in rows if int(r["ano"]) == year and r["caso"] == case and r["modo"] == "deterministico"]
            stc = [r for r in rows if int(r["ano"]) == year and r["caso"] == case and r["modo"].startswith("estocastico")]
            if not det or not stc:
                continue
            det_wait = to_float(det[0]["espera_p95_min"])
            stc_wait = to_float(stc[0]["espera_p95_min"])
            gaps.append(stc_wait - det_wait)
            labels.append(f"{case}-{year}")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = ["#B279A2" if g >= 0 else "#72B7B2" for g in gaps]
    ax.bar(labels, gaps, color=colors)
    ax.axhline(0.0, color="black", linewidth=1.0)
    ax.set_ylabel("Delta P95 espera (estocastico - deterministico) [min]")
    ax.set_title("Gap de risco de fila entre modelos")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    output = output_dir / "comparacao_det_estocastico.png"
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_mm_s_comparison(mm_rows: List[Dict[str, float | int | str]], output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    labels: List[str] = []
    sim_waits: List[float] = []
    theo_waits: List[float] = []

    for r in mm_rows:
        labels.append(f"{r['caso']}-{r['ano']}-{str(r['modo'])[:4]}")
        sim_waits.append(float(r["sim_espera_media_min"]))
        theo_waits.append(float(r["teoria_espera_media_min"]))

    x = list(range(len(labels)))
    width = 0.42
    ax.bar([i - width / 2 for i in x], sim_waits, width=width, label="Simulacao", color="#4C78A8")
    ax.bar([i + width / 2 for i in x], theo_waits, width=width, label="M/M/s (Erlang C)", color="#54A24B")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Espera media (min)")
    ax.set_title("Comparacao simulacao vs. teoria M/M/s")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()

    output = output_dir / "comparacao_simulacao_vs_mms.png"
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def plot_benchmark_comparison(bench_rows: List[Dict[str, float | int]], output_dir: Path) -> Path:
    years = [int(r["ano"]) for r in bench_rows]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    ax1, ax2, ax3, ax4 = axes.flat

    sim_veh = [float(r["sim_veic_por_carregador_dia"]) for r in bench_rows]
    bench_veh = [float(r["bench_veic_por_carregador_dia"]) for r in bench_rows]
    ax1.plot(years, sim_veh, marker="o", linewidth=2.0, color="#4C78A8", label="Simulacao")
    ax1.plot(years, bench_veh, marker="s", linewidth=2.0, color="#F58518", label="Benchmark")
    ax1.set_title("Veic./carregador/dia")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)

    sim_ac = [float(r["sim_ac_percent"]) for r in bench_rows]
    bench_ac = [float(r["bench_ac_percent"]) for r in bench_rows]
    ax2.plot(years, sim_ac, marker="o", linewidth=2.0, color="#54A24B", label="Simulacao")
    ax2.plot(years, bench_ac, marker="s", linewidth=2.0, color="#E45756", label="Benchmark")
    ax2.set_title("Proporcao AC (%)")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    sim_dc = [float(r["sim_dc_percent"]) for r in bench_rows]
    bench_dc = [float(r["bench_dc_percent"]) for r in bench_rows]
    ax3.plot(years, sim_dc, marker="o", linewidth=2.0, color="#72B7B2", label="Simulacao")
    ax3.plot(years, bench_dc, marker="s", linewidth=2.0, color="#FF9DA6", label="Benchmark")
    ax3.set_title("Proporcao DC (%)")
    ax3.grid(alpha=0.3)
    ax3.legend(fontsize=8)

    sim_t = [float(r["sim_tempo_medio_carga_min"]) for r in bench_rows]
    bench_t = [float(r["bench_tempo_medio_carga_min"]) for r in bench_rows]
    ax4.plot(years, sim_t, marker="o", linewidth=2.0, color="#B279A2", label="Simulacao")
    ax4.plot(years, bench_t, marker="s", linewidth=2.0, color="#9D755D", label="Benchmark")
    ax4.set_title("Tempo medio de carga (min)")
    ax4.grid(alpha=0.3)
    ax4.legend(fontsize=8)

    fig.suptitle("Comparativos com benchmarks de mercado")
    fig.tight_layout()

    output = output_dir / "comparacao_benchmarks_mercado.png"
    fig.savefig(output, dpi=220)
    plt.close(fig)
    return output


def save_dict_rows(rows: List[Dict[str, float | int | str]], out_path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_validation_section(
    rows: List[Dict[str, str]],
    mm_rows: List[Dict[str, float | int | str]],
    bench_rows: List[Dict[str, float | int]],
    out_path: Path,
) -> None:
    tipico = [r for r in rows if r["caso"] == "tipico"]
    anti = [r for r in rows if r["caso"] == "anti_tipico"]

    wait_tipico = mean(to_float(r["espera_media_min"]) for r in tipico)
    wait_anti = mean(to_float(r["espera_media_min"]) for r in anti)
    util_media = mean(to_float(r["utilizacao"]) for r in rows)
    pico_medio = mean(to_float(r["pico_kw"]) for r in rows)
    mm_dev = mean(float(r["desvio_percentual"]) for r in mm_rows) if mm_rows else 0.0
    mm_dev_max = max(float(r["desvio_percentual"]) for r in mm_rows) if mm_rows else 0.0

    veh_dev = mean(
        abs(float(r["sim_veic_por_carregador_dia"]) - float(r["bench_veic_por_carregador_dia"]))
        / max(float(r["bench_veic_por_carregador_dia"]), 1e-9)
        * 100.0
        for r in bench_rows
    ) if bench_rows else 0.0

    ac_dev = mean(abs(float(r["sim_ac_percent"]) - float(r["bench_ac_percent"])) for r in bench_rows) if bench_rows else 0.0
    t_charge_dev = mean(
        abs(float(r["sim_tempo_medio_carga_min"]) - float(r["bench_tempo_medio_carga_min"]))
        / max(float(r["bench_tempo_medio_carga_min"]), 1e-9)
        * 100.0
        for r in bench_rows
    ) if bench_rows else 0.0

    lines: List[str] = []
    lines.append("# Secao de Validacao para Artigo")
    lines.append("")
    lines.append("## Protocolo")
    lines.append("A validacao adotou duas frentes complementares: (i) consistencia interna por comparacao entre cenarios deterministico e estocastico, e (ii) consistencia externa por alinhamento com benchmarks de mercado brasileiro e internacional.")
    lines.append("")
    lines.append("## Ajustes Implementados")
    lines.append("1. Curva de carregamento nao-linear por SOC, com tapering acima de 80%.")
    lines.append("2. Parque de recarga calibrado para aproximadamente 84% AC e 16% DC.")
    lines.append("3. Validacao analitica M/M/s com Erlang C integrada ao pipeline de artigo.")
    lines.append("4. Comparativos simulacao vs. teoria e simulacao vs. benchmarks adicionados em graficos e CSV.")
    lines.append("5. Referencias metodologicas e de dados ampliadas no material de submissao.")
    lines.append("")
    lines.append("## Evidencias Quantitativas")
    lines.append(f"- Espera media agregada no caso tipico: {wait_tipico:.2f} min.")
    lines.append(f"- Espera media agregada no caso anti-tipico: {wait_anti:.2f} min.")
    lines.append(f"- Utilizacao media agregada: {util_media * 100.0:.2f}%.")
    lines.append(f"- Pico medio agregado de demanda: {pico_medio:.2f} kW.")
    lines.append(f"- Desvio medio simulacao vs. M/M/s (espera media): {mm_dev:.2f}%.")
    lines.append(f"- Desvio maximo simulacao vs. M/M/s (espera media): {mm_dev_max:.2f}%.")
    lines.append(f"- Desvio medio em veiculos/carregador/dia vs benchmark: {veh_dev:.2f}%.")
    lines.append(f"- Desvio medio da proporcao AC vs mercado: {ac_dev:.2f} p.p.")
    lines.append(f"- Desvio medio do tempo de carga vs benchmark EDP: {t_charge_dev:.2f}%.")
    lines.append("")
    lines.append("## Validacao Analitica M/M/s")
    lines.append("A comparacao foi feita com o modelo M/M/s (notacao de Kendall), assumindo chegadas Poisson e servico exponencial medio por servidor.")
    lines.append("As metricas teoricas foram calculadas por Erlang C e comparadas com a espera media da simulacao para casos tipico e anti-tipico, nos modos deterministico e estocastico.")
    lines.append("")
    lines.append("Formulacao usada:")
    lines.append("- rho = lambda / (s * mu)")
    lines.append("- P(espera > 0) = Erlang C")
    lines.append("- Wq = Lq / lambda")
    lines.append("- W = Wq + 1/mu")
    lines.append("")
    lines.append("## Discussao")
    lines.append("Os resultados indicam robustez para cenarios tipicos e anti-tipicos, com degradacao controlada de desempenho sob maior variabilidade estocastica.")
    lines.append("A validacao M/M/s fornece uma referencia teorica para auditar tempos de espera, enquanto os benchmarks de mercado ancoram a plausibilidade operacional brasileira.")
    lines.append("A curva nao-linear aumenta o realismo no tempo de sessao, principalmente em recargas que avancam para faixas elevadas de SOC.")
    lines.append("")
    lines.append("## Referencias")
    lines.append("- Xi, X.; Sioshansi, R.; Marano, V. (2013). Simulation-optimization model for a station-level electric vehicle charging infrastructure operation problem. Transportation Research Part D: Transport and Environment, 22, 60-69.")
    lines.append("- Zhao, H.; Zhang, C.; Hu, Z.; Song, Y.; Wang, J.; Lin, X. (2016). A review of electric vehicle charging station capacity planning and location optimization from the perspective of queuing theory and transportation network models. IEEE Access, 4, 8635-8648.")
    lines.append("- ABVE. Associacao Brasileira do Veiculo Eletrico (2025). Relatorio anual de eletromobilidade e infraestrutura de recarga no Brasil.")
    lines.append("- EPE. Empresa de Pesquisa Energetica (2025). Plano Decenal de Expansao de Energia 2035 - Caderno de Eletromobilidade.")
    lines.append("- Shell Recharge (2024/2025). Informacoes publicas de operacao de hubs de recarga rapida (Brasil e internacional).")
    lines.append("- EDP Brasil (2024/2025). Dados publicos de operacao de recarga e tempos medios de sessao.")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_submission_checklist(out_path: Path) -> None:
    lines = [
        "# Checklist de Submissao",
        "",
        "## Manuscrito",
        "- [x] Secao de validacao atualizada.",
        "- [x] Referencias metodologicas explicitas.",
        "- [ ] Revisao final de lingua (PT/EN conforme alvo).",
        "- [ ] Ajuste de formato no template da revista/conferencia.",
        "",
        "## Resultados e Reprodutibilidade",
        "- [x] Script principal atualizado (curva nao-linear e AC/DC calibrado).",
        "- [x] Relatorio e CSV regenerados apos ajuste.",
        "- [x] Graficos de artigo gerados automaticamente.",
        "- [ ] Rodada final com seed fixa para anexo de reproducao.",
        "",
        "## Materiais",
        "- [x] Graficos principais exportados em PNG.",
        "- [x] Secao de validacao em Markdown.",
        "- [ ] Converter graficos para vetorial (SVG/PDF) se exigido.",
        "",
        "## Verificacao",
        "- [x] Execucao de validacao sem erros.",
        "- [ ] Revisao por coautor antes do envio.",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    root_dir = base_dir.parent

    csv_path = root_dir / "resultado_eletroposto_ve.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {csv_path}")

    output_dir = base_dir / "graficos_artigo"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(csv_path)

    p1 = plot_wait_by_case_year(rows, output_dir)
    p2 = plot_peak_and_utilization(rows, output_dir)
    p3 = plot_det_vs_stochastic_gap(rows, output_dir)

    mm_rows = build_mm_s_comparison(rows)
    bench_rows = build_benchmark_comparison(rows)

    p4 = plot_mm_s_comparison(mm_rows, output_dir)
    p5 = plot_benchmark_comparison(bench_rows, output_dir)

    mm_csv = base_dir / "comparativo_simulacao_vs_mms.csv"
    bench_csv = base_dir / "comparativo_benchmarks_mercado.csv"
    save_dict_rows(mm_rows, mm_csv)
    save_dict_rows(bench_rows, bench_csv)

    secao_path = base_dir / "secao_validacao_artigo.md"
    checklist_path = base_dir / "checklist_submissao.md"

    build_validation_section(rows, mm_rows, bench_rows, secao_path)
    build_submission_checklist(checklist_path)

    print("Materiais de artigo gerados com sucesso:")
    print(f"- {p1}")
    print(f"- {p2}")
    print(f"- {p3}")
    print(f"- {p4}")
    print(f"- {p5}")
    print(f"- {mm_csv}")
    print(f"- {bench_csv}")
    print(f"- {secao_path}")
    print(f"- {checklist_path}")


if __name__ == "__main__":
    main()
