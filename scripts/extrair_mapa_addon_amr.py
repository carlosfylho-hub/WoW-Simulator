"""Extrai os enums autoritativos do addon AskMrRobot para ``dados/amr_mapa.json``.

O addon é a fonte que **gera** o export: ``ClassIds``, ``RaceIds``, ``FactionIds``,
``SlotIds`` e ``SpecIds`` (spec Blizzard → índice AMR). A versão vem do ``.toc``,
que casa com o ``$<versao>`` da string.

Uso:
    python scripts/extrair_mapa_addon_amr.py
    python scripts/extrair_mapa_addon_amr.py --addon-dir "C:/.../AddOns/AskMrRobot"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim.paths import DADOS_DIR  # noqa: E402

PADRAO = Path(
    r"C:\Program Files (x86)\World of Warcraft\_retail_\Interface\AddOns\AskMrRobot"
)
DESTINO = DADOS_DIR / "amr_mapa.json"

CLASSES = {
    "DeathKnight": "deathknight",
    "DemonHunter": "demonhunter",
    "Druid": "druid",
    "Evoker": "evoker",
    "Hunter": "hunter",
    "Mage": "mage",
    "Monk": "monk",
    "Paladin": "paladin",
    "Priest": "priest",
    "Rogue": "rogue",
    "Shaman": "shaman",
    "Warlock": "warlock",
    "Warrior": "warrior",
}


def _bloco(texto: str, nome: str) -> str:
    # Tabelas do serializador não têm chaves aninhadas; ``[^}]`` evita
    # vazar para o bloco seguinte (SlotIds é de uma linha só).
    casamento = re.search(rf"Amr\.{nome}\s*=\s*\{{([^}}]*)\}}", texto, re.DOTALL)
    return casamento.group(1) if casamento else ""


def _mapa_nome_id(bloco: str) -> dict[int, str]:
    saida: dict[int, str] = {}
    for nome, valor in re.findall(r'\["([^"]+)"\]\s*=\s*(\d+)', bloco):
        if nome.upper() == "NONE" or nome.lower() == "none":
            continue
        saida[int(valor)] = nome.lower()
    return saida


def _specs(bloco: str) -> dict[int, str]:
    saida: dict[int, str] = {}
    for spec_blizzard, indice, comentario in re.findall(
        r"\[(\d+)\]\s*=\s*(\d+),?\s*--\s*(\w+)", bloco
    ):
        for rotulo, token in CLASSES.items():
            if comentario.startswith(rotulo):
                saida[int(indice)] = token
                break
    return saida


def _spec_nomes(bloco: str) -> dict[int, str]:
    """Índice AMR -> token de spec do simc (``DruidBalance`` -> ``balance``)."""
    saida: dict[int, str] = {}
    for _spec_blizzard, indice, comentario in re.findall(
        r"\[(\d+)\]\s*=\s*(\d+),?\s*--\s*(\w+)", bloco
    ):
        for rotulo in sorted(CLASSES, key=len, reverse=True):
            if comentario.startswith(rotulo):
                resto = comentario[len(rotulo):]
                token = re.sub(r"(?<!^)(?=[A-Z])", "_", resto).lower()
                if token:
                    saida[int(indice)] = token
                break
    return saida


def _slots(bloco: str) -> list[int]:
    return [int(valor) for valor in re.findall(r"\d+", bloco)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-dir", type=Path, default=PADRAO)
    args = parser.parse_args(argv)

    toc = args.addon_dir / "AskMrRobot.toc"
    serializador = (
        args.addon_dir / "AskMrRobot-Serializer" / "AskMrRobot-Serializer.lua"
    )
    if not toc.is_file() or not serializador.is_file():
        print(f"Addon não encontrado em {args.addon_dir}")
        return 1

    versao = "0"
    for linha in toc.read_text(encoding="utf-8", errors="replace").splitlines():
        if linha.startswith("## Version:"):
            versao = linha.split(":", 1)[1].strip()
            break

    texto = serializador.read_text(encoding="utf-8", errors="replace")
    class_ids = _mapa_nome_id(_bloco(texto, "ClassIds"))
    race_ids = _mapa_nome_id(_bloco(texto, "RaceIds"))
    faction_ids = _mapa_nome_id(_bloco(texto, "FactionIds"))
    specs = _specs(_bloco(texto, "SpecIds"))
    spec_nomes = _spec_nomes(_bloco(texto, "SpecIds"))
    slots = _slots(_bloco(texto, "SlotIds"))

    if not specs or not class_ids:
        print("Não foi possível ler os enums do serializador.")
        return 1

    mapa: dict = {"versoes": {}}
    if DESTINO.is_file():
        try:
            mapa = json.loads(DESTINO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mapa = {"versoes": {}}

    versoes = mapa.setdefault("versoes", {})
    versoes[versao] = {
        "specs": {str(indice): classe for indice, classe in sorted(specs.items())},
        "spec_nomes": {str(indice): nome for indice, nome in sorted(spec_nomes.items())},
        "racas": {str(rid): nome for rid, nome in sorted(race_ids.items())},
        "faccoes": {str(fid): nome for fid, nome in sorted(faction_ids.items())},
        "classes": {str(cid): nome for cid, nome in sorted(class_ids.items())},
        "slots": slots,
    }
    mapa["_meta"] = {
        "fonte": "AddOn AskMrRobot local (AskMrRobot-Serializer.lua + .toc)",
        "addon_versao": versao,
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "versoes": sorted(versoes),
        "total_specs": sum(len(v.get("specs", {})) for v in versoes.values()),
    }
    DESTINO.write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Gravado {DESTINO} | addon v{versao} | specs={len(specs)} "
        f"| racas={len(race_ids)} | slots={len(slots)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
