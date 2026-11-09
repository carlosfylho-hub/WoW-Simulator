"""Efeitos e bônus de conjunto de TODOS os itens que o simulador mostra.

Drops de M+ (``mplus_loot_database.json``), peças de tier (todas as classes) e
peças craftáveis. Para cada item, lê o tooltip PT-BR do Wowhead e guarda:
- ``efeito``: textos "Equipar:"/"Uso:" do próprio item (berloques, colares, armas...);
- ``conjunto``: nome, nº de peças e bônus (no tier, um por especialização);
- ``engaste``: se o item tem Engaste Prismático.
Grava ``dados/derivados/tooltips_itens.json``. Só para a TELA (P1): o dano vem do simc.

Peças de tier do mesmo conjunto têm os mesmos bônus: basta 1 peça por classe;
as outras peças herdam o ``conjunto`` (é o mesmo conjunto do jogo, não estimativa).

Coletores: ``--json`` (um ou mais arquivos {item_id: tooltip}) → HTTP direto →
Crawl4AI → Firecrawl (``FIRECRAWL_API_KEY``). Itens cujo tooltip não foi obtido
ficam listados em ``_meta.sem_tooltip``; sem ``--parcial`` nada é gravado.

Uso (no Windows, com internet):
    python scripts/raspar_tooltips_itens.py
    python scripts/raspar_tooltips_itens.py --json fixtures/efeitos_embutidos/tooltips_pt.json fixtures/efeitos_embutidos/tooltips_tier_pt.json --parcial
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from raspar_efeitos_embutidos import coletar, extrair, ids_embutidos, salvar_cache  # noqa: E402

DESTINO = RAIZ / "dados" / "derivados" / "tooltips_itens.json"


def ids_por_grupo() -> dict[str, set[int]]:
    from wowsim.data import tier
    from wowsim.data.embellishments import listar_craftados
    from wowsim.masmorras.catalogo import itens_por_masmorra

    return {
        "mplus": {i.item_id for i in itens_por_masmorra()},
        "tier": {i for c in tier.todos().values() for i in c.ids},
        "craft": {int(r["item_id"]) for r in listar_craftados()} | set(ids_embutidos()),
    }


def conjuntos_de_tier() -> list[set[int]]:
    from wowsim.data import tier

    return [set(c.ids) for c in tier.todos().values()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, nargs="*", help="tooltips já salvos {item_id: tooltip}")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--parcial", action="store_true", help="grava mesmo sem o tooltip de todos")
    args = ap.parse_args(argv)

    grupos = ids_por_grupo()
    todos = sorted(set().union(*grupos.values()))
    if args.json:
        tooltips: dict[int, str] = {}
        for arq in args.json:
            tooltips.update(coletar(todos, arq))
    else:
        # Tier: 1 peça por conjunto basta (as outras herdam o bônus).
        alvo = [i for i in todos if i not in grupos["tier"] or i in {min(s) for s in conjuntos_de_tier()}]
        tooltips = coletar(alvo, None)
        salvar_cache(tooltips, "itens")  # reprocessar: --json cache/tooltips_wowhead/itens.json

    itens: dict[str, dict] = {}
    for item_id, tooltip in tooltips.items():
        dado = extrair(tooltip) or {}  # tooltip obtido sem efeito também é dado (item sem efeito)
        itens[str(item_id)] = dado
    for conjunto in conjuntos_de_tier():
        fonte = next((itens[str(i)] for i in sorted(conjunto) if itens.get(str(i), {}).get("conjunto")), None)
        if fonte:
            for i in conjunto:
                itens.setdefault(str(i), {}).setdefault("conjunto", fonte["conjunto"])
    sem = [i for i in todos if str(i) not in itens]
    print(f"{len(itens)}/{len(todos)} itens com tooltip ({len(sem)} sem)")
    if sem and not args.parcial:
        print("NÃO gravado (P1): sem tooltip para " + ", ".join(map(str, sem[:20])) + ("…" if len(sem) > 20 else ""))
        return 1
    saida = {
        "_meta": {
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gerador": "scripts/raspar_tooltips_itens.py",
            "fonte": "nether.wowhead.com tooltip PT-BR (locale=8)",
            "sem_tooltip": sem,
            "parcial": bool(sem),
        },
        "itens": dict(sorted(itens.items(), key=lambda kv: int(kv[0]))),
    }
    args.destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravado {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
