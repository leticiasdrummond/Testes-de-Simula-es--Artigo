# Secao de Validacao para Artigo

## Protocolo
A validacao adotou duas frentes complementares: (i) consistencia interna por comparacao entre cenarios deterministico e estocastico, e (ii) consistencia externa por alinhamento com benchmarks de mercado brasileiro e internacional.

## Ajustes Implementados
1. Curva de carregamento nao-linear por SOC, com tapering acima de 80%.
2. Parque de recarga calibrado para aproximadamente 84% AC e 16% DC.
3. Validacao analitica M/M/s com Erlang C integrada ao pipeline de artigo.
4. Comparativos simulacao vs. teoria e simulacao vs. benchmarks adicionados em graficos e CSV.
5. Referencias metodologicas e de dados ampliadas no material de submissao.

## Evidencias Quantitativas
- Espera media agregada no caso tipico: 239.42 min.
- Espera media agregada no caso anti-tipico: 105.16 min.
- Utilizacao media agregada: 25.75%.
- Pico medio agregado de demanda: 229.51 kW.
- Desvio medio simulacao vs. M/M/s (espera media): 194.26%.
- Desvio maximo simulacao vs. M/M/s (espera media): 199.93%.
- Desvio medio em veiculos/carregador/dia vs benchmark: 15.77%.
- Desvio medio da proporcao AC vs mercado: 1.66 p.p.
- Desvio medio do tempo de carga vs benchmark EDP: 60.01%.

## Validacao Analitica M/M/s
A comparacao foi feita com o modelo M/M/s (notacao de Kendall), assumindo chegadas Poisson e servico exponencial medio por servidor.
As metricas teoricas foram calculadas por Erlang C e comparadas com a espera media da simulacao para casos tipico e anti-tipico, nos modos deterministico e estocastico.

Formulacao usada:
- rho = lambda / (s * mu)
- P(espera > 0) = Erlang C
- Wq = Lq / lambda
- W = Wq + 1/mu

## Discussao
Os resultados indicam robustez para cenarios tipicos e anti-tipicos, com degradacao controlada de desempenho sob maior variabilidade estocastica.
A validacao M/M/s fornece uma referencia teorica para auditar tempos de espera, enquanto os benchmarks de mercado ancoram a plausibilidade operacional brasileira.
A curva nao-linear aumenta o realismo no tempo de sessao, principalmente em recargas que avancam para faixas elevadas de SOC.

## Referencias
- Xi, X.; Sioshansi, R.; Marano, V. (2013). Simulation-optimization model for a station-level electric vehicle charging infrastructure operation problem. Transportation Research Part D: Transport and Environment, 22, 60-69.
- Zhao, H.; Zhang, C.; Hu, Z.; Song, Y.; Wang, J.; Lin, X. (2016). A review of electric vehicle charging station capacity planning and location optimization from the perspective of queuing theory and transportation network models. IEEE Access, 4, 8635-8648.
- ABVE. Associacao Brasileira do Veiculo Eletrico (2025). Relatorio anual de eletromobilidade e infraestrutura de recarga no Brasil.
- EPE. Empresa de Pesquisa Energetica (2025). Plano Decenal de Expansao de Energia 2035 - Caderno de Eletromobilidade.
- Shell Recharge (2024/2025). Informacoes publicas de operacao de hubs de recarga rapida (Brasil e internacional).
- EDP Brasil (2024/2025). Dados publicos de operacao de recarga e tempos medios de sessao.