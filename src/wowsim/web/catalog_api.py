"""Expose the Python catalog as JSON so the React UI can use it as source of truth.

The Python catalog (`wow-sim/dados` + derivados) is authoritative. This module
flattens M+ loot, the upgrade-monitor trinkets and caster trinkets into a single
list with PT/EN names, ilvl, slot, provenance and the upgrade ``bonus_id``.
"""

from __future__ import annotations

from ..data import catalog
from ..models import ItemLoot


def _nome_pt(loot: ItemLoot) -> str | None:
    if loot.nome_pt:
        return loot.nome_pt
    return catalog.nome_item(loot.item_id).nome_pt


def _nome_en(loot: ItemLoot) -> str | None:
    if loot.nome_en:
        return loot.nome_en
    return catalog.nome_item(loot.item_id).nome_en


def _serializar(loot: ItemLoot, alvo: bool) -> dict:
    return {
        "id": loot.item_id,
        "nome_pt": _nome_pt(loot),
        "nome_en": _nome_en(loot),
        "slot": loot.slot,
        "ilvl": loot.ilvl,
        "origem": loot.origem,
        "fonte": loot.fonte,
        "bonus_id": loot.bonus_id,
        "peconha": loot.peconha,
        "alvo": alvo,
    }


def itens_catalogo() -> list[dict]:
    """All catalog items, de-duplicated by (id, ilvl, bonus)."""
    vistos: set[tuple] = set()
    saida: list[dict] = []

    def adicionar(loot: ItemLoot, alvo: bool) -> None:
        chave = (loot.item_id, loot.ilvl, loot.bonus_id)
        if chave in vistos:
            return
        vistos.add(chave)
        saida.append(_serializar(loot, alvo))

    for slot in catalog.ALIASES_SLOT:
        for loot in catalog.itens_mplus(slot):
            adicionar(loot, loot.ilvl in catalog.ILVLS_ALVO)

    for nivel in catalog.ILVLS_ALVO:
        for loot in catalog.berloques_monitor(nivel):
            adicionar(loot, True)

    for loot in catalog.berloques_conjurador():
        adicionar(loot, loot.ilvl in catalog.ILVLS_ALVO)

    saida.sort(key=lambda d: (d["slot"] or "", d["id"], d["ilvl"] or 0))
    return saida
