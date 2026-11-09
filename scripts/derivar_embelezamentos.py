"""Gera dados/derivados/embelezamentos.json cruzando o jogo (PT-BR) com o simc.

Fontes:
- ``dados/craft_sistemas_s2.json`` (itens ``tipo == "embelezamento"``): reagente,
  nome PT/EN, para que serve (``usavel_com``) e o efeito em PT (``fornece_propriedade``).
- ``simc-midnight/engine/dbc/generated/embellishment_data.inc``: nome EN e bônus
  que o simc aplica com ``embellishment=<nome tokenizado>`` no item.

Uso: python scripts/derivar_embelezamentos.py [--simc CAMINHO_DO_SIMC]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PADRAO_SIMC = RAIZ.parent / "simc-midnight"


def tokenizar(nome: str) -> str:
    """Como ``util::tokenize_fn`` do simc: minúsculas, sem apóstrofo, '_' no lugar do resto."""
    t = nome.lower().replace("'", "")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    return t.strip("_")


def alvo(usavel_com: str, nome_en: str) -> str | None:
    """Onde o reagente pode ir. None = de profissão específica (fora do modo Craft)."""
    u = (usavel_com or "").lower()
    if "engenharia" in u or "ferraria" in u:
        return None
    if "acessórios" in u:
        return "acessorio"
    if "armas e itens de mão secundária" in u:
        return "arma"
    if "armas e armaduras" in u:
        return "arma_ou_armadura"
    if "armaduras" in u:
        return "armadura"
    if "equipamentos" in u:
        return "qualquer"
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--simc", type=Path, default=PADRAO_SIMC)
    args = p.parse_args()

    inc = (args.simc / "engine/dbc/generated/embellishment_data.inc").read_text(encoding="utf-8")
    simc = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*\d+\s*,\s*\d+\s*\}', inc)
    }
    build = re.search(r"wow build ([\d.]+)", inc)

    jogo = json.loads((RAIZ / "dados/craft_sistemas_s2.json").read_text(encoding="utf-8"))["itens"]
    saida, vistos, sem_simc = [], set(), []
    for reagente, v in sorted(jogo.items()):
        if v.get("tipo") != "embelezamento":
            continue
        nome_en = v.get("nome_en") or ""
        if nome_en in vistos:  # o jogo lista duas qualidades do mesmo reagente
            continue
        if nome_en not in simc:
            sem_simc.append(nome_en)
            continue
        vistos.add(nome_en)
        saida.append(
            {
                "reagente_id": int(reagente),
                "nome_pt": v.get("nome_pt"),
                "nome_en": nome_en,
                "token_simc": tokenizar(nome_en),
                "bonus_id": simc[nome_en],
                "alvo": alvo(v.get("usavel_com") or "", nome_en),
                "usavel_com": v.get("usavel_com"),
                "descricao": v.get("fornece_propriedade") or v.get("efeito_pt"),
            }
        )

    destino = RAIZ / "dados/derivados/embelezamentos.json"
    destino.write_text(
        json.dumps(
            {
                "_meta": {
                    "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "gerado_por": "scripts/derivar_embelezamentos.py",
                    "fontes": ["dados/craft_sistemas_s2.json", "simc engine/dbc/generated/embellishment_data.inc"],
                    "simc_build": build.group(1) if build else None,
                    "sem_correspondencia_no_simc": sem_simc,
                    "limite": "Único-equipado: Embelezado (2) — no máximo 2 efeitos ativos",
                },
                "embelezamentos": saida,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(saida)} embelezamentos -> {destino} (sem simc: {sem_simc})")


if __name__ == "__main__":
    main()
