from pathlib import Path

# Lê e imprime o relatório gerado
report_path = Path("/tmp/relatorio_analise_investimento.txt")

if report_path.exists():
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # Imprime primeiras 3000 caracteres para visualização
        print(content[:3500])
        print("\n[...]\n")
        # Imprime as últimas linhas com recomendações
        lines = content.split('\n')
        print('\n'.join(lines[-60:]))
else:
    print("Relatório não encontrado")
