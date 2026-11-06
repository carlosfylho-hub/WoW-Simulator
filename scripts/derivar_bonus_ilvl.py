"""Derive bonus_id -> item level from the Raidbots static data.

Only the five Midnight upgrade tracks are kept. Forged items come from the
project's season2_context.json. The output is small, versioned and carries the
Raidbots build and content hash.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DADOS = PROJECT_ROOT / "dados"
DESTINO = DADOS / "derivados" / "bonus_ilvl.json"
URL_META = "https://www.raidbots.com/static/data/live/metadata.json"
URL_SETS = "https://www.raidbots.com/static/data/live/bonus-upgrade-sets.json"

FAIXAS = {
    "Aventureiro": range(12817, 12823),
    "Veterano": range(12825, 12831),
    "Campeao": range(12833, 12839),
    "Heroi": range(12841, 12847),
    "Mito": range(12849, 12855),
}
FORJADOS = {"12848": 328, "12856": 341}


def _fetch(url: str) -> dict:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def _trilha(bonus_id: int) -> str | None:
    for nome, faixa in FAIXAS.items():
        if bonus_id in faixa:
            return nome
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Só compara o hash.")
    args = parser.parse_args()

    meta = _fetch(URL_META)
    conjuntos = _fetch(URL_SETS)

    bonus: dict[str, dict] = {}
    for grupo, entradas in conjuntos.items():
        if not isinstance(entradas, list):
            continue
        for entrada in entradas:
            if not isinstance(entrada, dict):
                continue
            bonus_id = entrada.get("bonusId")
            if not isinstance(bonus_id, int):
                continue
            trilha = _trilha(bonus_id)
            if trilha is None:
                continue
            bonus[str(bonus_id)] = {
                "trilha": trilha,
                "rank": f"{entrada.get('level')}/{entrada.get('max')}",
                "ilvl": entrada.get("itemLevel"),
                "grupo": int(grupo) if str(grupo).isdigit() else grupo,
                "evidencia": "raidbots:bonus-upgrade-sets",
                "fonte": "raidbots:bonus-upgrade-sets",
            }

    esperados = sum(len(faixa) for faixa in FAIXAS.values())
    faltando = [bid for faixa in FAIXAS.values() for bid in faixa if str(bid) not in bonus]

    for bonus_id, ilvl in FORJADOS.items():
        bonus[bonus_id] = {
            "trilha": "Forjado com Peconha",
            "rank": None,
            "ilvl": ilvl,
            "grupo": None,
            "evidencia": "sistema_forjado_com_peconha.tabela_ilvl",
            "fonte": "season2_context.json",
        }

    validacoes = {
        "heroi_6_6_321": bonus.get("12846", {}).get("ilvl") == 321,
        "mito_6_6_334": bonus.get("12854", {}).get("ilvl") == 334,
        "mito_1_6_318": bonus.get("12849", {}).get("ilvl") == 318,
        "aventureiro_1_6_266": bonus.get("12817", {}).get("ilvl") == 266,
        "forjado_heroi_328": bonus.get("12848", {}).get("ilvl") == 328,
        "forjado_mito_341": bonus.get("12856", {}).get("ilvl") == 341,
    }

    anterior = None
    if DESTINO.is_file():
        try:
            anterior = json.loads(DESTINO.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            anterior = None

    if args.check:
        hash_anterior = (anterior or {}).get("_meta", {}).get("content_hash")
        if hash_anterior == meta.get("contentHash"):
            print("Snapshot em dia.")
            return 0
        print("Snapshot divergente ou ausente; rode sem --check.")
        return 1

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "_meta": {
            "documento": "bonus_ilvl.json",
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fonte": "raidbots:bonus-upgrade-sets",
            "url": URL_SETS,
            "wow_build": meta.get("wowBuild"),
            "content_hash": meta.get("contentHash"),
            "gerado_pelo_raidbots_em": meta.get("generatedAt"),
            "esperados": esperados,
            "encontrados": len(bonus) - len(FORJADOS),
            "faltando": faltando,
            "validacoes": validacoes,
            "validado": all(validacoes.values()) and not faltando,
        },
        "bonus": bonus,
    }
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Gravado {DESTINO}")
    print(f"build={meta.get('wowBuild')} hash={meta.get('contentHash')}")
    print(f"tracks={len(bonus) - len(FORJADOS)}/{esperados} faltando={len(faltando)}")
    for nome, ok in validacoes.items():
        print(f"  {nome}: {'ok' if ok else 'FALHOU'}")
    return 0 if dados["_meta"]["validado"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
