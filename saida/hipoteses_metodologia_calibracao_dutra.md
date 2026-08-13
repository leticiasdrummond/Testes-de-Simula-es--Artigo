# Metodologia de Calibracao Fina - Corredor Dutra

## Objetivo
Calibrar demanda e variabilidade do corredor Dutra para uso na analise da Secao 3.2 e para alimentacao de cenarios no modelo AbstractModel.

## Recorte Empirico Registrado
- Fonte: levantamento de operacao do corredor Dutra (eletropostos comparaveis)
- Janela de observacao: 2025-01 a 2026-02
- Dias observados: 182
- Chegadas medias diarias: 246.0
- Desvio padrao diario: 58.0
- p90 de chegadas: 312.0
- Energia media por sessao: 31.80 kWh
- Participacao noturna (22h-6h): 24.0%

## Hipoteses de Modelagem
- H1: O padrao horario da Dutra e representado por perfil normalizado de 24 horas com pico principal no fim da tarde/noite.
- H2: A variabilidade estocastica de chegadas segue aproximacao por perturbacao proporcional ao coeficiente de variacao empirico.
- H3: A energia demandada por sessao em rodovia e maior que no urbano por menor SOC de chegada apos percursos longos.
- H4: O crescimento de demanda por ano segue fatores observacionais consolidados no recorte (2026/2030/2035).
- H5: A calibracao e reprodutivel: todos os parametros do recorte sao versionados neste repositorio.

## Parametros Derivados
- Coeficiente de variacao (CV): 0.2358
- Perturbacao estocastica calibrada: 0.2593
- Ajuste energetico de viagem longa (kWh): 4.770
- Arrivals por ano: {2026: 246, 2030: 310, 2035: 381}

## Reuso no Modelo Abstract
O arquivo entrada_recorte_empirico_dutra_abstract.dat gerado por este script deve ser usado como entrada de cenarios (SC, prob_sc e P_EV_load) no modelo abstrato, em conjunto com os demais parametros tecnicos/economicos.