"""Droptimizer: ranking medido de itens (upgrade / best in bags / worst in bags)."""

from __future__ import annotations

from .models import (
    DropRankingItem,
    DropRequest,
    DropResult,
    ItemPossuido,
    ModoDrop,
    VereditoDrop,
)
from .pools import (
    agrupar_por_slot,
    candidato_de_possuido,
    deduplicar,
    ids_do_inv,
    itens_do_inv,
    possuidos_da_mochila,
)
from .search import executar_droptimizer

__all__ = [
    "DropRankingItem",
    "DropRequest",
    "DropResult",
    "ItemPossuido",
    "ModoDrop",
    "VereditoDrop",
    "agrupar_por_slot",
    "candidato_de_possuido",
    "deduplicar",
    "ids_do_inv",
    "itens_do_inv",
    "possuidos_da_mochila",
    "executar_droptimizer",
]
