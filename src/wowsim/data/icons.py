"""Central icon index built from every JSON snapshot.

Icon names are WoW texture slugs (``inv_...``). Some files store the slug in
``icone``/``icon`` and others only a zamimg URL; numeric render URLs (Blizzard
icon ids) cannot be converted to a slug and are ignored instead of guessed.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from ..paths import DADOS_DIR, DERIVADOS_DIR

CAMPOS_SLUG = ("icone", "icon")
CAMPOS_URL = ("icone_url", "icon_url", "icone_url_media", "icon_url_media")
_ID_NUMERICO = re.compile(r"^\d+$")


@lru_cache(maxsize=2)
def _arquivos(raiz: str, assinatura: tuple) -> dict[int, str]:
    """Scan JSON files once. ``assinatura`` invalidates when files change."""
    indice: dict[int, str] = {}
    for caminho in Path(raiz).rglob("*.json"):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item_id, slug in _percorrer(dados):
            if slug:
                indice.setdefault(item_id, slug)
    return indice


def _slug(valor: str) -> str | None:
    texto = valor.strip()
    if not texto:
        return None
    if "/" in texto:
        texto = texto.rstrip("/").split("/")[-1]
    texto = texto.split("?")[0]
    if "." in texto:
        texto = texto.rsplit(".", 1)[0]
    if _ID_NUMERICO.match(texto):
        return None
    return texto or None


def _percorrer(node: object) -> Iterator[tuple[int, str | None]]:
    if isinstance(node, dict):
        item_id = node.get("id", node.get("item_id"))
        if isinstance(item_id, int):
            slug = None
            for campo in CAMPOS_SLUG:
                valor = node.get(campo)
                if isinstance(valor, str):
                    slug = _slug(valor)
                    if slug:
                        break
            if not slug:
                for campo in CAMPOS_URL:
                    valor = node.get(campo)
                    if isinstance(valor, str):
                        slug = _slug(valor)
                        if slug:
                            break
            yield item_id, slug
        for valor in node.values():
            yield from _percorrer(valor)
    elif isinstance(node, list):
        for valor in node:
            yield from _percorrer(valor)


def _assinatura(raiz: Path) -> tuple:
    return tuple(
        (str(caminho), caminho.stat().st_mtime_ns)
        for caminho in sorted(raiz.rglob("*.json"))
    )


def _derivados() -> dict[int, str]:
    """Scraped icons live in derivados/icones.json and win over the snapshot."""
    caminho = DERIVADOS_DIR / "icones.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    icones = dados.get("icones")
    if not isinstance(icones, dict):
        return {}
    saida: dict[int, str] = {}
    for chave, valor in icones.items():
        try:
            item_id = int(chave)
        except (TypeError, ValueError):
            continue
        if isinstance(valor, str) and valor.strip():
            saida[item_id] = valor.strip()
    return saida


def _indice() -> dict[int, str]:
    raiz = DADOS_DIR
    if not raiz.is_dir():
        return _derivados()
    indice = _derivados()
    for item_id, slug in _arquivos(str(raiz), _assinatura(raiz)).items():
        indice.setdefault(item_id, slug)
    return indice


def limpar_cache() -> None:
    _arquivos.cache_clear()


def icone(item_id: int) -> str | None:
    """Texture slug for an item id, or None when no trusted source has one."""
    return _indice().get(item_id)


def listar() -> dict[int, str]:
    return dict(_indice())
