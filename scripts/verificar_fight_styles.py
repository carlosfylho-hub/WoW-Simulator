"""Verifica quais fight_style o binário local do SimC aceita.

Uso: python scripts/verificar_fight_styles.py
Não faz parte da suíte; script de diagnóstico manual.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wowsim.parser.addon import parse_texto  # noqa: E402
from wowsim.topgear.runner import criar_simulador  # noqa: E402
from wowsim.topgear.search import conjunto_do_personagem  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pyrogalth.simc"

ESTILOS = [
    "Patchwerk",
    "DungeonSlice",
    "DungeonSliceRace",
    "TargetDummy",
    "ExecutePatchwerk",
    "HecticAddCleave",
    "LightMovement",
    "HeavyMovement",
    "CastingPatchwerk",
    "CleaveAdd",
    "HelterSkelter",
]


def main() -> None:
    texto = FIXTURE.read_text(encoding="utf-8")
    personagem = parse_texto(texto)
    base = conjunto_do_personagem(personagem)
    for estilo in ESTILOS:
        try:
            simulador = criar_simulador(personagem, fight_style=estilo, threads=1)
            leitura = simulador({"base": base}, 5)
            print(f"OK    {estilo:22s} dps={round(leitura.base_dps or 0)}")
        except Exception as exc:  # noqa: BLE001 - diagnóstico
            print(f"ERRO  {estilo:22s} {str(exc).splitlines()[-1][:120]}")


if __name__ == "__main__":
    main()
