"""Catálogo de itens de M+ por masmorra e elegibilidade por classe.

O catálogo original descartava a masmorra (guardava o slot em ``origem``). Os
berloques ficam em subseções nomeadas pela masmorra e não têm ``dungeon_pt``;
``MASMORRA_DA_SUBSECAO`` resolve esses casos. As subseções foram conferidas em
``dados/mplus_loot_database.json``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data import catalog

# Os berloques ficam em subseções nomeadas pela masmorra, sem campo dungeon_pt.
# Chave da subseção -> nome PT-BR usado nos demais itens (conferido em dados/).
MASMORRA_DA_SUBSECAO = {
    "altar_das_presas": "Altar das Presas",
    "murder_row": "Murder Row",
    "o_vale_ofuscante": "O Vale Ofuscante",
    "arena_rasgada_pelo_vazio": "Arena da Chaga do Caos",
    "covil_de_nalorakk": "Covil de Nalorakk",
    "piscinas_da_vida_rubi": "Piscinas da Vida Rubi",
    "templo_de_sethraliss": "Templo de Sethraliss",
    "descanso_do_rei": "Descanso do Rei",
}
SECAO_ARMADURA = {"tecido": "armadura_tecido_mplus", "couro": "armadura_couro_mplus"}


@dataclass(frozen=True)
class ItemDeMasmorra:
    item_id: int
    nome_pt: str | None
    slot: str
    masmorra: str
    secao: str
    usavel_conjurador: bool | None


def itens_por_masmorra() -> list[ItemDeMasmorra]:
    saida: list[ItemDeMasmorra] = []
    vistos: set[tuple[int, str]] = set()
    for secao, sub, item in catalog._flatten_mplus():
        masmorra = item.get("dungeon_pt") or MASMORRA_DA_SUBSECAO.get(sub)
        if not masmorra:
            continue  # sem masmorra conhecida (ex.: Delve): fora deste ranking
        slot = catalog.normalizar_slot(item.get("slot") or sub)
        if secao == "trinkets_mplus":
            slot = "trinket"
        chave = (int(item["item_id"]), masmorra)
        if chave in vistos or not slot:
            continue
        vistos.add(chave)
        saida.append(
            ItemDeMasmorra(
                int(item["item_id"]),
                item.get("nome_pt"),
                slot,
                masmorra,
                secao,
                item.get("usavel_por_conjurador"),
            )
        )
    return saida


def elegivel(item: ItemDeMasmorra, *, tipo_armadura: str, atributo: str) -> bool:
    """O jogo filtra o loot pela spec; desconhecido = mantém (decide o simc)."""
    if item.secao.startswith("armadura_") and item.secao != SECAO_ARMADURA.get(tipo_armadura):
        return False
    if item.slot == "trinket":
        return item.usavel_conjurador is not False if atributo == "Intelecto" else True
    primario = catalog.atributo_primario(item.item_id)
    return primario is None or primario == atributo
