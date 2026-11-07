"""Verify bonus_id -> item level using Wowhead tooltips with the exact bonus list."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAIDA = PROJECT_ROOT / "dados" / "verificacao" / "bonus.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

CASOS = [
    ("heroi_6_6", 271546, [13692, 6652, 13695, 13698, 12846], 321),
    ("mito_1_6", 271546, [13692, 6652, 13695, 13698, 12849], 318),
    ("mito_6_6", 271543, [6652, 12854, 13696, 13695, 1587], 334),
    ("forjado_mito", 273781, [6652, 13668, 12856], 341),
    ("aventureiro_1_6", 271546, [13692, 6652, 13695, 13698, 12817], 266),
    ("aventureiro_6_6", 271546, [13692, 6652, 13695, 13698, 12822], 282),
]

ILVL = re.compile(r"N[ií]vel do Item:\s*<!--ilvl-->(\d+)")
TRACK = re.compile(r"N[ií]vel de aprimoramento:\s*([^<]+)")


def _fetch(item_id: int, bonus: list[int]) -> str:
    bonus_q = urllib.parse.quote(":".join(str(b) for b in bonus))
    url = (
        f"https://nether.wowhead.com/tooltip/item/{item_id}"
        f"?dataEnv=1&locale=8&bonus={bonus_q}"
    )
    requisicao = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        return json.loads(resposta.read().decode("utf-8")).get("tooltip", "")


def main() -> int:
    resultados = []
    for nome, item_id, bonus, esperado in CASOS:
        tooltip = _fetch(item_id, bonus)
        ilvl_match = ILVL.search(tooltip)
        track_match = TRACK.search(tooltip)
        ilvl = int(ilvl_match.group(1)) if ilvl_match else None
        resultados.append(
            {
                "caso": nome,
                "item_id": item_id,
                "bonus": bonus,
                "ilvl_esperado": esperado,
                "ilvl_wowhead": ilvl,
                "track_wowhead": track_match.group(1).strip() if track_match else None,
                "igual": ilvl == esperado,
                "fonte": "nether.wowhead.com/tooltip/item com bonus",
            }
        )
        print(f"{nome}: esperado={esperado} wowhead={ilvl} igual={ilvl == esperado}")

    dados = {
        "_meta": {
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(resultados),
            "iguais": sum(1 for item in resultados if item["igual"]),
        },
        "casos": resultados,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Gravado {SAIDA}")
    return 0 if dados["_meta"]["iguais"] == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
