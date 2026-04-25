"""
Exemplo de saída do relatório de análise de investimento.
Este script mostra um exemplo típico dos resultados gerados.
"""

print("""
====================================================================================================
ANÁLISE COMPARATIVA DE INVESTIMENTO EM MICRORREDE PV-BESS
Objetivo: Induzir Decisão de Investimento Otimizado
====================================================================================================

====================================================================================================
1. CAPACIDADES OTIMIZADAS POR CENÁRIO
====================================================================================================
Cenário                      PV (kW)   BESS (kWh)   Trafo (kW)    CAPEX (BRL)
----------------------------------------------------------------------------------------------------
Base                           82.91        82.11        56.28         529,866
CAPEX_70%                     100.35       110.61        67.43         524,550
CAPEX_85%                      89.73        93.80        60.65         527,172
CAPEX_114%                     77.05        72.33        52.80         532,151
Horizonte_180dias              80.19        73.87        54.55         431,625
Horizonte_730dias              84.46        86.81        57.30         584,448
TarifaVE_90%                   82.91        82.11        56.28         529,866
TarifaVE_110%                  82.91        82.11        56.28         529,866
TarifaVE_120%                  82.91        82.11        56.28         529,866

====================================================================================================
2. INDICADORES DE LUCRATIVIDADE
====================================================================================================
Cenário                    Lucro Anual   ROI (%) Payback (anos)     VPL (BRL)
----------------------------------------------------------------------------------------------------
Base                           108,209      20.4            4.90         135,197
CAPEX_70%                      173,095      33.0            3.03         380,914
CAPEX_85%                      137,747      26.1            3.83         251,630
CAPEX_114%                      82,806      15.6            6.42          42,412
Horizonte_180dias               53,180      12.3            8.12         -72,013
Horizonte_730dias              216,418      37.0            2.70         668,942
TarifaVE_90%                    65,539      12.4            8.08         -68,485
TarifaVE_110%                  150,879      28.5            3.51         297,879
TarifaVE_120%                  193,549      36.5            2.74         491,561

====================================================================================================
3. INDICADORES DE MERCADO
====================================================================================================
Cenário                    Exp. Rede (%)  Autossuf. (%) Compet. Tarif.(%)  Dif. Tarif.(BRL/kWh)
----------------------------------------------------------------------------------------------------
Base                                50.9           49.1              31.8                  0.203
CAPEX_70%                           42.0           58.0              31.8                  0.203
CAPEX_85%                           47.2           52.8              31.8                  0.203
CAPEX_114%                          54.1           45.9              31.8                  0.203
Horizonte_180dias                   51.9           48.1              31.8                  0.203
Horizonte_730dias                   50.2           49.8              31.8                  0.203
TarifaVE_90%                        50.9           49.1              17.7                  0.113
TarifaVE_110%                       50.9           49.1              46.0                  0.293
TarifaVE_120%                       50.9           49.1              60.1                  0.383

====================================================================================================
4. INDICADORES OPERACIONAIS
====================================================================================================
Cenário                      FC PV (%)  Util. Trafo(%)  Ciclos BESS/dia   Perdas BESS(%)
----------------------------------------------------------------------------------------------------
Base                              30.7            92.2             0.62            10.5
CAPEX_70%                         25.4            89.1             0.55            10.5
CAPEX_85%                         28.5            91.0             0.59            10.5
CAPEX_114%                        33.1            93.2             0.65            10.5
Horizonte_180dias                 31.8            92.8             0.64            10.5
Horizonte_730dias                 30.2            91.8             0.61            10.5
TarifaVE_90%                      30.7            92.2             0.62            10.5
TarifaVE_110%                     30.7            92.2             0.62            10.5
TarifaVE_120%                     30.7            92.2             0.62            10.5

====================================================================================================
5. ANÁLISE DE SENSIBILIDADE E RECOMENDAÇÕES
====================================================================================================

5.1 Cenários Ordenados por ROI (Retorno sobre Investimento):
----------------------------------------------------------------------------------------------------
  1. Horizonte_730dias     ROI:   37.0%  Payback:  2.70 anos
  2. TarifaVE_120%         ROI:   36.5%  Payback:  2.74 anos
  3. CAPEX_70%             ROI:   33.0%  Payback:  3.03 anos
  4. TarifaVE_110%         ROI:   28.5%  Payback:  3.51 anos
  5. CAPEX_85%             ROI:   26.1%  Payback:  3.83 anos

5.2 Cenários com Menor Payback:
----------------------------------------------------------------------------------------------------
  1. Horizonte_730dias     Payback:  2.70 anos  ROI:   37.0%
  2. TarifaVE_120%         Payback:  2.74 anos  ROI:   36.5%
  3. CAPEX_70%             Payback:  3.03 anos  ROI:   33.0%
  4. TarifaVE_110%         Payback:  3.51 anos  ROI:   28.5%
  5. CAPEX_85%             Payback:  3.83 anos  ROI:   26.1%

5.3 Cenários com Maior Valor Presente Líquido (VPL):
----------------------------------------------------------------------------------------------------
  1. Horizonte_730dias     VPL:      668,942 BRL
  2. TarifaVE_120%         VPL:      491,561 BRL
  3. CAPEX_70%             VPL:      380,914 BRL
  4. TarifaVE_110%         VPL:      297,879 BRL
  5. CAPEX_85%             VPL:      251,630 BRL

5.4 Impacto da Redução de CAPEX:
----------------------------------------------------------------------------------------------------
  CAPEX 70%: ROI = 33.0% (Δ+12.6%), Payback = 3.03 anos (Δ-1.87)
  CAPEX 85%: ROI = 26.1% (Δ+5.8%), Payback = 3.83 anos (Δ-1.07)
  CAPEX 114%: ROI = 15.6% (Δ-4.8%), Payback = 6.42 anos (Δ+1.52)

5.5 Impacto do Horizonte de Avaliação:
----------------------------------------------------------------------------------------------------
  180 dias: ROI = 12.3% (Δ-8.1%), Lucro Anual = 53,180 BRL
  730 dias: ROI = 37.0% (Δ+16.6%), Lucro Anual = 216,418 BRL

5.6 Impacto do Diferencial Tarifário (Tarifa VE):
----------------------------------------------------------------------------------------------------
  Tarifa 90%: ROI = 12.4% (Δ-8.1%), Competitividade = 17.7%
  Tarifa 110%: ROI = 28.5% (Δ+8.1%), Competitividade = 46.0%
  Tarifa 120%: ROI = 36.5% (Δ+16.1%), Competitividade = 60.1%

====================================================================================================
6. RECOMENDAÇÕES PARA OTIMIZAÇÃO DO INVESTIMENTO
====================================================================================================

A. CENÁRIO RECOMENDADO (Melhor ROI): Horizonte_730dias
   - ROI: 37.0%
   - Payback: 2.70 anos
   - VPL: 668,942 BRL
   - Capacidades: PV=84.5 kW, BESS=86.8 kWh

B. ESTRATÉGIAS PARA MAXIMIZAR RETORNO:
   1. REDUÇÃO DE CAPEX:
      - Reduzir CAPEX em 30% aumenta ROI em 12.6 pontos percentuais
      - Buscar fornecedores competitivos, compras em volume, incentivos fiscais

   2. OTIMIZAÇÃO TARIFÁRIA:
      - Aumentar tarifa VE em 20% aumenta ROI em 16.1 pontos percentuais
      - Análise de competitividade de mercado é fundamental

   3. HORIZONTE DE AVALIAÇÃO:
      - Horizonte mais longo permite amortizar melhor o CAPEX
      - Considerar vida útil dos equipamentos (PV: 25 anos, BESS: 10-15 anos)

   4. AUTOSSUFICIÊNCIA ENERGÉTICA:
      - Autossuficiência atual: 49.1%
      - Exposição à rede: 50.9%
      - Maior investimento em PV/BESS reduz exposição à volatilidade de preços

====================================================================================================
FIM DO RELATÓRIO
====================================================================================================
""")
