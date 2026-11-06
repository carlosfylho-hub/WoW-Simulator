"""Phase 5 acceptance: rings and trinkets at the fixture.

Generates only ring enchant alternatives and trinket candidates, runs simc and
writes the PT-BR report. Prints the deltas so the manual criterion can be
checked without opening the files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wowsim import simc_runner as sr  # noqa: E402
from wowsim.gen import profilesets  # noqa: E402
from wowsim.parser.addon import parse_arquivo  # noqa: E402
from wowsim.report import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=500)
    args = parser.parse_args()

    personagem = parse_arquivo(PROJECT_ROOT / "fixtures" / "pyrogalth.simc")
    aneis = [
        variacao
        for variacao in profilesets.encantamentos(personagem)
        if variacao.nome.startswith("ench_rings_")
    ]
    trinkets = profilesets.berloques(personagem, nivel=341)
    variacoes = [profilesets.gerar(personagem, categorias=set())[0], *aneis, *trinkets]

    pasta = PROJECT_ROOT / "saida" / "aceite-fase5"
    destino = profilesets.escrever_arquivo(personagem, variacoes, pasta / "lote.simc")
    execucao = sr.run_simc(
        destino,
        iterations=args.iterations,
        fight_style="DungeonSlice",
        threads=sr.threads_padrao(),
    )
    resultado = sr.read_results(execucao.json_path)
    if resultado.base is None:
        print("Base ausente no JSON.")
        return 1

    base = resultado.base.dps
    nomes = {variacao.nome: variacao for variacao in variacoes}
    print(f"Base: {base:,.0f} DPS")
    print(f"Variações no JSON: {len(resultado.variacoes)} de {len(variacoes) - 1}")

    print("\nAnéis:")
    for entrada in resultado.variacoes:
        if entrada.nome.startswith("ench_rings_"):
            print(f"  {entrada.nome}: {100 * (entrada.dps - base) / base:+.2f}%")

    print("\nBerloques:")
    for entrada in resultado.variacoes:
        if entrada.nome.startswith("trinket"):
            variacao = nomes.get(entrada.nome)
            aviso = " [R4]" if variacao and variacao.aviso else ""
            print(f"  {entrada.nome}: {100 * (entrada.dps - base) / base:+.2f}%{aviso}")

    md, html = render(
        personagem,
        resultado,
        variacoes,
        destino=pasta,
        iterations=args.iterations,
        fight_style="DungeonSlice",
    )
    print(f"\nRelatório: {md}")
    print(f"HTML: {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
