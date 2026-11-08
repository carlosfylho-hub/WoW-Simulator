"""Scrape Mail and Plate armor for the Top Gear pools from Wowhead via crawl4ai.

Pipeline:
1. crawl4ai renders the Wowhead armor list pages (mail/plate) and we collect
   every ``item=<id>`` link from the rendered HTML.
2. For each id we read the ``nether.wowhead.com`` tooltip (locale 8 PT-BR and
   locale 0 EN) to get names, item level, slot, primary attribute and icon.
3. Only current-season pieces (``--min-ilvl``, default 300) in the armor slots
   are kept. Results are written to ``dados/armaduras_malha_placa.json`` with
   provenance; ``catalog.itens_da_secao`` merges this file into the pools.

Nothing here estimates stats: item level and names come straight from Wowhead.

Usage:
    python scripts/raspar_armaduras.py                 # mail + plate
    python scripts/raspar_armaduras.py --tipo malha
    python scripts/raspar_armaduras.py --ids 251199 251232 --tipo malha
    python scripts/raspar_armaduras.py --max-ids 200 --delay 0.2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# crawl4ai's rich logger uses arrow glyphs; force UTF-8 so Windows cp1252 does
# not crash the crawl.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim.paths import DADOS_DIR  # noqa: E402

DESTINO = DADOS_DIR / "armaduras_malha_placa.json"
AGENTE = "wowsim/0.1 (+local armor scrape via crawl4ai)"
TOOLTIP = "https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale={locale}"

# armor type (classe) -> (PT label, EN label, Wowhead list url, relevant specs)
TIPOS = {
    "malha": (
        "Malha",
        "Mail",
        "https://www.wowhead.com/items/armor/mail",
        ["Caçador", "Xamã", "Evocador"],
    ),
    "placa": (
        "Placa",
        "Plate",
        "https://www.wowhead.com/items/armor/plate",
        ["Guerreiro", "Paladino", "Cavaleiro da Morte"],
    ),
}

_ITEM_ID = re.compile(r"/item=(\d+)")
# Inside the embedded ``listviewitems`` array: id is always followed by level
# and name. Keys are unquoted elsewhere, so we parse this stable triple.
_ITEM_NIVEL = re.compile(r'"id":(\d+),"level":(\d+),"name"')
_ILVL_PT = re.compile(r"N[ií]vel do Item:\s*<!--ilvl-->(\d+)")
_ILVL_EN = re.compile(r"Item Level:\s*<!--ilvl-->(\d+)")
# Adaptive primary stat, e.g. "[Força ou Intelecto]" / "[Agilidade ou Intelecto]".
_ATRIB_PAR = re.compile(r"\[\s*([^\]\s][^\]]*?)\s+ou\s+([^\]]*?)\]")

# Slot detection from the localized tooltip line.
_SLOT_PT = (
    ("head", ("cabeça", "cabeca", "testa")),
    ("shoulder", ("ombros", "ombro", "omoplata")),
    ("chest", ("peitoral", "torso", "peito")),
    ("wrist", ("pulsos", "pulso", "bracelete")),
    ("hands", ("mãos", "maos", "luvas", "manoplas")),
    ("waist", ("cintura", "cinto")),
    ("legs", ("pernas", "perna", "calças", "calcas")),
    ("feet", ("pés", "pes", "botas")),
)
_ATRIBUTOS = ("Intelecto", "Força", "Agilidade")


def _get_json(url: str, tentativas: int = 3) -> dict | None:
    for tentativa in range(tentativas):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(requisicao, timeout=25) as resposta:  # noqa: S310
                return json.loads(resposta.read().decode("utf-8", errors="replace"))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError):
            if tentativa + 1 == tentativas:
                return None
            time.sleep(0.8)
    return None


def _slot_do_texto(texto: str) -> str | None:
    minusculo = texto.casefold()
    for slot, marcas in _SLOT_PT:
        if any(marca in minusculo for marca in marcas):
            return slot
    return None


def _atributos_do_texto(texto: str) -> list[str]:
    """Return every primary attribute the item can use.

    Modern armor carries an adaptive stat such as ``+189 [Força ou Intelecto]``
    (plate) or ``[Agilidade ou Intelecto]`` (mail), so a single fixed attribute
    would wrongly exclude legal specs.
    """
    casamento = _ATRIB_PAR.search(texto)
    if casamento:
        par = [casamento.group(1).strip(), casamento.group(2).strip()]
        return [atributo for atributo in par if atributo]
    for atributo in _ATRIBUTOS:
        if atributo.casefold() in texto.casefold():
            return [atributo]
    return []


def _ler_tooltip(item_id: int) -> dict:
    pt = _get_json(TOOLTIP.format(item_id=item_id, locale=8))
    en = _get_json(TOOLTIP.format(item_id=item_id, locale=0))
    tooltip = (pt or {}).get("tooltip") or ""
    ilvl = None
    for padrao in (_ILVL_PT, _ILVL_EN):
        casamento = padrao.search(tooltip)
        if casamento:
            ilvl = int(casamento.group(1))
            break
    return {
        "item_id": item_id,
        "nome_pt": (pt or {}).get("name"),
        "nome_en": (en or {}).get("name"),
        "ilvl": ilvl,
        "slot": _slot_do_texto(tooltip),
        "atributos": _atributos_do_texto(tooltip),
        "icone": (pt or {}).get("icon"),
        "qualidade": (pt or {}).get("quality"),
    }


def _ids_do_html(html: str, min_id: int) -> list[int]:
    """All item ids in the page's embedded ``listviewitems`` array.

    Wowhead renders only the first page as links, but the full item list lives
    in ``listviewitems``. Its ``level`` field is unreliable (legacy items carry
    odd values), so we keep modern ids by ``min_id`` and let the tooltip apply
    the authoritative ilvl range.
    """
    indice = html.find("listviewitems")
    if indice >= 0:
        inicio = html.find("[", indice)
        fim = html.find("];", inicio)
        if inicio >= 0 and fim > inicio:
            pares = _ITEM_NIVEL.findall(html[inicio:fim])
            if pares:
                return [
                    int(item_id)
                    for item_id, _nivel in pares
                    if int(item_id) >= min_id
                ]
    # Fallback: server-rendered anchors (first page only).
    return [int(valor) for valor in _ITEM_ID.findall(html)]


async def _ids_da_lista(
    url: str, min_id: int, limite: int | None, headless: bool
) -> list[int]:
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler(headless=headless) as crawler:
        resultado = await crawler.arun(url=url)
    html = (
        getattr(resultado, "html", "")
        or getattr(resultado, "cleaned_html", "")
        or ""
    )
    vistos: set[int] = set()
    ids: list[int] = []
    for item_id in _ids_do_html(html, min_id):
        if item_id in vistos:
            continue
        vistos.add(item_id)
        ids.append(item_id)
        if limite is not None and len(ids) >= limite:
            break
    return ids


def _montar_item(dados: dict, tipo: str) -> dict:
    item_id = dados["item_id"]
    icone = dados.get("icone")
    return {
        "item_id": item_id,
        "nome_pt": dados.get("nome_pt"),
        "nome_en": dados.get("nome_en"),
        "slot": dados["slot"],
        "atributos": list(dados.get("atributos") or []),
        "stats": {"ilvl_referencia": dados.get("ilvl")},
        "wowhead": f"https://www.wowhead.com/pt/item={item_id}",
        "armadura": tipo,
        "icone": icone,
        "icone_url": f"https://wow.zamimg.com/images/wow/icons/large/{icone}.jpg"
        if icone
        else None,
        "icone_url_medium": f"https://wow.zamimg.com/images/wow/icons/medium/{icone}.jpg"
        if icone
        else None,
    }


def _carregar_existente() -> dict:
    try:
        return json.loads(DESTINO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _raspar_tipo(
    tipo: str,
    ids_explicitos: list[int] | None,
    max_ids: int | None,
    min_id: int,
    min_ilvl: int,
    max_ilvl: int,
    delay: float,
    headless: bool,
) -> dict[str, list[dict]]:
    rotulo_pt, rotulo_en, url, _specs = TIPOS[tipo]
    if ids_explicitos:
        ids = ids_explicitos
    else:
        ids = asyncio.run(_ids_da_lista(url, min_id, max_ids, headless))
    print(f"[{tipo}] {len(ids)} ids coletados da lista completa (listviewitems).")

    por_slot: dict[str, list[dict]] = {}
    mantidos = 0
    for posicao, item_id in enumerate(ids, start=1):
        dados = _ler_tooltip(item_id)
        time.sleep(max(0.0, delay))

        if not dados.get("slot"):
            continue
        if dados.get("ilvl") is None or dados["ilvl"] < min_ilvl:
            continue
        if max_ilvl and dados["ilvl"] > max_ilvl:
            continue
        if not dados.get("nome_pt") and not dados.get("nome_en"):
            continue

        item = _montar_item(dados, tipo)
        por_slot.setdefault(dados["slot"], []).append(item)
        mantidos += 1
        print(
            f"[{tipo} {posicao}/{len(ids)}] {item_id} {dados.get('nome_pt')!r} "
            f"slot={dados['slot']} ilvl={dados['ilvl']} "
            f"attr={'/'.join(dados.get('atributos') or [])}"
        )

    for lista in por_slot.values():
        lista.sort(key=lambda registro: (-(registro["stats"].get("ilvl_referencia") or 0), registro["item_id"]))

    print(f"[{tipo}] {mantidos} itens mantidos em {len(por_slot)} slots.")
    return por_slot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tipo", choices=("malha", "placa", "ambos"), default="ambos")
    parser.add_argument("--ids", nargs="*", type=int, default=None)
    parser.add_argument("--max-ids", type=int, default=None)
    parser.add_argument("--min-ilvl", type=int, default=300)
    parser.add_argument(
        "--max-ilvl",
        type=int,
        default=350,
        help="Descarta itens legados/timewalking acima deste ilvl (0 = sem teto).",
    )
    parser.add_argument(
        "--min-id",
        type=int,
        default=240000,
        help="Só itens com id >= isto (foca na temporada atual; legados têm id baixo).",
    )
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    tipos = ["malha", "placa"] if args.tipo == "ambos" else [args.tipo]
    saida = _carregar_existente()
    saida.setdefault("_meta", {})

    for tipo in tipos:
        rotulo_pt, rotulo_en, url, specs = TIPOS[tipo]
        por_slot = _raspar_tipo(
            tipo,
            args.ids,
            args.max_ids,
            args.min_id,
            args.min_ilvl,
            args.max_ilvl,
            args.delay,
            headless=not args.headed,
        )
        secao = {
            "descricao": (
                f"Todas as peças de {rotulo_pt} ({rotulo_en}) raspadas do Wowhead "
                f"(crawl4ai) para o Top Gear."
            ),
            "specs_relevantes": specs,
            "fonte": {
                "lista": url,
                "tooltip": "nether.wowhead.com/tooltip/item (locale 8 + 0)",
                "metodo": "crawl4ai + tooltip",
                "min_id": args.min_id,
                "min_ilvl": args.min_ilvl,
                "max_ilvl": args.max_ilvl or None,
                "fonte_lista": "listviewitems (lista completa do Wowhead)",
            },
            **por_slot,
        }
        saida[f"armadura_{tipo}_mplus"] = secao
        saida["_meta"][f"armadura_{tipo}_mplus"] = {
            "itens": sum(len(lista) for lista in por_slot.values()),
            "slots": sorted(por_slot),
            "raspado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    saida["_meta"]["fonte"] = "Wowhead via crawl4ai"
    saida["_meta"]["gerado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nGravado {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
