"""Season 2 consumables used by the Top Gear search.

Data now lives in ``dados/consumiveis_s2.json`` with explicit provenance
instead of being hardcoded here. Tokens are the SimulationCraft profile
keywords (``flask=``, ``potion=``, ``food=``, ``augmentation=``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..paths import DADOS_DIR

ARQUIVO = "consumiveis_s2.json"


@lru_cache(maxsize=1)
def _dados() -> dict:
    return json.loads((DADOS_DIR / ARQUIVO).read_text(encoding="utf-8"))


def _consumiveis() -> dict[str, list[dict]]:
    return _dados().get("consumiveis", {})


CONSUMIVEIS: dict[str, list[dict]] = _consumiveis()


def _fonte() -> str:
    origem = _dados().get("fonte")
    return f"{ARQUIVO} <- {origem}" if origem else ARQUIVO


FONTE = _fonte()


def opcoes(categoria: str) -> list[dict]:
    return list(CONSUMIVEIS.get(categoria, []))


def nome(categoria: str, token: str | None) -> str | None:
    if not token:
        return None
    for opcao in CONSUMIVEIS.get(categoria, []):
        if opcao.get("token") == token:
            return opcao.get("nome_pt") or opcao.get("nome_en")
    return None


def categorias() -> tuple[str, ...]:
    return tuple(CONSUMIVEIS)
