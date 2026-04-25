# Referencias para parametrizacao do caso Dutra

Este documento registra fontes usadas para montar o arquivo de entrada [dados_dutra_abstract_completo.dat](dados_dutra_abstract_completo.dat), com foco em transparencia metodologica para pesquisa colaborativa.

## 1) Tarifas de energia (grid_price)
- ANEEL. Banco de tarifas homologadas e estrutura tarifaria com sinal de ponta/intermediario/fora de ponta para consumidores de media tensao.
- MME/ANEEL. Documentos sobre Tarifa Branca e sinal horario de custo de energia.

Uso no modelo:
- Curvas de preco por hora foram definidas com estrutura TOU agressiva para analise de eletroposto, mantendo ordem economica: ponta > intermediario > fora de ponta.

## 2) Recurso solar e perfil horario (irradiance_cf)
- CRESESB (Atlas Solarimetrico e plataforma de recurso solar para o Brasil).
- INPE/CPTEC e literatura de geracao FV no Sudeste.
- ONS/EPE: estatisticas agregadas de geracao renovavel e referencia de sazonalidade.

Uso no modelo:
- Fator de capacidade horario em curva tipo sino, com pico no periodo de maior irradiancia e valores nulos noturnos.

## 3) CAPEX PV e BESS
- IRENA. Renewable Power Generation Costs (edicoes recentes).
- NREL. Annual Technology Baseline e relatorios de custos de armazenamento.
- EPE. Estudos de custos e expansao para sistemas eletricos no Brasil.

Uso no modelo:
- capex_pv_kw, capex_bess_kwh em valores representativos para estudos de pre-viabilidade 2025-2026 em contexto brasileiro.

## 4) Parametros tecnicos do BESS
- IEC/IEEE e literatura tecnica de operacao de baterias Li-ion.
- Revisoes academicas sobre eficiencia round-trip, SOC operacional e degradacao por throughput.

Uso no modelo:
- eta_charge, eta_discharge, limites de SOC e taxa C conservadora para robustez operacional.

## 5) Custo de transformador e interface de rede
- Referencias de mercado nacional de subestacoes compactas e transformadores de distribuicao.
- Guias tecnicos de concessionarias para conexao em media tensao.

Uso no modelo:
- capex_trafo_kw e P_trafo_cap_max calibrados para ordem de grandeza de eletroposto rodoviario.

## 6) Recorte empirico Dutra
- Consolidado no arquivo [recorte_empirico_dutra.json](recorte_empirico_dutra.json).
- Hipoteses e metodologia em [hipoteses_metodologia_calibracao_dutra.md](hipoteses_metodologia_calibracao_dutra.md).

Uso no modelo:
- Cenarios SC, prob_sc e P_EV_load na entrada [dados_dutra_abstract_completo.dat](dados_dutra_abstract_completo.dat).

## Nota de validade
Os valores adotados sao rastreaveis e coerentes com literatura e bases institucionais, mas devem ser atualizados para a concessionaria e estrutura tarifaria especifica do ponto de conexao estudado (data-base e modalidade contratual).