"""Raspa o Wowhead para os dados visuais dos embelezamentos (ícone, texto, materiais).

Só para a TELA (P1): nenhum número daqui vira dano. O ganho continua vindo do
simc via ``embellishment=<token>``.

Pipeline:
1. Tooltip JSON leve (``nether.wowhead.com/tooltip/item/<id>``) em PT-BR
   (``locale=8``) e EN (``locale=0``): nome, ícone, qualidade e HTML do efeito.
2. ``crawl4ai`` (opcional) na página renderizada: materiais da receita ("Criado
   por") e onde o reagente pode ser usado. Se a página não trouxer de forma
   estável, o campo fica vazio — não adivinhamos.
3. Cache em ``cache/wowhead/`` e falha de rede não derruba o script.

Saída: ``dados/derivados/embelezamentos_wowhead.json``, mesclado depois por
``scripts/derivar_embelezamentos.py``.

Uso:
    python scripts/raspar_embelezamentos.py
    python scripts/raspar_embelezamentos.py --ids 240167 240165 --delay 0.5
    python scripts/raspar_embelezamentos.py --sem-pagina
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
DADOS = ROOT / "dados"
DESTINO = DADOS / "derivados" / "embelezamentos_wowhead.json"
CACHE = ROOT / "cache" / "wowhead"
TOOLTIP = "https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale={locale}"
PAGINA = "https://www.wowhead.com/pt/item={item_id}"
AGENTE = "wowsim/0.1 (+local embellishment scrape via crawl4ai)"
ICONE = "https://wow.zamimg.com/images/wow/icons/large/{slug}.jpg"


def _ler_json(caminho: Path) -> dict | None:
    if caminho.is_file():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _tooltip(item_id: int, locale: int) -> dict | None:
    arquivo = CACHE / f"{item_id}_{locale}.json"
    em_cache = _ler_json(arquivo)
    if em_cache is not None:
        return em_cache
    req = urllib.request.Request(
        TOOLTIP.format(item_id=item_id, locale=locale), headers={"User-Agent": AGENTE}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados


def texto_do_html(bruto: str) -> str:
    """HTML do tooltip -> texto legível (sem tags e sem scripts)."""
    texto = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", bruto or "")
    texto = re.sub(r"(?i)<br\s*/?>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"[ \t]+", " ", html.unescape(texto))
    texto = re.sub(r" *\n *", "\n", texto)
    return re.sub(r"\n\s*\n+", "\n", texto).strip()


    """Pega as linhas de uma seção ("Criado por"/"Usado em") até a próxima vazia."""
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if titulo.lower() in linha.lower():
            itens: list[str] = []
            for seguinte in linhas[i + 1:]:
                limpo = seguinte.strip(" -•\t")
                if not limpo:
                    if itens:
                        break
                    continue
                itens.append(limpo)
                if len(itens) >= 12:
                    break
            return itens
    return []
    """Pega as linhas de uma seção ("Criado por"/"Usado em") até a próxima vazia."""
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if titulo.lower() in linha.lower():
            itens: list[str] = []
            for seguinte in linhas[i + 1:]:
                limpo = seguinte.strip(" -•\t")
                if not limpo:
                    if itens:
                        break
                    continue
                itens.append(limpo)
                if len(itens) >= 12:
                    break
            return itens
    return []


def _secao(texto: str, titulo: str) -> list[str]:
    """Linhas de uma seção ("Criado por"/"Usado em"), descartando ruído de navegação.

    A página do Wowhead mistura tabela, menu e comentários no texto; só aceitamos
    linhas curtas e claras. O que não for confiável fica de fora (P1: não adivinhar).
    """
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if titulo.lower() not in linha.lower():
            continue
        itens: list[str] = []
        for seguinte in linhas[i + 1:]:
            limpo = seguinte.strip(" -•\t")
            if not limpo:
                if itens:
                    break
                continue
            baixo = limpo.lower()
            if len(limpo) > 60 or any(
                ruido in baixo
                for ruido in (
                    "comentar",
                    "contribuir",
                    "orden",
                    "anterior",
                    "próximo",
                    "captura de tela",
                    "enviar",
                    "logado",
                    "idiomas",
                )
            ):
                continue
            itens.append(limpo)
            if len(itens) >= 12:
                break
        return itens
    return []


async def _pagina(item_id: int) -> dict:
    """crawl4ai: materiais da receita e 'usado em'. Vazio se não achar."""
    try:
        from crawl4ai import AsyncWebCrawler  # noqa: PLC0415
    except ImportError:
        return {"materiais": [], "usado_em": [], "_falhas": ["crawl4ai indisponível"]}
    try:
        async with AsyncWebCrawler(headless=True) as crawler:
            resultado = await crawler.arun(url=PAGINA.format(item_id=item_id))
    except Exception as exc:  # noqa: BLE001 - rede/browser não devem quebrar o script
        return {"materiais": [], "usado_em": [], "_falhas": [f"crawl4ai: {exc}"]}
    texto = texto_do_html(getattr(resultado, "html", "") or "")
    materiais = _secao(texto, "Criado por") or _secao(texto, "Created by")
    usado_em = _secao(texto, "Usado em") or _secao(texto, "Used in")
    falhas: list[str] = []
    if not materiais:
        falhas.append("materiais não encontrados")
    if not usado_em:
        falhas.append("usado em não encontrado")
    return {"materiais": materiais, "usado_em": usado_em, "_falhas": falhas}


def _entrada(item_id: int, pt: dict | None, en: dict | None) -> dict:
    pt = pt or {}
    en = en or {}
    icone = pt.get("icon") or en.get("icon")
    return {
        "reagente_id": item_id,
        "nome_pt": pt.get("name"),
        "nome_en": en.get("name"),
        "icone": icone,
        "icone_url": ICONE.format(slug=icone) if icone else None,
        "qualidade": pt.get("quality"),
        "texto_completo": texto_do_html(pt.get("tooltip") or ""),
        "texto_en": texto_do_html(en.get("tooltip") or ""),
        "materiais": [],
        "usado_em": [],
        "_falhas": [],
    }


def _ids_padrao() -> list[int]:
    dados = _ler_json(DADOS / "derivados" / "embelezamentos.json") or {}
    return [
        int(e["reagente_id"])
        for e in dados.get("embelezamentos", [])
        if isinstance(e, dict) and e.get("reagente_id") is not None
    ]


async def _coletar(ids: list[int], delay: float, incluir_pagina: bool) -> list[dict]:
    saida: list[dict] = []
    for item_id in ids:
        entrada = _entrada(item_id, _tooltip(item_id, 8), _tooltip(item_id, 0))
        if incluir_pagina:
            entrada.update(await _pagina(item_id))
        saida.append(entrada)
        if delay:
            time.sleep(delay)
    return saida


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="*", default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--sem-pagina", action="store_true", help="Só tooltip JSON (sem crawl4ai).")
    args = parser.parse_args()

    ids = args.ids or _ids_padrao()
    embelezamentos = asyncio.run(_coletar(ids, args.delay, not args.sem_pagina))
    sem_icone = [e["reagente_id"] for e in embelezamentos if not e.get("icone_url")]

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(
            {
                "_meta": {
                    "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "gerado_por": "scripts/raspar_embelezamentos.py",
                    "fonte": "Wowhead (tooltip JSON + crawl4ai, best-effort)",
                    "sem_icone": sem_icone,
                },
                "embelezamentos": embelezamentos,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(embelezamentos)} embelezamentos -> {DESTINO} (sem ícone: {sem_icone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
