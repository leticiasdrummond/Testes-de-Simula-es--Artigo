from pyomo.environ import (
    AbstractModel,
    Constraint,
    Objective,
    Param,
    RangeSet,
    SolverFactory,
    Var,
    value,
    minimize,
    NonNegativeReals,
    PositiveIntegers,
    PositiveReals,
    UnitInterval,
)
from pyomo.opt import SolverStatus, TerminationCondition
from pathlib import Path


model = AbstractModel()

# Horizonte temporal discreto do problema (numero total de intervalos de operacao).
model.N = Param(within=PositiveIntegers)

# Conjunto de tempo: representa cada passo temporal do horizonte de planejamento.
model.T = RangeSet(1, model.N)

# Geracao fotovoltaica disponivel em cada intervalo de tempo.
model.PV_gen = Param(model.T, within=NonNegativeReals)

# Demanda eletrica da carga em cada intervalo de tempo.
model.Load = Param(model.T, within=NonNegativeReals)

# Preco de compra de energia da rede em cada intervalo de tempo.
model.buy_price = Param(model.T, within=NonNegativeReals)

# Eficiencia de carregamento do sistema de armazenamento (fracao entre 0 e 1).
model.eta_ch = Param(within=UnitInterval)

# Eficiencia de descarregamento do sistema de armazenamento (fracao entre 0 e 1).
model.eta_dch = Param(within=UnitInterval)

# Capacidade nominal de energia do banco de baterias (BESS).
model.W_BESS = Param(within=NonNegativeReals)

# Limite maximo de potencia instantanea comprada da rede.
model.P_buy_max = Param(within=NonNegativeReals)

# Duracao de cada intervalo de tempo do modelo.
model.delta_t = Param(within=PositiveReals)

## Inclusao de variaveis de decisao:

# Potencia eletrica importada da rede para atendimento da demanda no intervalo t.
model.P_buy = Var(model.T, within=NonNegativeReals)

# Potencia eletrica exportada para a rede no intervalo t, representando excedentes energeticos.
model.P_sell = Var(model.T, within=NonNegativeReals)

# Potencia de carregamento da bateria no intervalo t, associada ao armazenamento de energia.
model.P_ch = Var(model.T, within=NonNegativeReals)

# Potencia de descarregamento da bateria no intervalo t, associada ao suprimento de energia armazenada.
model.P_dch = Var(model.T, within=NonNegativeReals)

# Estado de carga da bateria (SOC) no intervalo t, representando o nivel de energia acumulada.
model.S = Var(model.T, within=NonNegativeReals)


# Definicao da funcao objetivo.
def objective_rule(model):
    return sum(model.buy_price[t] * model.P_buy[t] for t in model.T)


model.objective = Objective(rule=objective_rule, sense=minimize)


# Balanco de potencia por periodo.
def energy_balance_rule(model, t):
    return (
        model.eta_dch * model.P_dch[t] + model.PV_gen[t] + model.P_buy[t]
        == model.Load[t] + model.P_ch[t] / model.eta_ch + model.P_sell[t]
    )


model.energy_balance = Constraint(model.T, rule=energy_balance_rule)


# Dinamica do SOC no primeiro periodo.
def battery_dynamics_initial_rule(model, t):
    if t != 1:
        return Constraint.Skip
    return model.S[t] == (model.P_ch[t] - model.P_dch[t]) * model.delta_t


model.battery_dynamics_initial = Constraint(model.T, rule=battery_dynamics_initial_rule)


# Dinamica recursiva do SOC para t > 1.
def battery_dynamics_recursive_rule(model, t):
    if t == 1:
        return Constraint.Skip
    return model.S[t] == model.S[t - 1] + (model.P_ch[t] - model.P_dch[t]) * model.delta_t


model.battery_dynamics_recursive = Constraint(model.T, rule=battery_dynamics_recursive_rule)


# Limite de energia armazenada no BESS.
def battery_energy_limit_rule(model, t):
    return (0, model.S[t], model.W_BESS)


model.battery_energy_limit = Constraint(model.T, rule=battery_energy_limit_rule)


# Limite de compra instantanea da rede.
def grid_purchase_limit_rule(model, t):
    return (0, model.P_buy[t], model.P_buy_max)


model.grid_purchase_limit = Constraint(model.T, rule=grid_purchase_limit_rule)


def _format_num(numero):
    return f"{numero:.6f}"


