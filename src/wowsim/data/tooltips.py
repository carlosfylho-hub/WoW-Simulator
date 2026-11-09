"""Efeito e bônus de conjunto dos itens (``dados/derivados/tooltips_itens.json``).

Gerado por ``scripts/raspar_tooltips_itens.py`` (tooltip PT-BR do Wowhead). Só
para a tela (P1). Sem o arquivo ou sem o item, devolve vazio — nunca inventa.
"""

from __future__ import annotations

from functools import lru_cache

from . import catalog


@lru_cache(maxsize=1)
def _itens() -> dict:
    try:
        return catalog._derivado("tooltips_itens.json").get("itens") or {}
    except (FileNotFoundError, OSError, ValueError):
        return {}


def info(item_id: int | None) -> dict:
    """``{"efeito": str | None, "conjunto": dict | None}`` do item (vazio se não houver)."""
    if item_id is None:
        return {}
    reg = _itens().get(str(item_id)) or {}
    return {k: reg[k] for k in ("efeito", "conjunto") if reg.get(k)}
