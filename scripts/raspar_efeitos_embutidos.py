"""Efeito do embelezamento EMBUTIDO das peças craftadas (o que já vem no item).

Ex.: Elo do Adorador dos Loas — "Equipar: ... evocando o avatar de um loa ...".
Esses efeitos não são reagentes (não estão em ``embelezamentos.json``); o texto
vem do tooltip PT-BR do Wowhead (``nether.wowhead.com/tooltip/item/<id>?locale=8``).
Gera ``dados/derivados/efeitos_embutidos.json``. Só para a TELA (P1): o dano
continua vindo do simc, que já simula o efeito do próprio item.

Coletores (o primeiro que funcionar vale para cada item):
1. ``--json ARQ``: tooltips já salvos ({item_id: tooltip}) — offline/teste;
2. HTTP direto (urllib) no endpoint JSON do Wowhead;
3. **Crawl4AI**;
4. **Firecrawl** (``FIRECRAWL_API_KEY`` no ambiente).

Se faltar o efeito de algum item, NÃO grava (código 1) — salvo ``--parcial``.

Uso:
    python scripts/raspar_efeitos_embutidos.py
    python scripts/raspar_efeitos_embutidos.py --json fixtures/efeitos_embutidos/tooltips_pt.json
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

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
DESTINO = RAIZ / "dados" / "derivados" / "efeitos_embutidos.json"
URL = "https://nether.wowhead.com/tooltip/item/{id}?dataEnv=1&locale=8"
AGENTE = "Mozilla/5.0 (wowsim; tooltip de efeito embutido)"


def ids_embutidos() -> list[int]:
    from wowsim.data.embellishments import listar_craftados

    return sorted({int(r["item_id"]) for r in listar_craftados() if r.get("embutido")})


# ------------------------------------------------------------------ coleta
def _tooltip_de_json(texto: str) -> str | None:
    try:
        return json.loads(texto).get("tooltip")
    except (ValueError, AttributeError):
        m = re.search(r"\{.*\}", texto or "", re.S)
        return _tooltip_de_json(m.group(0)) if m and m.group(0) != texto else None


def _direto(item_id: int) -> str | None:
    req = urllib.request.Request(URL.format(id=item_id), headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return _tooltip_de_json(r.read().decode("utf-8"))


async def _crawl4ai(ids: list[int]) -> dict[int, str]:
    from crawl4ai import AsyncWebCrawler  # type: ignore[import-not-found]

    saida: dict[int, str] = {}
    async with AsyncWebCrawler() as crawler:
        for item_id in ids:
            r = await crawler.arun(url=URL.format(id=item_id))
            bruto = re.sub(r"<[^>]+>", "", getattr(r, "html", "") or "")
            t = _tooltip_de_json(bruto)
            if t:
                saida[item_id] = t
    return saida


def _firecrawl(item_id: int) -> str | None:
    chave = os.environ.get("FIRECRAWL_API_KEY")
    if not chave:
        return None
    corpo = json.dumps({"url": URL.format(id=item_id), "formats": ["rawHtml"]}).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v1/scrape", data=corpo,
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        dados = json.loads(r.read().decode("utf-8"))
    return _tooltip_de_json((dados.get("data") or {}).get("rawHtml") or "")


def coletar(ids: list[int], arq_json: Path | None) -> dict[int, str]:
    if arq_json is not None:
        dados = json.loads(arq_json.read_text(encoding="utf-8"))
        return {int(k): v for k, v in dados.items() if k.isdigit() and int(k) in ids}
    saida: dict[int, str] = {}
    for item_id in ids:
        try:
            t = _direto(item_id)
            if t:
                saida[item_id] = t
        except Exception as erro:  # noqa: BLE001
            print(f"  direto falhou em {item_id}: {erro}")
    faltam = [i for i in ids if i not in saida]
    if faltam:
        try:
            saida.update(asyncio.run(_crawl4ai(faltam)))
        except ImportError:
            print("  crawl4ai não instalado; pulando.")
        except Exception as erro:  # noqa: BLE001
            print(f"  crawl4ai falhou: {erro}")
    for item_id in [i for i in ids if i not in saida]:
        try:
            t = _firecrawl(item_id)
            if t:
                saida[item_id] = t
        except Exception as erro:  # noqa: BLE001
            print(f"  firecrawl falhou em {item_id}: {erro}")
    return saida


# ---------------------------------------------------------------- extração
def _limpar(texto: str) -> str:
    texto = re.sub(r"\(\s*1\s*\*\s*(\d+)\s*\)", r"\1", texto)                    # (1 * 846) -> 846
    texto = re.sub(r"\(\s*1\s*\*\s*(\d+)\s*\*\s*(\d+)\s*\)", r"\1 × \2", texto)    # (1 * 161 * 10)
    texto = re.sub(r"\[\s*1\s*\*\s*(\d+)\s*\*\s*\(\s*(\d+)\s*\)\s*\]", r"\1 × \2", texto)
    texto = re.sub(r"([.!)])(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", r"\1 ", texto)                  # frases coladas
    return re.sub(r"\s+", " ", texto).strip()


def extrair(tooltip: str) -> dict | None:
    """Efeito ("Equipar:"/"Uso:") e bônus de conjunto ("(2) Conjunto :")."""
    efeitos = [
        _limpar(m.group(1))
        for m in re.finditer(r"((?:Equipar|Uso):.*?)(?=Equipar:|Uso:|Requer Nível|Preço de Venda|$)", tooltip, re.S)
    ]
    conjunto = None
    m_nome = re.search(r"Requer Nível \d+(.+?) \(0/(\d+)\)", tooltip)
    bonus = [
        {"pecas": int(m.group(1)), "efeito": _limpar(m.group(2))}
        for m in re.finditer(r"\((\d)\) Conjunto\s*:\s*(.*?)(?=\(\d\) Conjunto|Preço de Venda|$)", tooltip, re.S)
    ]
    if bonus:
        conjunto = {
            "nome": m_nome.group(1).strip() if m_nome else None,
            "total": int(m_nome.group(2)) if m_nome else None,
            "bonus": bonus,
        }
    if not efeitos and not conjunto:
        return None
    return {"efeito": " ".join(efeitos) or None, "conjunto": conjunto, "engaste": "Engaste Prismático" in tooltip}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path, help="tooltips já salvos {item_id: tooltip}")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--parcial", action="store_true", help="grava mesmo se faltar algum item")
    args = ap.parse_args(argv)

    ids = ids_embutidos()
    tooltips = coletar(ids, args.json)
    itens: dict[str, dict] = {}
    faltou: list[int] = []
    for item_id in ids:
        dado = extrair(tooltips.get(item_id) or "")
        if dado is None:
            faltou.append(item_id)
        else:
            itens[str(item_id)] = dado
    print(f"{len(itens)}/{len(ids)} itens com efeito")
    if faltou and not args.parcial:
        print("NÃO gravado (P1): sem efeito para " + ", ".join(map(str, faltou)))
        return 1
    saida = {
        "_meta": {
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gerador": "scripts/raspar_efeitos_embutidos.py",
            "fonte": "nether.wowhead.com tooltip PT-BR (locale=8)",
            "sem_efeito": faltou,
        },
        "itens": itens,
    }
    args.destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravado {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
