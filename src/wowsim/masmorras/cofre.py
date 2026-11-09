"""Grande Cofre: itens das opções do cofre a partir do ``.gv`` do AMR.

O ``.gv`` usa o mesmo formato de diferença acumulada do ``.inv`` (o codec em
``parser.amr_codec`` já decodifica). Sem um export real com o cofre cheio, os
testes usam tokens sintéticos; a validação ao vivo entra no T10.
"""

from __future__ import annotations

from ..data import catalog
from ..parser.amr import ImportAMR
from ..parser.amr_codec import decodificar_itens


def opcoes_do_cofre(importacao: ImportAMR) -> list[dict]:
    """Itens do Grande Cofre com slot e ilvl resolvidos pelo catálogo."""
    saida: list[dict] = []
    for it in decodificar_itens(importacao.gv):
        slots = catalog.slots_do_item(it.item_id)
        ilvl = next(
            (
                catalog.bonus_para_ilvl(b).ilvl
                for b in it.bonus_ids
                if catalog.bonus_para_ilvl(b).ilvl
            ),
            None,
        )
        saida.append(
            {
                "item_id": it.item_id,
                "slots": slots,
                "ilvl": ilvl,
                "bonus_ids": list(it.bonus_ids),
            }
        )
    return saida
