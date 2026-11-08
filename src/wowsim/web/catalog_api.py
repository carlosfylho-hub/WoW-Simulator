"""Expose the Python catalog as JSON so the React UI can use it as source of truth.

The Python catalog (`wow-sim/dados` + derivados) is authoritative. This module
flattens M+ loot, the upgrade-monitor trinkets and caster trinkets into a single
list with PT/EN names, ilvl, slot, provenance and the upgrade ``bonus_id``.
"""

from __future__ import annotations

from ..data import catalog, embellishments, icons
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
    embeleza = embellishments.info(loot.item_id)
    return {
        "id": loot.item_id,
        "nome_pt": _nome_pt(loot),
        "nome_en": _nome_en(loot),
        "slot": loot.slot,
        "icon": icons.icone(loot.item_id),
        "ilvl": loot.ilvl,
        "origem": loot.origem,
        "fonte": loot.fonte,
        "bonus_id": loot.bonus_id,
        "peconha": loot.peconha,
        "alvo": alvo,
        "craftado": embeleza.craftado,
        "embellished": embeleza.embutido,
        "embelezado_embutido": embeleza.embutido,
        "aceita_embelezamento": embeleza.aceita,
        "embelezamento_recomendado": embeleza.recomendado,
        "limite_embelezamentos": embeleza.limite,
    }


def mapa_icones() -> dict[str, str]:
    """Complete id -> texture slug map, including raid/tier items."""
    return {str(item_id): slug for item_id, slug in sorted(icons.listar().items())}


def itens_catalogo() -> list[dict]:
    """All catalog items, de-duplicated by (id, ilvl, bonus)."""
    vistos: set[tuple] = set()
    ids_vistos: set[int] = set()
    saida: list[dict] = []

    def adicionar(loot: ItemLoot, alvo: bool) -> None:
        chave = (loot.item_id, loot.ilvl, loot.bonus_id)
        ids_vistos.add(loot.item_id)
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

    # Craftable items are not in the M+ database but carry embellishment info
    # that the tooltip must show. Add them once, only if not already present.
    for craft in embellishments.listar_craftados():
        item_id = craft["item_id"]
        if item_id in ids_vistos:
            continue
        embeleza = embellishments.info(item_id)
        ids_vistos.add(item_id)
        saida.append(
            {
                "id": item_id,
                "nome_pt": embeleza.nome_pt,
                "nome_en": embeleza.nome_en,
                "slot": catalog.normalizar_slot(craft.get("slot")),
                "icon": icons.icone(item_id),
                "ilvl": 331,
                "origem": "craft",
                "fonte": craft.get("fonte") or "craft_receitas_s2.json",
                "bonus_id": None,
                "peconha": None,
                "alvo": False,
                "craftado": embeleza.craftado,
                "embellished": embeleza.embutido,
                "embelezado_embutido": embeleza.embutido,
                "aceita_embelezamento": embeleza.aceita,
                "embelezamento_recomendado": embeleza.recomendado,
                "limite_embelezamentos": embeleza.limite,
            }
        )

    # Fallback: items known by the official stats snapshot (delve/world drops)
    # still deserve a name and icon in the UI. Only declared data is used.
    for chave, registro in catalog.itens_stats_index().items():
        try:
            item_id = int(chave)
        except (TypeError, ValueError):
            continue
        if item_id in ids_vistos or not isinstance(registro, dict):
            continue
        nome_pt = registro.get("nome_pt")
        nome_en = registro.get("nome_en")
        if not (nome_pt or nome_en):
            continue
        # Only include items that have a trustworthy icon; never break the
        # "every catalog item has an icon" invariant.
        icone = icons.icone(item_id)
        if not icone:
            continue
        slots = catalog.slots_do_item(item_id)
        ids_vistos.add(item_id)
        saida.append(
            {
                "id": item_id,
                "nome_pt": nome_pt,
                "nome_en": nome_en,
                "slot": slots[0] if slots else None,
                "icon": icone,
                "ilvl": None,
                "origem": "stats",
                "fonte": "stats_oficiais_itens.json",
                "bonus_id": None,
                "peconha": None,
                "alvo": False,
                "craftado": False,
                "embellished": False,
                "embelezado_embutido": False,
                "aceita_embelezamento": False,
                "embelezamento_recomendado": None,
                "limite_embelezamentos": None,
            }
        )

    saida.sort(key=lambda d: (d["slot"] or "", d["id"], d["ilvl"] or 0))
    return saida
