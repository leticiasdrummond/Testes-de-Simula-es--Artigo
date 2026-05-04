# Registro Formal dos Dados Levantados

## Objetivo
Consolidar em um unico ponto os dados levantados e utilizados na pesquisa,
garantindo rastreabilidade, integracao entre arquivos e passos reproduziveis.

## Padrao de registro
Cada item deve registrar:
- **Arquivo** (caminho no repositorio).
- **Tipo**: primario (empirico), derivado (transformado) ou saida gerada.
- **Origem/Periodo**: fonte do dado, janela observacional ou escopo.
- **Geracao/Reproducao**: script ou procedimento para regenerar o arquivo.
- **Documentacao**: referencia cruzada com docs tecnicos.

## Inventario integrado (dados levantados e entradas consolidadas)
| ID | Arquivo | Tipo | Origem/Periodo | Geracao/Reproducao | Documentacao |
|---|---|---|---|---|---|
| DUTRA-EMPIRICO | `recorte_empirico_dutra.json` | Primario (empirico consolidado) | Levantamento de operacao do corredor Dutra (2025-01 a 2026-02) | `python analise_secao_3_2_rodovia.py` (gera JSON e recalcula indicadores) | `hipoteses_metodologia_calibracao_dutra.md` |
| DUTRA-RECORTE-ABSTRACT | `entrada_recorte_empirico_dutra_abstract.dat` | Derivado (entrada para modelo abstrato) | Recorte empirico Dutra + calibracao do estudo | `python analise_secao_3_2_rodovia.py` | `hipoteses_metodologia_calibracao_dutra.md` |
| DUTRA-INPUT | `dados_dutra_abstract_completo.dat` | Entrada consolidada | Parametrizacao completa do caso Dutra (fontes setoriais + recorte empirico) | Curadoria manual versionada | `referencias_parametros_dutra.md` |
| BRASIL-CENARIOS | `dados_cenarios_brasil.dat` | Entrada calibrada | Calibracao Brasil para cenarios de referencia | Curadoria manual versionada | `CALIBRAÇÃO BRASIL/validacao_metodologia_mercado_brasil.md` |
| EXEMPLO-BASE | `dados_exemplo.dat` | Entrada exemplo | Conjunto didatico para testes do modelo principal | Curadoria manual versionada | `docs/dados_exemplo.md` |
| EXEMPLO-LEGADO | `data.dat` | Entrada legado | Dataset base do `main2.py` | Curadoria manual versionada | `docs/dados_exemplo.md` (estrutura similar) |

## Artefatos gerados (reproduziveis)
| Arquivo | Script | Observacao |
|---|---|---|
| `relatorio_saida.txt` | `python main.py` | Saida principal do modelo Pyomo com `dados_exemplo.dat`. |
| `relatorio1.txt` | `python main2.py` | Saida do modelo alternativo. |
| `resultado_eletroposto_ve.csv`, `relatorio_eletroposto_ve.txt` | `python simulacao_eletroposto_ve.py` | Perfis estocasticos de demanda VE. |
| `resultado_secao_3_2_rodovia.csv`, `relatorio_secao_3_2_rodovia.txt` | `python analise_secao_3_2_rodovia.py` | Analise de cenarios para corredor rodoviario. |
| `saida_fronteira_viabilidade/` | `python analise_fronteira_viabilidade.py` | Mapa de viabilidade economica. |

## Regras de atualizacao
- Qualquer novo dado levantado deve ser adicionado a esta tabela com fonte e janela.
- Alteracoes em recortes empiricos precisam atualizar o JSON correspondente e a
  documentacao de hipoteses associada.
- Resultados gerados devem manter o script de reproducao documentado.
