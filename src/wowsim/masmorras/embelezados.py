"""Quais slots do conjunto já gastam um dos 2 efeitos de embelezamento, e qual.

Motivação (P-052): o modo Craft precisa saber o que o personagem já usa para não
medir um terceiro embelezamento (o simc não impõe o limite de 2 — P-049) e para
oferecer "trocar o reagente X por Y" (P-050). Aqui cruzamos os ``bonus_ids`` do
item equipado com ``dados/derivados/embelezamentos.json`` (cada embelezamento tem
o seu ``bonus_id``) e marcamos também os que vêm embutidos no próprio item.

Nada é estimado: só reconhecemos o que o dado declara.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data import catalog, embellishments
from ..topgear.models import Conjunto
from .craft import Embelezamento, embelezamentos_com_bonus


@dataclass(frozen=True)
class EmbelezadoAtual:
    """Um slot que já possui embelezamento ativo."""

    slot: str
    item_id: int
    embutido: bool                    # vem do próprio item (não dá para trocar)
    aplicado: Embelezamento | None    # reagente aplicado (dá para trocar)


def _por_bonus() -> dict[int, Embelezamento]:
    return {
        emb.bonus_id: emb
        for emb in embelezamentos_com_bonus()
        if emb.bonus_id is not None
    }


def embelezados_do_conjunto(conjunto: Conjunto) -> list[EmbelezadoAtual]:
    """Slots equipados que já consomem embelezamento (embutido ou reagente)."""
    por_bonus = _por_bonus()
    saida: list[EmbelezadoAtual] = []
    for slot, candidato in conjunto.itens.items():
        if candidato.item_id is None:
            continue
        aplicado = next(
            (por_bonus[bonus] for bonus in (candidato.bonus_ids or []) if bonus in por_bonus),
            None,
        )
        embutido = embellishments.info(candidato.item_id).embutido
        if aplicado or embutido or candidato.embelezamento_simc or candidato.embelezamento:
            saida.append(
                EmbelezadoAtual(slot, candidato.item_id, embutido, aplicado)
            )
    return saida