def write_report_artigo(instance, results, data_path, report_path):
    n_periodos = int(value(instance.N))
    objetivo = value(instance.objective)

    energia_total_carga = sum(value(instance.Load[t]) * value(instance.delta_t) for t in instance.T)
    energia_total_pv = sum(value(instance.PV_gen[t]) * value(instance.delta_t) for t in instance.T)
    energia_total_rede = sum(value(instance.P_buy[t]) * value(instance.delta_t) for t in instance.T)
    energia_total_exportada = sum(value(instance.P_sell[t]) * value(instance.delta_t) for t in instance.T)
    energia_total_carga_bess = sum(value(instance.P_ch[t]) * value(instance.delta_t) for t in instance.T)
    energia_total_descarga_bess = sum(value(instance.P_dch[t]) * value(instance.delta_t) for t in instance.T)
    soc_min = min(value(instance.S[t]) for t in instance.T)
    soc_max = max(value(instance.S[t]) for t in instance.T)

    linhas = [
        "RELATORIO AUDITADO - OTIMIZACAO DO DESPACHO ENERGETICO",
        "",
        "1. Objetivo e escopo",
        "Este documento apresenta, de forma auditavel e reproduzivel, os parametros de entrada,",
        "as variaveis avaliadas e os resultados da otimizacao para operacao horaria da estacao",
        "com fotovoltaico e bateria. O foco e minimizar o custo de compra de energia da rede.",
        "",
        "2. Rastreabilidade da execucao",
        f"arquivo_dados,{data_path.name}",
        f"arquivo_relatorio,{report_path.name}",
        f"solver,gurobi",
        f"solver_status,{results.solver.status}",
        f"termination_condition,{results.solver.termination_condition}",
        "",
        "3. Parametros globais utilizados",
        "parametro,valor",
        f"N,{n_periodos}",
        f"eta_ch,{_format_num(value(instance.eta_ch))}",
        f"eta_dch,{_format_num(value(instance.eta_dch))}",
        f"W_BESS,{_format_num(value(instance.W_BESS))}",
        f"P_buy_max,{_format_num(value(instance.P_buy_max))}",
        f"delta_t,{_format_num(value(instance.delta_t))}",
        "",
        "4. Indicadores agregados de resultado",
        "indicador,valor",
        f"objetivo_total,{_format_num(objetivo)}",
        f"energia_total_carga,{_format_num(energia_total_carga)}",
        f"energia_total_pv,{_format_num(energia_total_pv)}",
        f"energia_total_importada_rede,{_format_num(energia_total_rede)}",
        f"energia_total_exportada_rede,{_format_num(energia_total_exportada)}",
        f"energia_total_carregamento_bess,{_format_num(energia_total_carga_bess)}",
        f"energia_total_descarregamento_bess,{_format_num(energia_total_descarga_bess)}",
        f"soc_minimo,{_format_num(soc_min)}",
        f"soc_maximo,{_format_num(soc_max)}",
        "",
        "5. Interpretacao tecnica dos resultados",
        "A solucao obtida representa o despacho de menor custo sob as restricoes fisicas do sistema.",
        "O perfil horario de compra da rede (P_buy) evidencia quando o sistema precisou de suporte externo,",
        "enquanto P_ch, P_dch e S descrevem o papel da bateria no deslocamento de energia ao longo do dia.",
        "A comparacao entre energia fotovoltaica, carga e intercambio com a rede permite revisar a coerencia",
        "operacional da solucao e apoiar colaboracao entre equipes tecnica, economica e de validacao.",
        "",
        "6. Serie temporal completa para colaboracao e revisao",
        "t,PV_gen,Load,buy_price,P_buy,P_sell,P_ch,P_dch,S",
    ]

    for t in instance.T:
        linhas.append(
            ",".join(
                [
                    str(int(t)),
                    _format_num(value(instance.PV_gen[t])),
                    _format_num(value(instance.Load[t])),
                    _format_num(value(instance.buy_price[t])),
                    _format_num(value(instance.P_buy[t])),
                    _format_num(value(instance.P_sell[t])),
                    _format_num(value(instance.P_ch[t])),
                    _format_num(value(instance.P_dch[t])),
                    _format_num(value(instance.S[t])),
                ]
            )
        )

    report_path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    base_dir = Path(__file__).resolve().parent
    data_path = base_dir / "data.dat"
    report_path = base_dir / "relatorio1.txt"

    instance = model.create_instance(str(data_path))

    solver = SolverFactory("gurobi")
    if not solver.available(False):
        raise RuntimeError(
            "Solver 'gurobi' indisponivel. Verifique instalacao/licenca e disponibilidade do gurobi_cl."
        )

    results = solver.solve(instance, tee=False)
    status = results.solver.status
    termination = results.solver.termination_condition

    if status != SolverStatus.ok or termination != TerminationCondition.optimal:
        raise RuntimeError(
            "Resolucao sem otimalidade confirmada. "
            f"status={status}, termination_condition={termination}."
        )

    write_report_artigo(instance, results, data_path, report_path)
    print(f"Relatorio auditado salvo em: {report_path}")


if __name__ == "__main__":
    main()
