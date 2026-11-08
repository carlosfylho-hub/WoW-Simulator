"""Deriva as peças de tier set de cada classe direto do ``item_data.inc`` do SimC.

Por que existe: os JSONs de spec trazem só os *nomes* das peças de tier, sem
``item_id``. O SimC guarda ``id_set`` e ``class_mask`` em cada item, então a
fonte autoritativa é o próprio dado compilado no binário que roda a simulação.

Regra de seleção (documentada no ``_meta`` do arquivo gerado): por classe, vale o
conjunto de 5 peças (cabeça, ombros, torso, mãos, pernas), qualidade Épica, com
máscara de uma única classe, de **maior item_id** (o mais recente).

Uso:
    python scripts/derivar_tier_sets.py
    python scripts/derivar_tier_sets.py --simc-dir ../simc-midnight --saida dados/derivados/tier_sets.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# class_mask do SimC (1 << (id_da_classe - 1)) -> nome de classe do SimC.
CLASSES = {
    0x1: "warrior",
    0x2: "paladin",
    0x4: "hunter",
    0x8: "rogue",
    0x10: "priest",
    0x20: "death_knight",
    0x40: "shaman",
    0x80: "mage",
    0x100: "warlock",
    0x200: "monk",
    0x400: "druid",
    0x800: "demon_hunter",
    0x1000: "evoker",
}
# inventory_type -> slot do simc. Torso aparece como 5 (armadura) ou 20 (manto).
SLOT_POR_INV = {1: "head", 3: "shoulder", 5: "chest", 20: "chest", 7: "legs", 10: "hands"}
SLOTS_TIER = ("head", "shoulder", "chest", "hands", "legs")

_LINHA = re.compile(r'\{ "((?:[^"\\]|\\.)*)",\s*(.*?)\s*\},?\s*(//.*)?$')


def ler_itens_com_set(caminho: Path) -> dict[int, list[dict]]:
    """Lê o ``item_data.inc`` e agrupa por ``id_set`` (apenas ``id_set != 0``)."""
    conjuntos: dict[int, list[dict]] = defaultdict(list)
    with caminho.open(encoding="utf-8", errors="replace") as arquivo:
        for linha in arquivo:
            texto = linha.strip()
            if not texto.startswith('{ "'):
                continue
            casamento = _LINHA.match(texto)
            if not casamento:
                continue
            resto = re.sub(r"\{[^}]*\}", "SOCK", casamento.group(2))
            campos = [campo.strip() for campo in resto.split(",")]
            # id,fl1,fl2,tf,level,reql,rs,rsl,quality,inv,cls,sub,bind,delay,dmg,
            # mod,&stats,cnt,cmask,rmask,SOCK,gemprop,sockbonus,idset,curve,art,craftq
            if len(campos) < 24:
                continue
            try:
                id_set = int(campos[23])
                if not id_set:
                    continue
                conjuntos[id_set].append(
                    {
                        "item_id": int(campos[0]),
                        "nome_en": casamento.group(1),
                        "ilvl_base": int(campos[4]),
                        "qualidade": int(campos[8]),
                        "inv": int(campos[9]),
                        "class_mask": int(campos[18], 0),
                    }
                )
            except ValueError:
                continue
    return conjuntos


def escolher_por_classe(conjuntos: dict[int, list[dict]]) -> dict[str, dict]:
    """Escolhe, por classe, o conjunto de tier de 5 peças mais recente."""
    candidatos: dict[str, list[tuple[int, int, dict[str, list[dict]]]]] = defaultdict(list)
    for id_set, itens in conjuntos.items():
        if len(itens) != 5:
            continue
        if any(item["qualidade"] != 4 for item in itens):
            continue
        masks = {item["class_mask"] for item in itens}
        if len(masks) != 1:
            continue
        mask = next(iter(masks))
        classe = CLASSES.get(mask)
        if classe is None:
            continue
        por_slot: dict[str, list[dict]] = defaultdict(list)
        for item in itens:
            slot = SLOT_POR_INV.get(item["inv"])
            if slot:
                por_slot[slot].append(item)
        if sorted(por_slot) != sorted(SLOTS_TIER):
            continue
        if any(len(v) != 1 for v in por_slot.values()):
            continue
        candidatos[classe].append((max(i["item_id"] for i in itens), id_set, por_slot))

    saida: dict[str, dict] = {}
    for classe, lista in candidatos.items():
        _, id_set, por_slot = max(lista, key=lambda t: t[0])
        mask = next(m for m, nome in CLASSES.items() if nome == classe)
        saida[classe] = {
            "set_id": id_set,
            "class_mask": mask,
            "slots": {slot: [por_slot[slot][0]["item_id"]] for slot in SLOTS_TIER},
            "nomes_en": {slot: por_slot[slot][0]["nome_en"] for slot in SLOTS_TIER},
        }
    return dict(sorted(saida.items()))


def _build(simc_dir: Path) -> str | None:
    for arquivo in simc_dir.rglob("client_data_version.inc"):
        achado = re.search(r'CLIENT_DATA_WOW_VERSION\s+"([^"]+)"', arquivo.read_text(errors="replace"))
        if achado:
            return achado.group(1)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simc-dir", type=Path, default=RAIZ.parent / "simc-midnight")
    parser.add_argument("--saida", type=Path, default=RAIZ / "dados" / "derivados" / "tier_sets.json")
    args = parser.parse_args(argv)

    item_data = args.simc_dir / "engine" / "dbc" / "generated" / "item_data.inc"
    if not item_data.exists():
        print(f"item_data.inc não encontrado em {item_data}", file=sys.stderr)
        return 2

    por_classe = escolher_por_classe(ler_itens_com_set(item_data))
    if not por_classe:
        print("Nenhum conjunto de tier encontrado; abortando sem gravar.", file=sys.stderr)
        return 3

    documento = {
        "_meta": {
            "fonte": "simc engine/dbc/generated/item_data.inc (id_set, class_mask, inventory_type)",
            "wow_build": _build(args.simc_dir),
            "regra": (
                "Por classe: conjunto de 5 peças (head, shoulder, chest, hands, legs), "
                "qualidade Épica, máscara de uma única classe, de maior item_id (mais recente)."
            ),
            "classes": len(por_classe),
        },
        "por_classe": por_classe,
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(por_classe)} classes gravadas em {args.saida}")
    for classe, info in por_classe.items():
        print(f"  {classe:13s} set {info['set_id']}  {info['slots']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
