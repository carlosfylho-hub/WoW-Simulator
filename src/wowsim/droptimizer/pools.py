"""Candidatos do Droptimizer e fontes de itens possuídos.

Fase 4/5: candidatos vêm de uma lista explícita de itens possuídos. O `.inv` do
AMR entrega ids (slot resolvido depois); ``Gear from Bags`` do SimC já traz slot.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..data import catalog
from ..models import Personagem
from ..topgear.models import Candidato
from .models import ItemPossuido

_ID_INV = re.compile(r"^(\d+)")


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


_CAMPO_INV = re.compile(r"([a-zA-Z])(-?\d+)")


def ids_do_inv(importacao) -> list[int]:
    """Ids de item do ``.inv`` do AMR (inventário/bolsas/cofre)."""
    ids: set[int] = set()
    for token in importacao.inv:
        casamento = _ID_INV.match(token.strip())
        if not casamento:
            continue
        item_id = int(casamento.group(1))
        if item_id > 0:
            ids.add(item_id)
    return sorted(ids)


def inv_ignorados(importacao) -> list[int]:
    """Ids do ``.inv`` cujo InventoryType não resolve para um slot de equipamento.

    São tokens de item sem slot conhecido (ex.: materiais, receitas); o merge não
    os transforma em possuídos equipáveis. Servem para o aviso ``amr_inv_ignorado``.
    """
    ignorados: list[int] = []
    for token in importacao.inv:
        casamento = _ID_INV.match(token.strip())
        if not casamento:
            continue
        item_id = int(casamento.group(1))
        if item_id <= 0:
            continue
        if not catalog.slots_do_item(item_id):
            ignorados.append(item_id)
    return sorted(set(ignorados))


def itens_do_inv(importacao) -> list[ItemPossuido]:
    """Converte o ``.inv`` em possuídos, resolvendo slot via InventoryType.

    O token traz ``b`` (bônus), ``e`` (encanto), ``x`` (gema) e ``n`` (tuning).
    Anéis/berloques/armas de uma mão geram uma entrada por slot possível.
    """
    saida: list[ItemPossuido] = []
    for token in importacao.inv:
        token = token.strip()
        casamento = _ID_INV.match(token)
        if not casamento:
            continue
        item_id = int(casamento.group(1))
        if item_id <= 0:
            continue
        slots = catalog.slots_do_item(item_id)
        if not slots:
            continue

        bonus_ids: list[int] = []
        gems: list[int] = []
        enchant: int | None = None
        for campo in _CAMPO_INV.finditer(token):
            tag = campo.group(1)
            valor = int(campo.group(2))
            if tag == "b" and valor > 0:
                bonus_ids.append(valor)
            elif tag == "e":
                enchant = valor
            elif tag == "x" and valor > 0:
                gems.append(valor)

        ilvl: int | None = None
        for bonus_id in bonus_ids:
            nivel = catalog.bonus_para_ilvl(bonus_id).ilvl
            if nivel:
                ilvl = nivel
                break

        for slot in slots:
            saida.append(
                ItemPossuido(
                    slot=slot,
                    item_id=item_id,
                    ilvl=ilvl,
                    bonus_ids=list(bonus_ids),
                    enchant_id=enchant,
                    gem_ids=list(gems),
                    fonte="inv_amr",
                )
            )
    return deduplicar(saida)
