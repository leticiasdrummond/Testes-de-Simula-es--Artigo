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


model = AbstractModel()

# Horizonte temporal discreto do problema (número total de intervalos de operação).
model.N = Param(within=PositiveIntegers)

# Conjunto de tempo: representa cada passo temporal do horizonte de planejamento.
model.T = RangeSet(1, model.N)

# Geração fotovoltaica disponível em cada intervalo de tempo.
model.PV_gen = Param(model.T, within=NonNegativeReals)

# Demanda elétrica da carga em cada intervalo de tempo.
model.Load = Param(model.T, within=NonNegativeReals)

# Preço de compra de energia da rede em cada intervalo de tempo.
model.buy_price = Param(model.T, within=NonNegativeReals)

# Eficiência de carregamento do sistema de armazenamento (fração entre 0 e 1).
model.eta_ch = Param(within=UnitInterval)

# Eficiência de descarregamento do sistema de armazenamento (fração entre 0 e 1).
model.eta_dch = Param(within=UnitInterval)

# Capacidade nominal de energia do banco de baterias (BESS).
model.W_BESS = Param(within=NonNegativeReals)

# Limite máximo de potência instantânea comprada da rede.
model.P_buy_max = Param(within=NonNegativeReals)

# Duração de cada intervalo de tempo do modelo.
model.delta_t = Param(within=PositiveReals)

## Inclusão de variáveis de decisão:

# Potência elétrica importada da rede para atendimento da demanda no intervalo t.
model.P_buy = Var(model.T, within=NonNegativeReals)

# Potência elétrica exportada para a rede no intervalo t, representando excedentes energéticos.
model.P_sell = Var(model.T, within=NonNegativeReals)

# Potência de carregamento da bateria no intervalo t, associada ao armazenamento de energia.
model.P_ch = Var(model.T, within=NonNegativeReals)

# Potência de descarregamento da bateria no intervalo t, associada ao suprimento de energia armazenada.
model.P_dch = Var(model.T, within=NonNegativeReals)

# Estado de carga da bateria (SOC) no intervalo t, representando o nível de energia acumulada.
model.S = Var(model.T, within=NonNegativeReals)

## Definição da função objetivo:
def objective_rule(model):
    # A função objetivo representa o dispêndio total com importação de energia da rede
    # ao longo do horizonte de planejamento, ponderado pelos preços horários de compra.
    return sum(model.buy_price[t] * model.P_buy[t] for t in model.T)


model.objective = Objective(rule=objective_rule, sense=minimize)


def energy_balance_rule(model, t):
    # O balanço de potência impõe conservação de energia em cada intervalo, garantindo
    # que as fontes disponíveis da microrrede/eletroposto (rede, FV e bateria em descarga)
    # atendam integralmente os usos energéticos (carga local, carregamento da bateria e exportação).
    return (
        model.eta_dch * model.P_dch[t] + model.PV_gen[t] + model.P_buy[t]
        == model.Load[t] + model.P_ch[t] / model.eta_ch + model.P_sell[t]
    )


model.energy_balance = Constraint(model.T, rule=energy_balance_rule)


def battery_dynamics_initial_rule(model, t):
    # No primeiro intervalo do horizonte, o SOC resulta exclusivamente do saldo líquido
    # entre carregamento e descarregamento, refletindo a condição inicial operacional do BESS.
    if t != 1:
        return Constraint.Skip
    return model.S[t] == (model.P_ch[t] - model.P_dch[t]) * model.delta_t


model.battery_dynamics_initial = Constraint(model.T, rule=battery_dynamics_initial_rule)


def battery_dynamics_recursive_rule(model, t):
    # A evolução temporal do SOC para t > 1 representa a memória energética do sistema
    # de armazenamento, acoplando decisões consecutivas de operação na microrrede/eletroposto.
    if t == 1:
        return Constraint.Skip
    return model.S[t] == model.S[t - 1] + (model.P_ch[t] - model.P_dch[t]) * model.delta_t


model.battery_dynamics_recursive = Constraint(model.T, rule=battery_dynamics_recursive_rule)


def battery_energy_limit_rule(model, t):
    # Este limite físico impõe que o SOC permaneça entre vazio técnico e capacidade nominal,
    # evitando planejamento inviável de armazenamento para a bateria do eletroposto.
    return (0, model.S[t], model.W_BESS)


model.battery_energy_limit = Constraint(model.T, rule=battery_energy_limit_rule)


def grid_purchase_limit_rule(model, t):
    # A restrição de intercâmbio com a rede representa a capacidade contratada/conectada
    # de importação, limitando a potência comprada em cada intervalo de operação.
    return (0, model.P_buy[t], model.P_buy_max)


model.grid_purchase_limit = Constraint(model.T, rule=grid_purchase_limit_rule)


if __name__ == "__main__":
    # A instanciação do AbstractModel com dados externos permite separar estrutura matemática
    # e cenário operacional, prática recomendada para estudos acadêmicos de microrredes.
    instance = model.create_instance("data.dat")

    # O resolvedor Gurobi é empregado para obtenção da solução ótima do problema linear,
    # fornecendo o despacho econômico de compra de energia e uso do armazenamento.
    solver = SolverFactory("gurobi")
    results = solver.solve(instance, tee=False)

    # O valor ótimo da função objetivo quantifica o custo total mínimo de suprimento elétrico
    # via importação da rede no horizonte analisado.
    print("Valor ótimo da função objetivo (custo total de compra):")
    print(value(instance.objective))

    # A trajetória de P_buy[t] indica o perfil temporal de dependência da rede,
    # evidenciando períodos de maior sensibilidade tarifária e de maior demanda local.
    print("\nP_buy[t] - potência comprada da rede por intervalo:")
    for t in instance.T:
        print(f"t={t:2d}  P_buy={value(instance.P_buy[t]):8.4f}")

    # A evolução de S[t] descreve a estratégia ótima de carregamento e descarregamento
    # do BESS, permitindo interpretar o papel da bateria no suporte à operação do eletroposto.
    print("\nS[t] - estado de carga da bateria por intervalo:")
    for t in instance.T:
        print(f"t={t:2d}  S={value(instance.S[t]):8.4f}")