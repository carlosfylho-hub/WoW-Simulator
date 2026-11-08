"""Benchmark: estima quantas iterações (lutas simuladas) por segundo a CPU local faz.

Uso: python scripts/benchmark_simc.py
Não faz parte da suíte; script de medição manual.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wowsim.parser.addon import parse_texto  # noqa: E402
from wowsim.topgear.runner import criar_simulador  # noqa: E402
from wowsim.topgear.search import conjunto_do_personagem  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pyrogalth.simc"


def main() -> None:
    texto = FIXTURE.read_text(encoding="utf-8")
    personagem = parse_texto(texto)
    base = conjunto_do_personagem(personagem)
    nucleos = os.cpu_count() or 2
    threads = max(1, nucleos - 1)
    print(f"CPU: {nucleos} nucleos logicos | threads usadas: {threads}\n")

    plano = [("Patchwerk", 2000), ("DungeonSlice", 1500)]
    for estilo, iteracoes in plano:
        simulador = criar_simulador(personagem, fight_style=estilo, threads=threads)
        inicio = time.monotonic()
        leitura = simulador({"base": base}, iteracoes)
        duracao = time.monotonic() - inicio
        ips = iteracoes / duracao
        dps = round(leitura.base_dps or 0)
        print(f"[{estilo}] {iteracoes} iteracoes em {duracao:.2f}s -> {ips:,.0f} iter/s (dps~{dps:,})")
        print(f"    1 minuto  ~ {ips * 60:,.0f} iteracoes")
        print(f"    1 hora    ~ {ips * 3600:,.0f} iteracoes")
        print(f"    1 milhao  ~ {1_000_000 / ips:.0f} s ({1_000_000 / ips / 60:.1f} min)\n")


if __name__ == "__main__":
    main()
