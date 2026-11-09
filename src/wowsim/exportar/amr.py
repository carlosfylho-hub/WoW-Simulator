"""String de importação do AMR (Best in Bags) com o conjunto medido.

O cabeçalho (identidade, spec, talentos, árvore, ``.qN``) é copiado de uma
string que o próprio AMR gerou para o personagem; aqui só se trocam os itens e o
bloco de extras (``linha_importacao`` do codec, já validada). Nada é estimado.
"""

from __future__ import annotations

from ..parser.amr import SLOTS_AMR
from ..parser.amr_codec import ItemAmr, linha_importacao
from ..topgear.models import Conjunto

# Inverso de SLOTS_AMR: nome interno -> número do slot do AMR (1..17).
_SLOT_PARA_AMR = {nome: numero for numero, nome in SLOTS_AMR.items()}

__all__ = ["ItemAmr", "linha_importacao", "itens_de_conjunto"]


def itens_de_conjunto(conjunto: Conjunto) -> list[ItemAmr]:
    """Converte um :class:`Conjunto` em itens do AMR (bônus, gemas e encanto).

    ``gem_ids`` é completado até 3 com ``0``; o Catalisador vira
    ``catalyst_source`` (``redirected_base_stats`` no simc).
    """
    itens: list[ItemAmr] = []
    for slot, cand in conjunto.itens.items():
        if cand.item_id is None:
            continue
        numero = _SLOT_PARA_AMR.get(slot)
        if numero is None:
            continue
        gems = list(cand.gem_ids)
        while len(gems) < 3:
            gems.append(0)
        bonus = list(cand.bonus_ids or ([cand.bonus_id] if cand.bonus_id else []))
        itens.append(
            ItemAmr(
                item_id=cand.item_id,
                slot=numero,
                bonus_ids=bonus,
                gem_ids=gems[:3],
                enchant_id=cand.enchant_id or 0,
                catalyst_source=cand.redirected_base_stats or 0,
            )
        )
    return itens
