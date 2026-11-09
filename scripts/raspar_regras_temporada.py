"""Raspa as regras da temporada (Midnight S2) que o jogo não expõe no export.

Gera ``dados/derivados/regras_temporada.json``, lido por ``data/regras.py``:

* Forja do Veneno (Ascendant Venomstones): custo, quais slots aceitam e o nível
  final (Method.gg);
* Craft: nível máximo por brasão (Herói/Mito), brasões por craft, centelhas
  (Icy Veins, Spark Crafting Guide);
* Upgrade: brasões por etapa (Icy Veins) e os descontos — marca do slot e o
  desconto de 50% do bando (WowCarry).

Ordem dos coletores (o primeiro que funcionar vale para cada página):

1. ``--md DIR``: lê páginas já salvas (``<chave>.md``) — offline, para teste;
2. **Crawl4AI** (``pip install crawl4ai`` + ``python -m playwright install chromium``);
3. **Firecrawl** (só se ``FIRECRAWL_API_KEY`` estiver no ambiente).

Cada página baixada é salva em ``cache/regras_temporada/<chave>.md``. Regra P1:
se um campo obrigatório não for achado, o script NÃO grava o JSON e lista o que
faltou (código de saída 1) — nunca grava valor estimado.

Uso:
    python scripts/raspar_regras_temporada.py
    python scripts/raspar_regras_temporada.py --md fixtures/regras_temporada
    python scripts/raspar_regras_temporada.py --coletor firecrawl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
DESTINO = ROOT / "dados" / "derivados" / "regras_temporada.json"
CACHE = ROOT / "cache" / "regras_temporada"

FONTES = {
    "method_venomstones": "https://www.method.gg/guides/how-to-unlock-ascendant-venomstones-in-wow-midnight-season-2-neck-weapon-trinket-upgrades",
    "icy_spark": "https://www.icy-veins.com/wow/spark-crafting-guide",
    "icy_upgrade": "https://www.icy-veins.com/wow/world-of-warcraft-gear-upgrading-guide",
    "wowcarry_desconto": "https://wowcarry.com/blog/wow/gearing-changes-in-midnight-crest-costs-free-discounts",
}


# --------------------------------------------------------------------- coleta
async def _crawl4ai(urls: dict[str, str]) -> dict[str, str]:
    from crawl4ai import AsyncWebCrawler  # type: ignore[import-not-found]

    saida: dict[str, str] = {}
    async with AsyncWebCrawler() as crawler:
        for chave, url in urls.items():
            r = await crawler.arun(url=url)
            md = getattr(r, "markdown", None)
            texto = getattr(md, "raw_markdown", None) or (md if isinstance(md, str) else None)
            if getattr(r, "success", False) and texto:
                saida[chave] = texto
            else:
                print(f"  crawl4ai falhou em {chave}: {getattr(r, 'error_message', '?')}")
    return saida


def _firecrawl(urls: dict[str, str]) -> dict[str, str]:
    chave_api = os.environ.get("FIRECRAWL_API_KEY")
    if not chave_api:
        print("  firecrawl: FIRECRAWL_API_KEY ausente; pulando.")
        return {}
    saida: dict[str, str] = {}
    for chave, url in urls.items():
        corpo = json.dumps({"url": url, "formats": ["markdown"], "onlyMainContent": True}).encode()
        req = urllib.request.Request(
            "https://api.firecrawl.dev/v1/scrape",
            data=corpo,
            headers={"Authorization": f"Bearer {chave_api}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
            texto = (dados.get("data") or {}).get("markdown")
            if texto:
                saida[chave] = texto
        except Exception as erro:  # noqa: BLE001 - registra e segue para a próxima
            print(f"  firecrawl falhou em {chave}: {erro}")
    return saida


def coletar(coletor: str, md_dir: Path | None) -> dict[str, str]:
    paginas: dict[str, str] = {}
    if md_dir is not None:
        for chave in FONTES:
            arq = md_dir / f"{chave}.md"
            if arq.is_file():
                paginas[chave] = arq.read_text(encoding="utf-8")
        return paginas
    faltam = dict(FONTES)
    if coletor in ("auto", "crawl4ai"):
        try:
            paginas.update(asyncio.run(_crawl4ai(faltam)))
        except ImportError:
            print("  crawl4ai não instalado (pip install crawl4ai; python -m playwright install chromium).")
        except Exception as erro:  # noqa: BLE001
            print(f"  crawl4ai falhou: {erro}")
    faltam = {k: v for k, v in FONTES.items() if k not in paginas}
    if faltam and coletor in ("auto", "firecrawl"):
        paginas.update(_firecrawl(faltam))
    CACHE.mkdir(parents=True, exist_ok=True)
    for chave, texto in paginas.items():
        (CACHE / f"{chave}.md").write_text(texto, encoding="utf-8")
    return paginas


# ------------------------------------------------------------------- extração
def _num(padrao: str, texto: str, grupo: int = 1) -> int | None:
    m = re.search(padrao, texto, re.I | re.S)
    return int(m.group(grupo)) if m else None


def extrair(paginas: dict[str, str]) -> tuple[dict, list[str]]:
    faltou: list[str] = []
    venom = paginas.get("method_venomstones", "")
    spark = paginas.get("icy_spark", "")
    upgrade = paginas.get("icy_upgrade", "")
    desconto = paginas.get("wowcarry_desconto", "")

    def linha(rotulo: str) -> tuple[int, int] | None:
        m = re.search(rf"\|\s*{rotulo}\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", venom, re.I)
        return (int(m.group(1)), int(m.group(2))) if m else None

    forja = {
        "custo": _num(r"collect\s+(\d+)\s+Ascendant Venomstones", venom)
        or _num(r"use\s+(\d+)\s+of them", venom),
        "moeda": "Ascendant Venomstone",
        "mito": linha("Myth Track Items"),
        "heroi": linha("Hero Track Items"),
        "craft_arma_mito": linha("Tidal Crafted Myth Weapon"),
        "craft_arma_heroi": linha("Tidal Crafted Hero Weapon"),
        "aceita_colar": bool(re.search(r"Necklaces", venom)),
        "aceita_berloque": bool(re.search(r"Trinkets", venom)),
        "aceita_arma": bool(re.search(r"Weapons", venom)),
    }
    for k in ("custo", "mito", "heroi", "craft_arma_mito", "craft_arma_heroi"):
        if forja[k] is None:
            faltou.append(f"forja.{k}")
    slots = []
    if forja.pop("aceita_arma"):
        slots += ["main_hand", "off_hand"]
    if forja.pop("aceita_berloque"):
        slots += ["trinket1", "trinket2"]
    if forja.pop("aceita_colar"):
        slots += ["neck"]
    if not slots:
        faltou.append("forja.slots")
    forja["slots"] = slots
    for k in ("mito", "heroi", "craft_arma_mito", "craft_arma_heroi"):
        if forja[k]:
            forja[k] = {"antes": forja[k][0], "depois": forja[k][1]}

    m = re.search(r"up to\s+(\d+)\s+or\s+(\d+)\s+item level", spark, re.I)
    craft = {
        "brasoes": _num(r"add\s+(\d+)\s+Hero or Myth crests", spark),
        "ilvl_max": {"heroi": int(m.group(1)), "mito": int(m.group(2))} if m else None,
        "ilvl_sem_brasao": _num(r"can go up to\s+(\d+)\s+item level", spark),
        "centelhas": {
            "padrao": 2 if re.search(r"Two sparks are needed", spark, re.I) else None,
            "duas_maos": 4 if re.search(r"four being required", spark, re.I) else None,
        },
    }
    for k in ("brasoes", "ilvl_max", "ilvl_sem_brasao"):
        if craft[k] is None:
            faltou.append(f"craft.{k}")
    if None in craft["centelhas"].values():
        faltou.append("craft.centelhas")

    up = {
        "brasoes_por_etapa": _num(r"\|\s*(\d+)\s+Adventurer\s*\|", upgrade),
        "marca_do_slot": bool(re.search(r"without spending additional Mistcrests", desconto, re.I)),
        "desconto_bando_pct": _num(r"(\d+)%\s+Warband discount", desconto),
    }
    if up["brasoes_por_etapa"] is None:
        faltou.append("upgrade.brasoes_por_etapa")
    if not up["marca_do_slot"]:
        faltou.append("upgrade.marca_do_slot")
    if up["desconto_bando_pct"] is None:
        faltou.append("upgrade.desconto_bando_pct")
    return {"forja": forja, "craft": craft, "upgrade": up}, faltou


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", type=Path, help="pasta com <chave>.md já salvos (offline)")
    ap.add_argument("--coletor", choices=("auto", "crawl4ai", "firecrawl"), default="auto")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args(argv)

    paginas = coletar(args.coletor, args.md)
    print(f"Páginas obtidas: {sorted(paginas)} de {sorted(FONTES)}")
    regras, faltou = extrair(paginas)
    if faltou:
        print("NÃO gravado (P1): faltou " + ", ".join(faltou))
        return 1
    regras["_meta"] = {
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gerador": "scripts/raspar_regras_temporada.py",
        "coletor": "md" if args.md else args.coletor,
        "fontes": FONTES,
        "patch": "12.1.5",
    }
    args.destino.write_text(json.dumps(regras, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravado {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
