"""Peças de tier set por classe (derivadas do ``item_data.inc`` do SimC).

Os dados vêm de ``dados/derivados/tier_sets.json``, gerado por
``scripts/derivar_tier_sets.py``. O SimC calcula o bônus de 2/4 peças sozinho a
partir do ``id_set`` do item equipado; este módulo só diz *qual* item_id é a
peça de tier de cada slot, para o Catalisador poder trocar uma peça comum por
ela. Nada aqui estima dano.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import DERIVADOS_DIR

SLOTS_TIER = ("head", "shoulder", "chest", "hands", "legs")
ARQUIVO = "tier_sets.json"


@dataclass(frozen=True)
class ConjuntoTier:
    """O conjunto de tier de uma classe: uma peça por slot de tier."""

    classe: str
    set_id: int
    slots: dict[str, tuple[int, ...]]
    nomes_en: dict[str, str]

    @property
    def ids(self) -> frozenset[int]:
        return frozenset(i for ids in self.slots.values() for i in ids)

    def item_do_slot(self, slot: str) -> int | None:
        ids = self.slots.get(slot)
        return ids[0] if ids else None


def normalizar_classe(classe: str | None) -> str:
    """``"Death Knight"`` / ``"death-knight"`` -> ``"death_knight"``."""
    return (classe or "").strip().lower().replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=4)
def _carregar(caminho: str) -> dict[str, ConjuntoTier]:
    try:
        bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    conjuntos: dict[str, ConjuntoTier] = {}
    for classe, info in (bruto.get("por_classe") or {}).items():
        try:
            conjuntos[classe] = ConjuntoTier(
                classe=classe,
                set_id=int(info["set_id"]),
                slots={
                    slot: tuple(int(i) for i in ids)
                    for slot, ids in info["slots"].items()
                    if slot in SLOTS_TIER
                },
                nomes_en=dict(info.get("nomes_en") or {}),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return conjuntos


def todos() -> dict[str, ConjuntoTier]:
    return _carregar(str(DERIVADOS_DIR / ARQUIVO))


def conjunto_da_classe(classe: str | None) -> ConjuntoTier | None:
    """Tier set da classe, ou ``None`` se o dado não existir (recurso desligado)."""
    return todos().get(normalizar_classe(classe))


def ids_tier(classe: str | None) -> frozenset[int]:
    conjunto = conjunto_da_classe(classe)
    return conjunto.ids if conjunto else frozenset()


def disponivel() -> bool:
    return bool(todos())
