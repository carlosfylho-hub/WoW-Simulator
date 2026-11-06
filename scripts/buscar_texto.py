"""Search a saved text or JS file and print short matching excerpts.

Minified bundles are split on semicolons and newlines so a match does not
print a single megabyte line. It does not fetch anything.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("padrao", help="Expressão regular, sem diferenciar maiúsculas.")
    parser.add_argument("--limite", type=int, default=40)
    parser.add_argument("--tamanho", type=int, default=400)
    args = parser.parse_args()

    texto = args.arquivo.read_text(encoding="utf-8", errors="replace")
    regex = re.compile(args.padrao, re.IGNORECASE)

    vistos: set[str] = set()
    total = 0
    for trecho in re.split(r"[;\n]", texto):
        trecho = trecho.strip()
        if not trecho or not regex.search(trecho):
            continue
        recorte = trecho[: args.tamanho]
        if recorte in vistos:
            continue
        vistos.add(recorte)
        print(recorte)
        print("-" * 60)
        total += 1
        if total >= args.limite:
            break

    print(f"Ocorrências exibidas: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
