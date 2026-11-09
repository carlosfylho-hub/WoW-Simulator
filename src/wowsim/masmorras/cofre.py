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
from ..topgear.runner import criar_simulador, estilo_de_luta
from ..topgear.search import conjunto_do_personagem
from .avaliar import MAX_REFINO, Opcao, avaliar, itens_para_refinar
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
                opcoes[nome] = Opcao(
                    nome, item_dm, slot, catalisado, ilvl=op["ilvl"]
                )
    return conjuntos, opcoes


def rodar_ranking_cofre(
    personagem,
    importacao: ImportAMR,
    *,
    cenario: str = "dungeon_slice",
    it_triagem: int = 300,
    it_refino: int = 3000,
    threads: int | None = None,
    cancelar=None,
    orcamento_restante=None,
    base_out: dict | None = None,
    max_refino: int = MAX_REFINO,
) -> list:
    """Como ``rodar_ranking`` (T6), mas para as opções do Grande Cofre (T8)."""
    base = conjunto_do_personagem(personagem)
    conjuntos, opcoes = montar_opcoes_cofre(
        base, importacao, classe=personagem.classe
    )
    simular = criar_simulador(
        personagem,
        fight_style=estilo_de_luta(cenario),
        threads=threads,
        cancelar=cancelar,
        orcamento_restante=orcamento_restante,
    )
    leitura = simular(conjuntos, it_triagem)
    if base_out is not None:
        base_out["base_dps"] = leitura.base_dps
    triagem = avaliar(leitura, opcoes)
    vivos = itens_para_refinar(triagem, max_refino)
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    refino = avaliar(
        simular({n: conjuntos[n] for n in nomes}, it_refino),
        {n: opcoes[n] for n in nomes},
    )
    refinados = {a.item.item_id for a in refino}
    return refino + [a for a in triagem if a.item.item_id not in refinados]
