"""Grande Cofre: itens das opções do cofre a partir do ``.gv`` do AMR.

O ``.gv`` usa o mesmo formato de diferença acumulada do ``.inv`` (o codec em
``parser.amr_codec`` já decodifica). Sem um export real com o cofre cheio, os
testes usam tokens sintéticos; a validação ao vivo entra no T10.
"""

from __future__ import annotations

from ..data import catalog
from ..parser.amr import ImportAMR
from ..parser.amr_codec import decodificar_itens
from ..topgear.catalisador import gemeo_catalisado
from ..topgear.models import Candidato, Conjunto
from .avaliar import Opcao
from .catalogo import ItemDeMasmorra

MASMORRA_COFRE = "Grande Cofre"


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


def montar_opcoes_cofre(
    base: Conjunto, importacao: ImportAMR, *, classe: str | None
) -> tuple[dict[str, Conjunto], dict[str, Opcao]]:
    """Converte as opções do cofre em conjuntos/candidatos com os bônus REAIS.

    Usa o mesmo ``avaliar`` do T6 (fonte="cofre"); anel/berloque são testados nos
    dois slots. Itens sem slot resolvido (placeholder do cofre) são ignorados.
    """
    conjuntos: dict[str, Conjunto] = {}
    opcoes: dict[str, Opcao] = {}
    for op in opcoes_do_cofre(importacao):
        item_id = op["item_id"]
        if not item_id or not op["slots"]:
            continue
        nomes = catalog.nome_item(item_id)
        for slot in op["slots"]:
            if base.item_id(slot) == item_id:
                continue
            cru = Candidato(
                slot=slot,
                item_id=item_id,
                bonus_ids=list(op["bonus_ids"]),
                ilvl=op["ilvl"],
                fonte="cofre",
                nome_pt=nomes.nome_pt,
                nome_en=nomes.nome_en,
            )
            variantes = [(cru, False)]
            gemeo = gemeo_catalisado(cru, classe)
            if gemeo is not None:
                variantes.append((gemeo, True))
            item_dm = ItemDeMasmorra(
                item_id=item_id,
                nome_pt=nomes.nome_pt,
                slot=slot,
                masmorra=MASMORRA_COFRE,
                secao="cofre",
                usavel_conjurador=None,
            )
            for candidato, catalisado in variantes:
                nome = f"{'k' if catalisado else 'c'}_{item_id}_{slot}"
                conjuntos[nome] = base.com_troca(slot, candidato)
                opcoes[nome] = Opcao(nome, item_dm, slot, catalisado)
    return conjuntos, opcoes
