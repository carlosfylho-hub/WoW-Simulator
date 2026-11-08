"""Curated secondary-stat weights used by the heuristic pruner.

These weights are a *ranking* aid, never DPS. They live in
``dados/pesos_secundarios.json`` with provenance. Lookup order: spec, then class,
then the generic default. Unknown specs fall back gracefully so pruning always
works, even before measured weights exist (those arrive in a later phase).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import DADOS_DIR

ARQUIVO = "pesos_secundarios.json"


@dataclass(frozen=True)
class PesosSpec:
    """Resolved weights for one character plus where they came from."""

    valores: dict[str, float]
    fonte: str
    classe: str | None = None
    spec: str | None = None
    conhecido: bool = False


def _slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())


@lru_cache(maxsize=4)
def _json(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def limpar_cache() -> None:
    _json.cache_clear()


def carregar() -> dict:
    """Raw table (kept for inspection/tests)."""
    return _json(str(DADOS_DIR / ARQUIVO))


def _como_pesos(valores: object) -> dict[str, float]:
    if not isinstance(valores, dict):
        return {}
    saida: dict[str, float] = {}
    for chave, valor in valores.items():
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            saida[str(chave)] = float(valor)
    return saida


def pesos_para(classe: str | None = None, spec: str | None = None) -> PesosSpec:
    """Resolve weights: spec first, then class, then the generic default."""
    dados = carregar()
    fonte_base = str(dados.get("fonte") or ARQUIVO)
    por_spec = dados.get("por_spec") or {}
    por_classe = dados.get("por_classe") or {}

    if spec:
        chave = _slug(spec)
        if chave in por_spec:
            return PesosSpec(
                _como_pesos(por_spec[chave]),
                f"{fonte_base}:spec:{chave}",
                classe,
                spec,
                True,
            )

    if classe:
        chave = _slug(classe)
        if chave in por_classe:
            return PesosSpec(
                _como_pesos(por_classe[chave]),
                f"{fonte_base}:classe:{chave}",
                classe,
                spec,
                True,
            )

    padrao = _como_pesos(dados.get("padrao"))
    return PesosSpec(padrao, f"{fonte_base}:padrao", classe, spec, False)
