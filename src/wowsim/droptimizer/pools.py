"""Candidatos do Droptimizer e fontes de itens possuídos.

Fase 4/5: candidatos vêm de uma lista explícita de itens possuídos. O `.inv` do
AMR entrega ids (slot resolvido depois); ``Gear from Bags`` do SimC já traz slot.
"""

from __future__ import annotations

from typing import Iterable

from ..data import catalog
from ..models import Personagem
from ..parser.amr_codec import decodificar_itens
from ..topgear.models import Candidato
from .models import ItemPossuido


def candidato_de_possuido(item: ItemPossuido) -> Candidato:
    return Candidato(
        slot=item.slot,
        item_id=item.item_id,
        bonus_ids=list(item.bonus_ids),
        enchant_id=item.enchant_id,
        gem_ids=list(item.gem_ids),
        ilvl=item.ilvl,
        fonte=f"possuido:{item.fonte}",
    )


def agrupar_por_slot(itens: Iterable[ItemPossuido]) -> dict[str, list[Candidato]]:
    """Agrupa possuídos por slot, do maior ilvl para o menor."""
    saida: dict[str, list[Candidato]] = {}
    for item in itens:
        saida.setdefault(item.slot, []).append(candidato_de_possuido(item))
    for candidatos in saida.values():
        candidatos.sort(key=lambda c: (-(c.ilvl or 0), c.item_id or 0))
    return saida


def deduplicar(itens: Iterable[ItemPossuido]) -> list[ItemPossuido]:
    """Remove duplicatas por slot/item/bônus, preservando a fonte mais forte."""
    vistos: set[tuple] = set()
    saida: list[ItemPossuido] = []
    for item in itens:
        chave = (item.slot, item.item_id, tuple(item.bonus_ids))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(item)
    return saida


def possuidos_da_mochila(personagem: Personagem) -> list[ItemPossuido]:
    """Itens de ``Gear from Bags`` do SimC (slot já conhecido)."""
    saida: list[ItemPossuido] = []
    for slot, itens in personagem.mochila.items():
        for item in itens:
            if item.item_id is None:
                continue
            saida.append(
                ItemPossuido(
                    slot=slot,
                    item_id=item.item_id,
                    ilvl=catalog.ilvl_do_item(item),
                    bonus_ids=list(item.bonus_ids),
                    enchant_id=item.enchant_id,
                    gem_ids=list(item.gem_ids),
                    fonte="bags_simc",
                )
            )
    return deduplicar(saida)


def ids_do_inv(importacao) -> list[int]:
    """Ids de item do ``.inv`` do AMR (já sem diferença acumulada)."""
    return sorted({it.item_id for it in decodificar_itens(importacao.inv) if it.item_id > 0})


def inv_ignorados(importacao) -> list[int]:
    """Ids do ``.inv`` cujo InventoryType não resolve para um slot de equipamento.

    São tokens de item sem slot conhecido (ex.: materiais, receitas); o merge não
    os transforma em possuídos equipáveis. Servem para o aviso ``amr_inv_ignorado``.
    """
    return sorted({
        it.item_id
        for it in decodificar_itens(importacao.inv)
        if it.item_id > 0 and not catalog.slots_do_item(it.item_id)
    })


def itens_do_inv(importacao) -> list[ItemPossuido]:
    """Converte o ``.inv`` em possuídos, resolvendo slot via InventoryType.

    O token traz ``b`` (bônus), ``e`` (encanto), ``x`` (gema) e ``n`` (tuning),
    todos já decodificados. Anéis/berloques/armas de uma mão geram uma entrada
    por slot possível.
    """
    saida: list[ItemPossuido] = []
    for it in decodificar_itens(importacao.inv):
        if it.item_id <= 0:
            continue
        slots = catalog.slots_do_item(it.item_id)
        if not slots:
            continue

        bonus_ids = list(it.bonus_ids)
        ilvl: int | None = None
        for bonus_id in bonus_ids:
            nivel = catalog.bonus_para_ilvl(bonus_id).ilvl
            if nivel:
                ilvl = nivel
                break

        gems = [g for g in it.gem_ids if g]
        for slot in slots:
            saida.append(
                ItemPossuido(
                    slot=slot,
                    item_id=it.item_id,
                    ilvl=ilvl,
                    bonus_ids=list(bonus_ids),
                    enchant_id=it.enchant_id or None,
                    gem_ids=list(gems),
                    fonte="inv_amr",
                )
            )
    return deduplicar(saida)
