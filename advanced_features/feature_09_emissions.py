"""
Feature 9 — Modelo de Emissões de CO₂ e Intensidade de Carbono
===============================================================

Objetivo
--------
Quantificar a pegada de carbono da operação do eletroposto para:
  (a) análise ambiental de impacto climático;
  (b) elegibilidade a mecanismos de créditos de carbono (CBios, mercado voluntário);
  (c) comparação com alternativa de abastecimento por combustível fóssil;
  (d) inclusão de restrição de limite de emissões no modelo de otimização.

Contexto brasileiro (ONS/EPE)
------------------------------
O fator de emissão da rede elétrica brasileira varia conforme:
  - Matriz energética horária (predominância hidráulica + renováveis)
  - Despacho térmico (fator de emissão maior nas horas de pico)
  - Região elétrica (SIN: Sul, Sudeste, Norte, Nordeste)

Fator de emissão marginal (MEF — Marginal Emission Factor):
    Representa a geração adicional despachada para atender 1 kWh incremental
    de demanda. É o fator relevante para projetos de eficiência/DG.

Fator de emissão médio (AEF — Average Emission Factor):
    Média ponderada da intensidade de carbono do parque gerador.
    Publicado anualmente pelo MCiD/SEEG (ex.: 0.074 kgCO₂/kWh para 2022 Brasil).

Fator de emissão horário (HEF — Hourly Emission Factor):
    Varia ao longo do dia conforme o despacho. Em horários de pico, o MEF
    pode ser 5–10x maior que o AEF médio anual.

Créditos de carbono
--------------------
Emissões evitadas [tCO₂eq/ano] = Emissões_ref - Emissões_projeto
    Emissões_ref = consumo VE * AEF_rede (linha de base: recarga da rede sem FV/BESS)
    Emissões_projeto = importação efetiva * HEF[t]

Valor dos créditos (CBios/VCU):
    V_carbono [BRL/ano] = emissoes_evitadas [tCO₂] * preco_carbono [BRL/tCO₂]

Referências
-----------
- MCiD/SEEG (2023) "Sistema de Estimativa de Emissões e Remoções de GEE."
- ONS (2023) "Fatores de Emissão para Estudos de Geração Distribuída."
- EPA (2022) "Emissions & Generation Resource Integrated Database (eGRID)."
- ISO 14064 — Quantification and reporting of greenhouse gas emissions.
- IPCC (2006) "Guidelines for National GHG Inventories."

Uso
---
    from advanced_features.feature_09_emissions import (
        EmissionsModel, ONSEmissionFactors, compute_emissions_report
    )

    factors = ONSEmissionFactors.brazil_national_2023()
    model = EmissionsModel(factors, carbon_price_brl_ton=80.0)
    report = model.compute_annual_report(grid_import_profile, pv_profile, ev_load_profile)
    report.print_summary()
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
# Fatores de emissão horários
# ---------------------------------------------------------------------------

@dataclass
class ONSEmissionFactors:
    """
    Fatores de emissão de CO₂ horários para o Sistema Interligado Nacional (SIN).

    Unidade: kgCO₂eq/kWh

    Nota: os valores abaixo são referências educacionais baseadas em dados
    públicos do ONS/SEEG. Para uso em estudos regulatórios, consulte as
    publicações anuais do MCiD/SEEG e do MAPA Metodológico da ANEEL.
    """

    hourly_aef: Dict[int, float]     # fator médio horário [kgCO₂/kWh]
    hourly_mef: Dict[int, float]     # fator marginal horário [kgCO₂/kWh]
    region: str                      # região do SIN
    year: int                        # ano de referência

    @property
    def annual_aef(self) -> float:
        """Fator de emissão médio anual [kgCO₂/kWh]."""
        return sum(self.hourly_aef.values()) / len(self.hourly_aef)

    @property
    def annual_mef(self) -> float:
        """Fator de emissão marginal médio anual [kgCO₂/kWh]."""
        return sum(self.hourly_mef.values()) / len(self.hourly_mef)

    @classmethod
    def brazil_national_2023(cls) -> "ONSEmissionFactors":
        """
        Perfil nacional médio para o Brasil (SIN) — 2023.
        Fonte: SEEG/MCiD, ONS (estimativa educacional).

        Características:
        - AEF médio anual: ~0.074 kgCO₂/kWh (matriz predominantemente renovável)
        - MEF médio: ~0.12-0.18 kgCO₂/kWh (despacho térmico nas pontas)
        - Pico de emissão: horários 17h-22h (pico de consumo + despacho térmico)
        """
        # Perfil horário diário (valores educacionais calibrados para o Brasil)
        hourly_aef = {
            1: 0.050, 2: 0.045, 3: 0.042, 4: 0.040, 5: 0.042, 6: 0.050,
            7: 0.065, 8: 0.080, 9: 0.085, 10: 0.082, 11: 0.078, 12: 0.075,
            13: 0.072, 14: 0.070, 15: 0.073, 16: 0.082, 17: 0.105, 18: 0.130,
            19: 0.145, 20: 0.150, 21: 0.135, 22: 0.110, 23: 0.080, 24: 0.060,
        }
        hourly_mef = {t: min(0.50, v * 2.2) for t, v in hourly_aef.items()}
        return cls(hourly_aef=hourly_aef, hourly_mef=hourly_mef, region="Nacional", year=2023)

    @classmethod
    def brazil_sudeste_2023(cls) -> "ONSEmissionFactors":
        """Perfil Sudeste (maior concentração de carga e térmica a gás)."""
        base = cls.brazil_national_2023()
        # Sudeste tem mais térmica a gás — fator maior nas pontas
        sudeste_aef = {t: v * 1.25 for t, v in base.hourly_aef.items()}
        sudeste_mef = {t: v * 1.30 for t, v in base.hourly_mef.items()}
        return cls(hourly_aef=sudeste_aef, hourly_mef=sudeste_mef, region="Sudeste", year=2023)

    @classmethod
    def brazil_nordeste_2023(cls) -> "ONSEmissionFactors":
        """Perfil Nordeste (alta participação de eólica — menor fator)."""
        base = cls.brazil_national_2023()
        nordeste_aef = {t: v * 0.65 for t, v in base.hourly_aef.items()}
        nordeste_mef = {t: v * 0.80 for t, v in base.hourly_mef.items()}
        return cls(hourly_aef=nordeste_aef, hourly_mef=nordeste_mef, region="Nordeste", year=2023)


# ---------------------------------------------------------------------------
# Relatório de emissões
# ---------------------------------------------------------------------------

@dataclass
class EmissionsReport:
    """Relatório de emissões anuais do eletroposto."""

    # Emissões da operação
    emissoes_grid_import_kgco2_ano: float   # emissões da importação da rede [kgCO₂/ano]
    emissoes_ev_comb_referencia_kgco2_ano: float  # emissões de referência (gasolina/diesel) [kgCO₂/ano]

    # Emissões evitadas
    emissoes_evitadas_vs_rede_kgco2_ano: float    # vs. linha de base rede sem FV [kgCO₂/ano]
    emissoes_evitadas_vs_combustivel_kgco2_ano: float  # vs. combustível fóssil [kgCO₂/ano]

    # Créditos de carbono
    creditos_carbono_tco2_ano: float        # créditos elegíveis [tCO₂/ano]
    receita_carbono_brl_ano: float          # receita potencial [BRL/ano]
    carbon_price_brl_ton: float

    # Intensidade
    intensidade_kgco2_kwh: float            # kgCO₂/kWh entregue aos VEs
    intensidade_gco2_km: float              # gCO₂/km equivalente (consumo 5 km/kWh)

    # Geração local
    energia_pv_kwh_ano: float               # energia FV gerada anualmente [kWh/ano]
    energia_grid_kwh_ano: float             # energia importada da rede [kWh/ano]
    fracao_renovavel: float                 # fração do total entregue de fonte renovável

    def print_summary(self) -> None:
        """Imprime relatório de emissões formatado."""
        print("\n" + "=" * 65)
        print("RELATÓRIO DE EMISSÕES DE CO₂ — ELETROPOSTO PV-BESS-REDE")
        print("=" * 65)

        print(f"\n{'Emissões da operação':}")
        print(f"  Importação da rede:          {self.emissoes_grid_import_kgco2_ano/1000:>10.2f} tCO₂/ano")
        print(f"  Intensidade carregamento:    {self.intensidade_kgco2_kwh*1000:>10.2f} gCO₂/kWh")
        print(f"  Equiv. emissão VE:           {self.intensidade_gco2_km:>10.2f} gCO₂/km")

        print(f"\n{'Emissões evitadas':}")
        print(f"  Vs. rede sem FV/BESS:        {self.emissoes_evitadas_vs_rede_kgco2_ano/1000:>10.2f} tCO₂/ano")
        print(f"  Vs. frota a gasolina:        {self.emissoes_evitadas_vs_combustivel_kgco2_ano/1000:>10.2f} tCO₂/ano")

        print(f"\n{'Créditos de carbono':}")
        print(f"  Volume elegível:             {self.creditos_carbono_tco2_ano:>10.2f} tCO₂/ano")
        print(f"  Preço carbono referência:    {self.carbon_price_brl_ton:>10.2f} BRL/tCO₂")
        print(f"  Receita potencial:           {self.receita_carbono_brl_ano:>10.2f} BRL/ano")

        print(f"\n{'Geração local':}")
        print(f"  Energia FV anual:            {self.energia_pv_kwh_ano:>10.1f} kWh/ano")
        print(f"  Energia importada:           {self.energia_grid_kwh_ano:>10.1f} kWh/ano")
        print(f"  Fração renovável:            {self.fracao_renovavel*100:>10.1f} %")
        print("=" * 65)

    def to_dict(self) -> Dict[str, float]:
        return {
            "emissoes_tco2_ano": self.emissoes_grid_import_kgco2_ano / 1000,
            "evitadas_rede_tco2_ano": self.emissoes_evitadas_vs_rede_kgco2_ano / 1000,
            "evitadas_combustivel_tco2_ano": self.emissoes_evitadas_vs_combustivel_kgco2_ano / 1000,
            "creditos_carbono_tco2_ano": self.creditos_carbono_tco2_ano,
            "receita_carbono_brl_ano": self.receita_carbono_brl_ano,
            "intensidade_gco2_kwh": self.intensidade_kgco2_kwh * 1000,
            "fracao_renovavel_pct": self.fracao_renovavel * 100,
        }


# ---------------------------------------------------------------------------
# Modelo de emissões
# ---------------------------------------------------------------------------

class EmissionsModel:
    """
    Modelo de contabilidade de emissões de CO₂ para o eletroposto.

    Parâmetros de referência
    -------------------------
    - Consumo médio VE elétrico: 0.20 kWh/km (carro elétrico compacto)
    - Consumo médio VE a gasolina (substituto): 10 km/L = 0.10 L/km
    - Fator de emissão gasolina (SEEG 2022): 2.212 kgCO₂/L
    - Equivalente gasolina: 2.212 * 0.10 = 0.221 kgCO₂/km = 221 gCO₂/km
    - Comparável: VE elétrico com rede média BR: 74 gCO₂/km

    Referência: SEEG (2023), INMETRO (2022), EPE (2022).
    """

    def __init__(
        self,
        factors: ONSEmissionFactors,
        carbon_price_brl_ton: float = 80.0,
        ev_efficiency_km_per_kwh: float = 5.0,
        gasoline_emission_kgco2_liter: float = 2.212,
        gasoline_consumption_liter_km: float = 0.10,
        operational_days: float = 365.0,
        delta_t: float = 1.0,
    ) -> None:
        self.factors = factors
        self.carbon_price_brl_ton = carbon_price_brl_ton
        self.ev_efficiency_km_per_kwh = ev_efficiency_km_per_kwh
        self.gasoline_emission_kgco2_liter = gasoline_emission_kgco2_liter
        self.gasoline_consumption_liter_km = gasoline_consumption_liter_km
        self.operational_days = operational_days
        self.delta_t = delta_t

        # Emissão de referência por km (gasolina)
        self.gasoline_kgco2_km = gasoline_emission_kgco2_liter * gasoline_consumption_liter_km

    def daily_grid_emissions(self, grid_import_profile: Dict[int, float]) -> float:
        """Emissões diárias da importação da rede [kgCO₂/dia] usando MEF horário."""
        return sum(
            grid_import_profile.get(t, 0.0) * self.factors.hourly_mef.get(t, 0.074) * self.delta_t
            for t in range(1, 25)
        )

    def daily_baseline_emissions(self, ev_load_profile: Dict[int, float]) -> float:
        """
        Emissões da linha de base (recarga via rede sem FV/BESS) [kgCO₂/dia].
        Usa o AEF médio horário para o perfil de carga VE.
        """
        return sum(
            ev_load_profile.get(t, 0.0) * self.factors.hourly_aef.get(t, 0.074) * self.delta_t
            for t in range(1, 25)
        )

    def daily_gasoline_emissions(self, ev_load_kwh_dia: float) -> float:
        """
        Emissões equivalentes da linha de base a gasolina [kgCO₂/dia].
        Converte kWh de recarga para km percorridos e depois para kgCO₂.
        """
        km_equivalentes = ev_load_kwh_dia * self.ev_efficiency_km_per_kwh
        return km_equivalentes * self.gasoline_kgco2_km

    def compute_annual_report(
        self,
        grid_import_profile: Dict[int, float],
        pv_generation_profile: Dict[int, float],
        ev_load_profile: Dict[int, float],
    ) -> EmissionsReport:
        """
        Calcula relatório anual de emissões.

        Args:
            grid_import_profile: P_grid_import[t] [kW] para t=1..24 (dia representativo).
            pv_generation_profile: P_pv_gen[t] [kW] para t=1..24.
            ev_load_profile: P_EV_load[t] [kW] para t=1..24.

        Returns:
            EmissionsReport com todas as métricas calculadas.
        """
        # Emissões diárias
        emissoes_grid_dia = self.daily_grid_emissions(grid_import_profile)
        baseline_dia = self.daily_baseline_emissions(ev_load_profile)
        ev_load_kwh_dia = sum(ev_load_profile.get(t, 0.0) * self.delta_t for t in range(1, 25))
        gasoline_baseline_dia = self.daily_gasoline_emissions(ev_load_kwh_dia)

        # Emissões anuais
        emissoes_grid_ano = emissoes_grid_dia * self.operational_days
        baseline_ano = baseline_dia * self.operational_days
        gasoline_baseline_ano = gasoline_baseline_dia * self.operational_days

        # Emissões evitadas
        evitadas_vs_rede = max(0.0, baseline_ano - emissoes_grid_ano)
        evitadas_vs_combustivel = max(0.0, gasoline_baseline_ano - emissoes_grid_ano)

        # Créditos de carbono (em tCO₂)
        creditos = evitadas_vs_rede / 1000  # kgCO₂ → tCO₂
        receita_carbono = creditos * self.carbon_price_brl_ton

        # Intensidade
        ev_kwh_ano = ev_load_kwh_dia * self.operational_days
        intensidade_kgco2_kwh = emissoes_grid_ano / max(ev_kwh_ano, 1.0)
        intensidade_gco2_km = intensidade_kgco2_kwh * 1000 / self.ev_efficiency_km_per_kwh

        # Geração local
        pv_kwh_dia = sum(pv_generation_profile.get(t, 0.0) * self.delta_t for t in range(1, 25))
        pv_kwh_ano = pv_kwh_dia * self.operational_days
        grid_kwh_dia = sum(grid_import_profile.get(t, 0.0) * self.delta_t for t in range(1, 25))
        grid_kwh_ano = grid_kwh_dia * self.operational_days
        total_supplied = pv_kwh_ano + grid_kwh_ano
        fracao_renovavel = pv_kwh_ano / max(total_supplied, 1.0)

        return EmissionsReport(
            emissoes_grid_import_kgco2_ano=emissoes_grid_ano,
            emissoes_ev_comb_referencia_kgco2_ano=gasoline_baseline_ano,
            emissoes_evitadas_vs_rede_kgco2_ano=evitadas_vs_rede,
            emissoes_evitadas_vs_combustivel_kgco2_ano=evitadas_vs_combustivel,
            creditos_carbono_tco2_ano=creditos,
            receita_carbono_brl_ano=receita_carbono,
            carbon_price_brl_ton=self.carbon_price_brl_ton,
            intensidade_kgco2_kwh=intensidade_kgco2_kwh,
            intensidade_gco2_km=intensidade_gco2_km,
            energia_pv_kwh_ano=pv_kwh_ano,
            energia_grid_kwh_ano=grid_kwh_ano,
            fracao_renovavel=fracao_renovavel,
        )


# ---------------------------------------------------------------------------
# Extensão do modelo Pyomo com restrição de emissões
# ---------------------------------------------------------------------------

def add_emissions_constraint_to_model(
    model: AbstractModel,
    hourly_mef: Dict[int, float],
    max_daily_emissions_kgco2: float,
    carbon_price_brl_ton: float = 0.0,
) -> AbstractModel:
    """
    Adiciona restrição de emissões e componente de receita de carbono a um
    modelo Pyomo existente.

    Restrição de emissões (opcional):
        Σ_t P_grid_import[t] * MEF[t] * delta_t ≤ max_daily_emissions

    Receita de créditos de carbono (na função objetivo):
        Δf = carbon_price * (baseline_emissions - actual_emissions) / 1000
    Nota: para incluir na função objetivo, o modelo deve ser reconstruído.
    Esta função apenas adiciona a restrição de teto de emissões.

    Args:
        model: AbstractModel Pyomo existente (já construído).
        hourly_mef: fator de emissão marginal horário [kgCO₂/kWh].
        max_daily_emissions_kgco2: teto de emissões diárias [kgCO₂/dia].
        carbon_price_brl_ton: preço do carbono [BRL/tCO₂] (para cálculo de receita).

    Returns:
        Model com restrição de emissões adicionada (modifica in-place e retorna).
    """
    # Parâmetros de emissão
    model.hourly_mef = Param(model.T, initialize=hourly_mef, within=NonNegativeReals)
    model.max_daily_emissions = Param(initialize=max_daily_emissions_kgco2, within=NonNegativeReals)
    model.carbon_price = Param(initialize=carbon_price_brl_ton / 1000, within=NonNegativeReals)  # BRL/kgCO₂

    # Variável de emissões diárias
    model.daily_emissions = Var(within=NonNegativeReals)

    # Definição das emissões diárias
    def emissions_def(m):
        return m.daily_emissions == sum(
            m.P_grid_import[t] * m.hourly_mef[t]
            for t in m.T
        )
    model.EmissionsDefinition = Constraint(rule=emissions_def)

    # Restrição de teto de emissões
    def emissions_limit(m):
        return m.daily_emissions <= m.max_daily_emissions
    model.EmissionsLimit = Constraint(rule=emissions_limit)

    return model


# ---------------------------------------------------------------------------
# Demonstração
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Feature 9 — Emissões de CO₂ e Intensidade de Carbono")
    print("=" * 60)

    # Perfis de operação (exemplo)
    grid_import = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 45, 7: 60, 8: 50,
        9: 40, 10: 30, 11: 25, 12: 30, 13: 35, 14: 40, 15: 50,
        16: 55, 17: 80, 18: 100, 19: 95, 20: 85, 21: 70,
        22: 60, 23: 50, 24: 40,
    }
    pv_gen = {
        1: 0, 2: 0, 3: 0, 4: 0, 5: 5, 6: 15, 7: 30, 8: 50,
        9: 70, 10: 90, 11: 95, 12: 85, 13: 75, 14: 65, 15: 55,
        16: 40, 17: 25, 18: 10, 19: 0, 20: 0, 21: 0,
        22: 0, 23: 0, 24: 0,
    }
    ev_load = {
        1: 35, 2: 28, 3: 22, 4: 20, 5: 25, 6: 48, 7: 72, 8: 98,
        9: 105, 10: 115, 11: 110, 12: 100, 13: 95, 14: 90, 15: 98,
        16: 112, 17: 126, 18: 135, 19: 128, 20: 116, 21: 94,
        22: 72, 23: 54, 24: 42,
    }

    print("\nComparativo de regiões:")
    for nome, factory in [
        ("Brasil Nacional", ONSEmissionFactors.brazil_national_2023),
        ("Sudeste", ONSEmissionFactors.brazil_sudeste_2023),
        ("Nordeste", ONSEmissionFactors.brazil_nordeste_2023),
    ]:
        factors = factory()
        emissoes_model = EmissionsModel(
            factors,
            carbon_price_brl_ton=80.0,
            operational_days=365.0,
        )
        report = emissoes_model.compute_annual_report(grid_import, pv_gen, ev_load)
        print(f"\n  [{nome}] AEF médio = {factors.annual_aef*1000:.1f} gCO₂/kWh")
        print(f"    Emissões/ano:    {report.emissoes_grid_import_kgco2_ano/1000:.1f} tCO₂/ano")
        print(f"    Evitadas (rede): {report.emissoes_evitadas_vs_rede_kgco2_ano/1000:.1f} tCO₂/ano")
        print(f"    Créditos:        {report.creditos_carbono_tco2_ano:.1f} tCO₂/ano")
        print(f"    Receita carbono: {report.receita_carbono_brl_ano:.0f} BRL/ano")
        print(f"    Fração renovável:{report.fracao_renovavel*100:.1f}%")

    print("\nRelatório detalhado — Brasil Nacional:")
    factors_br = ONSEmissionFactors.brazil_national_2023()
    model = EmissionsModel(factors_br, carbon_price_brl_ton=80.0)
    report = model.compute_annual_report(grid_import, pv_gen, ev_load)
    report.print_summary()
