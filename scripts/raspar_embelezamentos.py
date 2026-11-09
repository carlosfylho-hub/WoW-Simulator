"""Raspa o Wowhead para os dados visuais dos embelezamentos (ícone, texto, materiais).

Só para a TELA (P1): nenhum número daqui vira dano. O ganho continua vindo do
simc via ``embellishment=<token>``.

Pipeline (cada passo é determinístico e verificável):

1. Tooltip JSON leve (``nether.wowhead.com/tooltip/item/<id>``) em PT-BR
   (``locale=8``) e EN (``locale=0``): nome, ícone, qualidade e HTML do efeito.
2. ``crawl4ai`` (opcional) na página renderizada do item. Em vez de procurar
   texto solto, a página é fatiada nas abas (``id="tab-*"``) e cada linha de
   ``<tr>`` vira ``{item_id, nome, quantidade}``. Assim sabemos qual lista é de
   materiais e qual é de "usado em", sem adivinhar pela ordem do texto.
3. Segundo salto: se a página diz *quem cria* o reagente (âncoras
   ``spell=<id>``), o tooltip JSON da receita é lido para trazer os materiais
   com quantidade (``"3× Nome"``). Esse passo não usa navegador.
4. Cache de HTML em ``cache/wowhead/pagina/<id>.html``: reexecutar é offline e
   instantâneo, e o ``--html`` permite ajustar seletores sem rede.

Se nada for encontrado, o campo fica vazio e o motivo vai para ``_falhas``.
Nunca inventamos (P1).

Uso:
    python scripts/raspar_embelezamentos.py
    python scripts/raspar_embelezamentos.py --ids 240167 240165 --delay 0.5
    python scripts/raspar_embelezamentos.py --sem-pagina
    python scripts/raspar_embelezamentos.py --debug-html 240167
    python scripts/raspar_embelezamentos.py --html cache/wowhead/pagina/240167.html
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
from typing import Callable

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[1]
DADOS = ROOT / "dados"
DESTINO = DADOS / "derivados" / "embelezamentos_wowhead.json"
CACHE = ROOT / "cache" / "wowhead"
CACHE_PAGINA = CACHE / "pagina"
TOOLTIP = "https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale={locale}"
TOOLTIP_RECEITA = "https://nether.wowhead.com/tooltip/spell/{spell_id}?dataEnv=1&locale={locale}"
PAGINA = "https://www.wowhead.com/pt/item={item_id}"
AGENTE = "wowsim/0.1 (+local embellishment scrape via crawl4ai)"
ICONE = "https://wow.zamimg.com/images/wow/icons/large/{slug}.jpg"

PAGINA_TIMEOUT_MS = 60_000
RENDER_ESPERA_S = 2.5
TENTATIVAS = 3
MAX_MATERIAIS = 20
MAX_USO = 12
MIN_HTML = 2_000

# Avaliado uma vez só: se o crawl4ai não está instalado, não repetimos o erro 21 vezes.
_CRAWL4AI_ERRO: str | None = None
_CRAWL4AI_TESTADO = False


# ---------------------------------------------------------------------------
# HTTP + cache
# ---------------------------------------------------------------------------


def _ler_json(caminho: Path) -> dict | None:
    if caminho.is_file():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _json_de_url(url: str, arquivo: Path) -> dict | None:
    """JSON com cache em disco; rede falha devolve ``None`` (nunca levanta)."""
    em_cache = _ler_json(arquivo)
    if em_cache is not None:
        return em_cache
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, ValueError, OSError):
        return None
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return dados


def _tooltip(item_id: int, locale: int) -> dict | None:
    return _json_de_url(
        TOOLTIP.format(item_id=item_id, locale=locale),
        CACHE / f"{item_id}_{locale}.json",
    )


def _tooltip_receita(spell_id: int, locale: int) -> dict | None:
    return _json_de_url(
        TOOLTIP_RECEITA.format(spell_id=spell_id, locale=locale),
        CACHE / f"spell_{spell_id}_{locale}.json",
    )


# ---------------------------------------------------------------------------
# HTML -> texto / estruturas
# ---------------------------------------------------------------------------


def texto_do_html(bruto: str) -> str:
    """HTML do tooltip -> texto legível (sem tags e sem scripts)."""
    texto = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", bruto or "")
    texto = re.sub(r"(?i)<br\s*/?>", "\n", texto)
    # Blocos fecham linha: sem isso a página inteira vira uma linha só e o
    # recorte por título ("Criado por"/"Usado em") não tem o que ler depois.
    texto = re.sub(r"(?i)</(?:p|div|li|tr|td|h[1-6]|table|section|ul|ol)\s*>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"[ \t]+", " ", html.unescape(texto))
    texto = re.sub(r" *\n *", "\n", texto)
    return re.sub(r"\n\s*\n+", "\n", texto).strip()


def _texto_limpo(bruto: str) -> str:
    """Texto de um trecho curto de HTML, em uma linha."""
    return re.sub(r"\s+", " ", texto_do_html(bruto)).strip(" -•\t")


_RUIDO = (
    "comentar",
    "contribuir",
    "orden",
    "anterior",
    "próximo",
    "captura de tela",
    "enviar",
    "logado",
    "idiomas",
    "editar",
    "ver em 3d",
)


def _secao(texto: str, titulo: str, *, evitar: tuple[str, ...] = ()) -> list[str]:
    """Linhas de uma seção ("Criado por"/"Usado em"), descartando ruído.

    ``evitar`` impede casar um título que contém outro: "Reagentes para" também
    contém "Reagentes", e sem isso as duas abas se misturam.
    """
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        baixo_linha = linha.lower()
        if titulo.lower() not in baixo_linha:
            continue
        if any(alvo.lower() in baixo_linha for alvo in evitar):
            continue
        itens: list[str] = []
        for seguinte in linhas[i + 1:]:
            limpo = seguinte.strip(" -•\t")
            if not limpo:
                if itens:
                    break
                continue
            baixo = limpo.lower()
            if len(limpo) > 60 or any(ruido in baixo for ruido in _RUIDO):
                continue
            itens.append(limpo)
            if len(itens) >= MAX_USO:
                break
        return itens
    return []


_RE_TAB = re.compile(
    r'<div[^>]*\bid="(tab-[a-z0-9-]+)"[^>]*>(.*?)(?=<div[^>]*\bid="tab-[a-z0-9-]+"|\Z)',
    re.I | re.S,
)
_RE_ANCORA_ITEM = re.compile(
    r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.I | re.S
)
_RE_ANCORA_SPELL = re.compile(
    r'<a\b[^>]*?href="[^"]*?spell=(\d+)[^"]*"[^>]*>(.*?)</a>', re.I | re.S
)
_RE_ITEM_NA_URL = re.compile(r"[?&/]item=(\d+)", re.I)
_RE_SPELL_NA_URL = re.compile(r"[?&/]spell=(\d+)", re.I)
_RE_TR = re.compile(r"<tr\b.*?</tr>", re.I | re.S)

_TABS_MATERIAIS = ("created", "criado", "craft", "reagent", "reagente", "recipe", "receita")
_TABS_USO = ("for", "para", "used", "usado", "teaches", "aprende", "contained", "contido")


def _classificar_aba(tab_id: str) -> str | None:
    """Diz se a aba fala de materiais ("criado por") ou de onde o item é usado."""
    chave = tab_id.lower().removeprefix("tab-")
    # "reagent-for" contém "reagent"; a ordem importa.
    if any(marca in chave for marca in _TABS_USO):
        return "usado_em"
    if any(marca in chave for marca in _TABS_MATERIAIS):
        return "materiais"
    return None


def _quantidade(bloco: str, nome: str) -> int | None:
    """Quantidade de uma linha de receita (``3 x Nome``), se explícita."""
    sem_ancoras = re.sub(r"(?is)<a\b.*?</a>", " ", bloco)
    texto = _texto_limpo(sem_ancoras).replace(nome, " ")
    achado = re.search(r"\b(\d{1,3})\b", texto)
    if not achado:
        return None
    valor = int(achado.group(1))
    return valor if 0 < valor <= 999 else None


def _itens_do_bloco(bloco: str) -> list[dict]:
    """Cada ``<tr>`` (ou o bloco inteiro) vira ``{item_id, nome, quantidade}``.

    Preferimos linhas de tabela porque nelas a quantidade está na mesma linha do
    nome; se não houver tabela, caímos nas âncoras soltas (sem quantidade).
    """
    saida: list[dict] = []
    vistos: set[int] = set()
    linhas = _RE_TR.findall(bloco) or [bloco]
    for linha in linhas:
        for ancora in _RE_ANCORA_ITEM.finditer(linha):
            url, interno = ancora.group(1), ancora.group(2)
            achado = _RE_ITEM_NA_URL.search(url)
            if not achado:
                continue
            item_id = int(achado.group(1))
            nome = _texto_limpo(interno)
            if not nome or len(nome) > 60 or item_id in vistos:
                continue
            vistos.add(item_id)
            saida.append(
                {"item_id": item_id, "nome": nome, "quantidade": _quantidade(linha, nome)}
            )
    return saida


def _formatar_linha(registro: dict) -> str:
    qtd = registro.get("quantidade")
    nome = registro.get("nome")
    if nome is None:
        # Nome ainda não resolvido (só o id veio do Listview): não inventamos.
        nome = f"#{registro['item_id']}" if registro.get("item_id") is not None else "?"
    return f"{qtd}× {nome}" if qtd else str(nome)


def _receitas_da_pagina(bruto: str) -> list[int]:
    """Ids de spell (receita) que criam o item, na ordem em que aparecem."""
    ids: list[int] = []
    for achado in _RE_ANCORA_SPELL.finditer(bruto or ""):
        valor = int(achado.group(1))
        if valor not in ids:
            ids.append(valor)
    return ids


def _fechar_colchete(texto: str, inicio: int) -> int | None:
    """Índice do ``]`` que fecha o ``[`` em ``inicio``, respeitando strings."""
    profundidade = 0
    dentro_string = False
    escape = False
    for i in range(inicio, len(texto)):
        ch = texto[i]
        if dentro_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                dentro_string = False
            continue
        if ch == '"':
            dentro_string = True
        elif ch == "[":
            profundidade += 1
        elif ch == "]":
            profundidade -= 1
            if profundidade == 0:
                return i
    return None


def _extrair_listview_data(bruto: str, listview_id: str) -> list[dict] | None:
    """Array ``data:`` de um ``new Listview({ id: '<listview_id>', ... })``.

    Esses blobs trazem o dado estruturado que o Wowhead renderiza nas abas:
    ``created-by-spell`` tem ``reagents`` (ids + quantidade); ``reagent-for``
    tem ``creates``/``displayName``. Devolve ``None`` quando não existe.
    """
    marca = re.search(r"id:\s*['\"]" + re.escape(listview_id) + r"['\"]", bruto or "")
    if not marca:
        return None
    pos_data = bruto.find("data:", marca.end())
    if pos_data == -1:
        return None
    inicio = bruto.find("[", pos_data)
    fim = _fechar_colchete(bruto, inicio) if inicio != -1 else None
    if fim is None:
        return None
    try:
        dados = json.loads(bruto[inicio : fim + 1])
    except json.JSONDecodeError:
        return None
    return dados if isinstance(dados, list) else None


def _materiais_do_listview(
    receitas: list, resolver_nome: Callable[[int], str | None] | None = None
) -> list[dict]:
    """Reagentes de uma receita (``reagents: [[id, quantidade], ...]``)."""
    registros: list[dict] = []
    vistos: set[int] = set()
    for receita in receitas:
        if not isinstance(receita, dict):
            continue
        for par in receita.get("reagents") or []:
            if not isinstance(par, (list, tuple)) or not par:
                continue
            try:
                item_id = int(par[0])
            except (TypeError, ValueError):
                continue
            if item_id in vistos:
                continue
            vistos.add(item_id)
            qtd = par[1] if len(par) > 1 and isinstance(par[1], int) else None
            nome = resolver_nome(item_id) if resolver_nome else None
            registros.append({"item_id": item_id, "nome": nome, "quantidade": qtd})
    return registros


def _usado_em_do_listview(receitas: list) -> list[dict]:
    """Itens criados por receitas que usam este reagente (``creates`` + nome)."""
    registros: list[dict] = []
    vistos: set[object] = set()
    for receita in receitas:
        if not isinstance(receita, dict):
            continue
        cria = receita.get("creates") or []
        item_id: int | None = None
        chave: object
        if isinstance(cria, (list, tuple)) and cria and isinstance(cria[0], int):
            item_id = cria[0]
            chave = item_id
        else:
            chave = receita.get("displayName") or receita.get("name")
        if chave in vistos:
            continue
        vistos.add(chave)
        nome = receita.get("displayName") or receita.get("name")
        registros.append({"item_id": item_id, "nome": nome, "quantidade": None})
    return registros


def _nome_do_item(item_id: int) -> str | None:
    """Nome PT-BR (ou EN) do item, pelo tooltip JSON em cache/rede."""
    dados = _tooltip(item_id, 8) or _tooltip(item_id, 0) or {}
    return dados.get("name")


def _nome_do_cache(item_id: int) -> str | None:
    """Nome do item usando só o cache local (modo offline/``--html``)."""
    for locale in (8, 0):
        dados = _ler_json(CACHE / f"{item_id}_{locale}.json") or {}
        if dados.get("name"):
            return dados["name"]
    return None


def extrair_pagina(
    bruto: str,
    *,
    texto: str | None = None,
    resolver_nome: Callable[[int], str | None] | None = None,
) -> dict:
    """Página do Wowhead -> materiais e "usado em", sem adivinhação.

    Ordem de confiança: (1) os blobs ``new Listview({...})`` embutidos, que
    trazem a receita com ``reagents`` (ids + quantidade) e as receitas que usam
    o reagente (``creates`` + nome); (2) as abas ``id="tab-*"`` do HTML;
    (3) o recorte por título do texto. ``_fonte`` diz qual caminho respondeu.
    """
    bruto = bruto or ""
    materiais: list[dict] = []
    usado_em: list[dict] = []
    fonte = "vazio"

    # (1) Listviews: dado estruturado, o caminho mais confiável.
    criado_por = _extrair_listview_data(bruto, "created-by-spell")
    reagente_para = _extrair_listview_data(bruto, "reagent-for")
    if criado_por:
        materiais = _materiais_do_listview(criado_por, resolver_nome)
    if reagente_para:
        usado_em = _usado_em_do_listview(reagente_para)
    if materiais or usado_em:
        fonte = "listview"

    # (2) Abas do HTML (quando não há Listview com o dado).
    if not materiais and not usado_em:
        for tab_id, bloco in _RE_TAB.findall(bruto):
            destino = _classificar_aba(tab_id)
            if destino is None:
                continue
            itens = _itens_do_bloco(bloco)
            if not itens:
                continue
            fonte = "abas"
            alvo = materiais if destino == "materiais" else usado_em
            conhecidos = {registro["item_id"] for registro in alvo}
            alvo.extend(item for item in itens if item["item_id"] not in conhecidos)

    # (3) Texto solto, último recurso.
    if not materiais and not usado_em:
        texto = texto if texto is not None else texto_do_html(bruto)
        for titulo in ("Criado por", "Created by"):
            nomes = _secao(texto, titulo, evitar=("reagentes para", "reagent for"))
            if nomes:
                materiais = [{"item_id": None, "nome": n, "quantidade": None} for n in nomes]
                fonte = "texto"
                break
        for titulo in ("Usado em", "Used in", "Reagentes para", "Reagent for"):
            nomes = _secao(texto, titulo)
            if nomes:
                usado_em = [{"item_id": None, "nome": n, "quantidade": None} for n in nomes]
                fonte = "texto" if fonte == "vazio" else fonte
                break

    return {
        "materiais": [_formatar_linha(registro) for registro in materiais[:MAX_MATERIAIS]],
        "usado_em": [
            str(registro["nome"]) for registro in usado_em[:MAX_USO] if registro.get("nome")
        ],
        "_detalhe": {
            "materiais": materiais[:MAX_MATERIAIS],
            "usado_em": usado_em[:MAX_USO],
        },
        "_fonte": fonte,
    }


def _materiais_da_receita(spell_id: int) -> list[str]:
    """Reagentes de uma receita, do tooltip JSON (sem navegador)."""
    dados = _tooltip_receita(spell_id, 8) or _tooltip_receita(spell_id, 0) or {}
    linhas = _itens_do_bloco(dados.get("tooltip") or "")
    if not linhas:
        # O tooltip às vezes traz só texto ("3 x Nome"); recorta a seção.
        nomes = _secao(texto_do_html(dados.get("tooltip") or ""), "Reagentes")
        return nomes[:MAX_MATERIAIS]
    return [_formatar_linha(registro) for registro in linhas[:MAX_MATERIAIS]]


# ---------------------------------------------------------------------------
# crawl4ai (opcional)
# ---------------------------------------------------------------------------


def _crawl4ai_erro() -> str | None:
    """Mensagem de indisponibilidade (ou ``None``). Avaliada uma única vez."""
    global _CRAWL4AI_ERRO, _CRAWL4AI_TESTADO
    if _CRAWL4AI_TESTADO:
        return _CRAWL4AI_ERRO
    _CRAWL4AI_TESTADO = True
    try:
        import crawl4ai  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001 - import quebrado também é indisponível
        _CRAWL4AI_ERRO = (
            "crawl4ai indisponível "
            f"({type(exc).__name__}); instale com "
            "`pip install crawl4ai` e `python -m playwright install chromium`"
        )
    return _CRAWL4AI_ERRO


def _html_do_resultado(resultado: object) -> str:
    """Melhor HTML disponível do CrawlResult, tolerando versões diferentes."""
    bruto = getattr(resultado, "html", None) or ""
    if isinstance(bruto, str) and bruto.strip():
        return bruto
    markdown = getattr(resultado, "markdown", None)
    if isinstance(markdown, str):
        return markdown
    for campo in ("fit_markdown", "raw_markdown"):
        valor = getattr(markdown, campo, None)
        if isinstance(valor, str) and valor.strip():
            return valor
    return ""


async def _rodar_crawler(url: str) -> str:
    """Abre a URL num Chromium headless e devolve o HTML já renderizado."""
    from crawl4ai import (  # noqa: PLC0415 - import caro, só quando usado
        AsyncWebCrawler,
        BrowserConfig,
        CacheMode,
        CrawlerRunConfig,
    )

    navegador = BrowserConfig(headless=True, verbose=False)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=PAGINA_TIMEOUT_MS,
        delay_before_return_html=RENDER_ESPERA_S,
        wait_until="domcontentloaded",
        word_count_threshold=3,
        excluded_tags=["script", "style", "noscript", "nav", "footer", "header"],
        exclude_external_links=True,
        verbose=False,
    )
    async with AsyncWebCrawler(config=navegador) as crawler:
        resultado = await crawler.arun(url=url, config=config)
    if not getattr(resultado, "success", True):
        motivo = getattr(resultado, "error_message", None) or "falhou"
        raise RuntimeError(str(motivo))
    return _html_do_resultado(resultado)


async def _html_da_pagina(item_id: int, *, forcar: bool = False) -> tuple[str | None, str | None]:
    """HTML da página do item, com cache em disco. Devolve ``(html, erro)``."""
    arquivo = CACHE_PAGINA / f"{item_id}.html"
    if arquivo.is_file() and not forcar:
        try:
            return arquivo.read_text(encoding="utf-8", errors="replace"), None
        except OSError:
            pass
    indisponivel = _crawl4ai_erro()
    if indisponivel:
        return None, indisponivel

    erro = "crawl4ai: página vazia"
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            bruto = await _rodar_crawler(PAGINA.format(item_id=item_id))
        except Exception as exc:  # noqa: BLE001 - rede/browser não devem quebrar
            erro = f"crawl4ai: {type(exc).__name__}: {exc}"
            await asyncio.sleep(1.5 * tentativa)
            continue
        if len(bruto) >= MIN_HTML:
            CACHE_PAGINA.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(bruto, encoding="utf-8")
            return bruto, None
        erro = f"crawl4ai: página curta ({len(bruto)} bytes)"
        await asyncio.sleep(1.0 * tentativa)
    return None, erro


async def _pagina(item_id: int, *, forcar: bool = False) -> dict:
    """Materiais da receita e "usado em" do item. Vazio se não achar."""
    bruto, erro = await _html_da_pagina(item_id, forcar=forcar)
    if bruto is None:
        return {"materiais": [], "usado_em": [], "_fonte": "vazio", "_falhas": [erro or "sem html"]}

    extraido = extrair_pagina(bruto, resolver_nome=_nome_do_item)
    falhas: list[str] = []

    # Segundo salto: sem materiais na página, tenta a receita que cria o item.
    if not extraido["materiais"]:
        for spell_id in _receitas_da_pagina(bruto)[:3]:
            materiais = _materiais_da_receita(spell_id)
            if materiais:
                extraido["materiais"] = materiais
                extraido["_fonte"] = f"receita:{spell_id}"
                break

    if not extraido["materiais"]:
        falhas.append("materiais não encontrados")
    if not extraido["usado_em"]:
        falhas.append("usado em não encontrado")
    extraido["_falhas"] = falhas
    return extraido


# ---------------------------------------------------------------------------
# Montagem do JSON final
# ---------------------------------------------------------------------------


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


async def _coletar(
    ids: list[int], delay: float, incluir_pagina: bool, *, forcar: bool = False
) -> list[dict]:
    saida: list[dict] = []
    for item_id in ids:
        entrada = _entrada(item_id, _tooltip(item_id, 8), _tooltip(item_id, 0))
        if incluir_pagina:
            entrada.update(await _pagina(item_id, forcar=forcar))
        saida.append(entrada)
        if delay:
            time.sleep(delay)
    return saida


def _debug_html(item_id: int) -> int:
    """Roda só o crawl de um id e grava o HTML cru, para conferir seletores."""
    bruto, erro = asyncio.run(_html_da_pagina(item_id, forcar=True))
    if bruto is None:
        print(f"falhou: {erro}")
        return 1
    CACHE_PAGINA.mkdir(parents=True, exist_ok=True)
    arquivo = CACHE_PAGINA / f"{item_id}.html"
    arquivo.write_text(bruto, encoding="utf-8")
    extraido = extrair_pagina(bruto, resolver_nome=_nome_do_item)
    print(f"{len(bruto)} bytes -> {arquivo}")
    print(f"abas vistas: {[tab for tab, _ in _RE_TAB.findall(bruto)]}")
    print(f"fonte: {extraido['_fonte']}")
    print(f"materiais: {extraido['materiais']}")
    print(f"usado_em: {extraido['usado_em']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="*", default=None)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--sem-pagina", action="store_true", help="Só tooltip JSON (sem crawl4ai).")
    parser.add_argument("--forcar-pagina", action="store_true", help="Ignora o cache de HTML.")
    parser.add_argument("--debug-html", type=int, default=None, help="Só baixa o HTML de um id.")
    parser.add_argument("--html", type=Path, default=None, help="Lê um HTML já salvo (offline).")
    args = parser.parse_args()

    if args.debug_html is not None:
        return _debug_html(args.debug_html)

    if args.html is not None:
        try:
            bruto = args.html.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"não foi possível ler {args.html}: {exc}")
            return 1
        extraido = extrair_pagina(bruto, resolver_nome=_nome_do_cache)
        print(json.dumps(extraido, ensure_ascii=False, indent=2))
        return 0

    ids = args.ids or _ids_padrao()
    embelezamentos = asyncio.run(
        _coletar(ids, args.delay, not args.sem_pagina, forcar=args.forcar_pagina)
    )
    sem_icone = [e["reagente_id"] for e in embelezamentos if not e.get("icone_url")]
    sem_materiais = [e["reagente_id"] for e in embelezamentos if not e.get("materiais")]

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(
            {
                "_meta": {
                    "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "gerado_por": "scripts/raspar_embelezamentos.py",
                    "fonte": "Wowhead (tooltip JSON + Listview/abas via crawl4ai, best-effort)",
                    "sem_icone": sem_icone,
                    "sem_materiais": sem_materiais,
                },
                "embelezamentos": embelezamentos,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(embelezamentos)} embelezamentos -> {DESTINO} "
        f"(sem ícone: {sem_icone}; sem materiais: {len(sem_materiais)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
