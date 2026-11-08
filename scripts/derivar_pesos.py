"""Derive measured secondary weights from an addon export and cache them.

Usage:
    python scripts/derivar_pesos.py fixtures/pyrogalth.simc [--simc caminho] [--iterations 200]

Requires the simc binary. Without it the command exits non-zero with a clear
message; the pruner then keeps using the curated ``dados/pesos_secundarios.json``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wowsim.data import pesos_medidos
from wowsim.parser.addon import parse_texto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path, help="Export do addon (.simc).")
    parser.add_argument("--simc", default=None, help="Caminho do binário simc.")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--fight-style", default="Patchwerk")
    args = parser.parse_args(argv)

    personagem = parse_texto(args.arquivo.read_text(encoding="utf-8"))
    pesos = pesos_medidos.derivar_pesos_medidos(
        personagem,
        simc_path=args.simc,
        iterations=args.iterations,
        fight_style=args.fight_style,
    )
    if pesos is None:
        print(
            "Não foi possível derivar pesos medidos (binário ausente ou sem "
            "scale_factors). O pruner seguirá com os pesos curados.",
            file=sys.stderr,
        )
        return 2
    print(f"Pesos medidos ({pesos.fonte}) para {pesos.classe}/{pesos.spec}:")
    for chave, valor in sorted(pesos.valores.items(), key=lambda kv: -kv[1]):
        print(f"  {chave}: {valor:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
