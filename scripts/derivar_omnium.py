"""Derive the Omnium Folio entry table from Raidbots static data.

Each choice entry (1368xx) is mapped to a rune code (1A..5C) by spell id using
the project's rune_ids_s2.json. The output records entry id, spell id, node and
PT-BR name for all 13 runes.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DADOS = PROJECT_ROOT / "dados"
DESTINO = DADOS / "derivados" / "omnium_entries.json"
URL_META = "https://www.raidbots.com/static/data/live/metadata.json"
URL_OMNIUM = "https://www.raidbots.com/static/data/live/omnium-talents.json"


def _fetch(url: str) -> dict:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Só compara o hash.")
    args = parser.parse_args()

    meta = _fetch(URL_META)
    arvore = _fetch(URL_OMNIUM)
    runas = json.loads((DADOS / "rune_ids_s2.json").read_text(encoding="utf-8"))["runas"]

    indice: dict[int, dict] = {}
    for runa in runas:
        for chave in ("id_base", "id_buff"):
            valor = runa.get(chave)
            if isinstance(valor, int):
                indice[valor] = runa

    entradas: list[dict] = []
    for no in arvore.get("nodes", []):
        for escolha in no.get("entries", []):
            spell_id = escolha.get("spellId")
            runa = indice.get(spell_id)
            entradas.append(
                {
                    "entry_id": escolha.get("id"),
                    "spell_id": spell_id,
                    "nome_en": escolha.get("name"),
                    "index": escolha.get("index"),
                    "node_id": no.get("id"),
                    "node_nome_en": no.get("name"),
                    "escolha": runa.get("escolha") if runa else None,
                    "linha": runa.get("linha") if runa else None,
                    "nome_pt": runa.get("nome_pt") if runa else None,
                    "mapeado": runa is not None,
                    "fonte": "raidbots:omnium-talents",
                }
            )

    nao_mapeados = [entrada for entrada in entradas if not entrada["mapeado"]]
    tem_136814 = any(entrada["entry_id"] == 136814 for entrada in entradas)

    if args.check:
        hash_anterior = None
        if DESTINO.is_file():
            hash_anterior = (
                json.loads(DESTINO.read_text(encoding="utf-8"))
                .get("_meta", {})
                .get("content_hash")
            )
        if hash_anterior == meta.get("contentHash"):
            print("Snapshot em dia.")
            return 0
        print("Snapshot divergente ou ausente; rode sem --check.")
        return 1

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "_meta": {
            "documento": "omnium_entries.json",
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fonte": "raidbots:omnium-talents",
            "url": URL_OMNIUM,
            "wow_build": meta.get("wowBuild"),
            "content_hash": meta.get("contentHash"),
            "total_entradas": len(entradas),
            "esperado": 13,
            "nao_mapeados": [entrada["entry_id"] for entrada in nao_mapeados],
            "tem_136814": tem_136814,
            "completo": len(entradas) == 13 and not nao_mapeados and tem_136814,
        },
        "entradas": entradas,
    }
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Gravado {DESTINO}")
    print(f"build={meta.get('wowBuild')} entradas={len(entradas)} nao_mapeados={len(nao_mapeados)}")
    for entrada in sorted(entradas, key=lambda e: (e.get("linha") or 99, e.get("index") or 0)):
        print(
            f"  {entrada['entry_id']} -> {entrada['escolha']} "
            f"{entrada['nome_pt'] or entrada['nome_en']} spell={entrada['spell_id']}"
        )
    return 0 if dados["_meta"]["completo"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
