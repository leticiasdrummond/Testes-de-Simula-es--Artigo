# Registro Formal dos Dados Levantados

## Objetivo
Consolidar em um único ponto os dados levantados e utilizados na pesquisa,
garantindo rastreabilidade, integração entre arquivos e passos reproduzíveis.

## Padrão de registro
Cada item deve registrar:
- **Arquivo** (caminho no repositório).
- **Tipo**: primário (empírico), derivado (transformado) ou saída gerada.
- **Origem/Período**: fonte do dado, janela observacional ou escopo.
- **Geração/Reprodução**: script ou procedimento para regenerar o arquivo.
- **Documentação**: referência cruzada com docs técnicos.

## Inventário integrado (dados levantados e entradas consolidadas)
| ID | Arquivo | Tipo | Origem/Período | Geração/Reprodução | Documentação |
|---|---|---|---|---|---|
| DUTRA-EMPIRICO | `recorte_empirico_dutra.json` | Primário (empírico consolidado) | Levantamento de operação do corredor Dutra (2025-01 a 2026-02) | `python analise_secao_3_2_rodovia.py` (gera JSON e recalcula indicadores) | `hipoteses_metodologia_calibracao_dutra.md` |
| DUTRA-RECORTE-ABSTRACT | `entrada_recorte_empirico_dutra_abstract.dat` | Derivado (entrada para modelo abstrato) | Recorte empírico Dutra + calibração do estudo | `python analise_secao_3_2_rodovia.py` | `hipoteses_metodologia_calibracao_dutra.md` |
| DUTRA-INPUT | `dados_dutra_abstract_completo.dat` | Entrada consolidada | Parametrização completa do caso Dutra (fontes setoriais + recorte empírico) | Curadoria manual versionada | `referencias_parametros_dutra.md` |
| BRASIL-CENARIOS | `dados_cenarios_brasil.dat` | Entrada calibrada | Calibração Brasil para cenários de referência | Curadoria manual versionada | `CALIBRAÇÃO BRASIL/validacao_metodologia_mercado_brasil.md` |
| EXEMPLO-BASE | `dados_exemplo.dat` | Entrada exemplo | Conjunto didático para testes do modelo principal | Curadoria manual versionada | `docs/dados_exemplo.md` |
| EXEMPLO-LEGADO | `data.dat` | Entrada legado | Dataset base do `main2.py` | Curadoria manual versionada | `docs/dados_exemplo.md` (estrutura similar) |

## Artefatos gerados (reproduzíveis)
| Arquivo | Script | Observação |
|---|---|---|
| `relatorio_saida.txt` | `python main.py` | Saída principal do modelo Pyomo com `dados_exemplo.dat`. |
| `relatorio1.txt` | `python main2.py` | Saída do modelo alternativo. |
| `resultado_eletroposto_ve.csv`, `relatorio_eletroposto_ve.txt` | `python simulacao_eletroposto_ve.py` | Perfis estocásticos de demanda VE. |
| `resultado_secao_3_2_rodovia.csv`, `relatorio_secao_3_2_rodovia.txt` | `python analise_secao_3_2_rodovia.py` | Análise de cenários para corredor rodoviário. |
| `saida_fronteira_viabilidade/` | `python analise_fronteira_viabilidade.py` | Mapa de viabilidade econômica. |

## Regras de atualização
- Qualquer novo dado levantado deve ser adicionado a esta tabela com fonte e janela.
- Alterações em recortes empíricos precisam atualizar o JSON correspondente e a
  documentação de hipóteses associada.
- Resultados gerados devem manter o script de reprodução documentado.
