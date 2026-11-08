"""Candidate pools per slot for the Top Gear search.

Every candidate carries its provenance (``fonte``) and the upgrade ``bonus_id``
that matches the requested item level. Eligibility filters here are meant to be
conservative: when the catalog does not say the primary attribute, the item is
kept and the validator/simulation decides.
"""

from __future__ import annotations

import itertools
from typing import Iterable, Sequence

from ..data import catalog, consumables, embellishments
from ..models import Personagem
from .models import Candidato, ContextoSpec, TipoArma

NIVEL_PARA_BONUS = {341: 12856, 334: 12854, 328: 12848, 321: 12846}
SECOES_ARMADURA = {
    "tecido": "armadura_tecido_mplus",
    "couro": "armadura_couro_mplus",
    "malha": "armadura_malha_mplus",
    "placa": "armadura_placa_mplus",
}
SLOTS_ARMADURA = (
    "head",
    "shoulder",
    "chest",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
)
ORDEM_SLOTS = SLOTS_ARMADURA + (
    "neck",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
)

SLOT_ENCHANT_PT = {
    "head": "cabeça",
    "shoulder": "ombros",
    "chest": "peitoral",
    "feet": "pés",
    "legs": "pernas",
    "hands": "mãos",
    "wrist": "pulsos",
    "back": "capa",
    "main_hand": "arma",
    "off_hand": "mão secundária",
    "finger": "anel",
}


def _nomes(item_id: int) -> tuple[str | None, str | None]:
    nomes = catalog.nome_item(item_id)
    return nomes.nome_pt, nomes.nome_en


def _tipo_arma(valor: str | None) -> TipoArma:
    if valor == "1h":
        return "1h"
    if valor == "2h":
        return "2h"
    return "desconhecido"


def _candidato(
    slot: str,
    loot,
    nivel: int,
    *,
    tipo_arma: TipoArma = "desconhecido",
    tipo_efeito: str | None = None,
    tipo_armadura: str | None = None,
) -> Candidato:
    nome_pt, nome_en = _nomes(loot.item_id)
    # Embellishment comes from the crafting catalog, never from ``peconha``:
    # a venom-forged drop is not an embellished craft.
    embelezado = embellishments.info(loot.item_id).embutido
    return Candidato(
        slot=slot,
        item_id=loot.item_id,
        bonus_id=NIVEL_PARA_BONUS[nivel],
        bonus_ids=[NIVEL_PARA_BONUS[nivel]],
        ilvl=nivel,
        fonte=loot.fonte,
        nome_pt=loot.nome_pt or nome_pt,
        nome_en=loot.nome_en or nome_en,
        tipo=loot.tipo,
        tipo_arma=_tipo_arma(tipo_arma),
        tipo_armadura=tipo_armadura,
        tipo_efeito=tipo_efeito or loot.tipo_efeito,
        embelezamento=embelezado,
    )


def _atributo_compativel(atributos: Iterable[str], alvo: str | None) -> bool:
    """Keep items with unknown attributes; only reject a known mismatch."""
    if not alvo:
        return True
    texto = " ".join(atributos).lower()
    if not texto.strip():
        return True
    return alvo.lower() in texto


def _chave(candidato: Candidato) -> tuple[int | None, int | None, int | None]:
    return (candidato.item_id, candidato.ilvl, candidato.bonus_id)


def _add(pools: dict[str, dict[tuple, Candidato]], slot: str, candidato: Candidato) -> None:
    pools.setdefault(slot, {})
    pools[slot].setdefault(_chave(candidato), candidato)


def construir_pools(
    *,
    tipo_armadura: str = "tecido",
    atributo: str = "Intelecto",
    niveis: Sequence[int] = catalog.ILVLS_ALVO,
    pool_por_slot: int | None = None,
) -> dict[str, list[Candidato]]:
    """Build ``slot -> candidates`` for items (enchant/gem/talent are separate).

    Deterministic ordering: highest item level first, then item id. When
    ``pool_por_slot`` is set the list is trimmed to the top K.
    """
    brutos: dict[str, dict[tuple, Candidato]] = {}

    secao = SECOES_ARMADURA.get(tipo_armadura)
    if secao:
        for loot in catalog.itens_da_secao(secao):
            if loot.slot not in SLOTS_ARMADURA:
                continue
            # Keep attribute-compatible pieces when the source exposes it
            # (scraped armor carries ``atributos``); unknown attributes pass.
            if not _atributo_compativel(loot.atributos, atributo):
                continue
            for nivel in niveis:
                _add(
                    brutos,
                    loot.slot,
                    _candidato(
                        loot.slot, loot, nivel, tipo_armadura=tipo_armadura
                    ),
                )

    caster_trinkets = {
        loot.item_id: loot.tipo_efeito for loot in catalog.berloques_conjurador()
    }
    for nivel in niveis:
        for loot in catalog.itens_monitor(nivel):
            if loot.slot == "trinket":
                if loot.item_id not in caster_trinkets:
                    continue
                for slot in ("trinket1", "trinket2"):
                    _add(
                        brutos,
                        slot,
                        _candidato(
                            slot,
                            loot,
                            nivel,
                            tipo_efeito=caster_trinkets.get(loot.item_id),
                        ),
                    )
                continue

            if not _atributo_compativel(loot.atributos, atributo):
                continue
            if loot.slot in ("main_hand", "off_hand", "neck"):
                _add(
                    brutos,
                    loot.slot,
                    _candidato(
                        loot.slot, loot, nivel, tipo_arma=_tipo_arma(loot.tipo)
                    ),
                )

    for loot in catalog.itens_mplus("finger"):
        if loot.slot != "finger":
            continue
        primario = catalog.atributo_primario(loot.item_id)
        if primario and primario != atributo:
            continue
        for nivel in niveis:
            for slot in ("finger1", "finger2"):
                _add(brutos, slot, _candidato(slot, loot, nivel))

    for loot in catalog.itens_mplus("neck"):
        if loot.slot != "neck":
            continue
        primario = catalog.atributo_primario(loot.item_id)
        if primario and primario != atributo:
            continue
        for nivel in niveis:
            _add(brutos, "neck", _candidato("neck", loot, nivel))

    for loot in catalog.itens_mplus("off_hand"):
        if loot.slot != "off_hand":
            continue
        primario = catalog.atributo_primario(loot.item_id)
        if primario and primario != atributo:
            continue
        for nivel in niveis:
            _add(brutos, "off_hand", _candidato("off_hand", loot, nivel))

    pools: dict[str, list[Candidato]] = {}
    for slot in ORDEM_SLOTS:
        candidatos = list(brutos.get(slot, {}).values())
        if not candidatos:
            continue
        candidatos.sort(key=lambda c: (-(c.ilvl or 0), c.item_id or 0))
        if pool_por_slot is not None:
            candidatos = candidatos[:pool_por_slot]
        pools[slot] = candidatos
    return pools


def resumo(pools: dict[str, list[Candidato]]) -> dict[str, int]:
    """Candidate count per slot, for logs and the pools preview endpoint."""
    return {slot: len(lista) for slot, lista in pools.items()}


def secoes_ausentes(tipo_armadura: str) -> list[str]:
    """Warn when an armor section is missing so empty pools are never silent.

    The M+ snapshot currently only ships cloth/leather sections; mail/plate
    classes would otherwise get empty armor pools with no explanation.
    """
    secao = SECOES_ARMADURA.get(tipo_armadura)
    if secao is None:
        return [f"Sem seção de armadura mapeada para '{tipo_armadura}'."]
    if not catalog.itens_da_secao(secao):
        return [
            f"Seção '{secao}' vazia/ausente: pools de armadura para "
            f"'{tipo_armadura}' ficarão vazias até incluir o loot M+."
        ]
    return []


def encantos_por_slot() -> dict[str, list[Candidato]]:
    """Enchant candidates per equipment slot, keeping the layer in ``tipo``."""
    saida: dict[str, list[Candidato]] = {}
    for slot, slot_pt in SLOT_ENCHANT_PT.items():
        vistos: set[tuple[int | None, str | None]] = set()
        lista: list[Candidato] = []
        for encantamento in catalog.encantamentos_por_slot(slot_pt):
            chave = (encantamento.enchant_id, encantamento.camada)
            if chave in vistos:
                continue
            vistos.add(chave)
            lista.append(
                Candidato(
                    slot=slot,
                    enchant_id=encantamento.enchant_id,
                    fonte=encantamento.fonte,
                    nome_pt=encantamento.nome_pt,
                    nome_en=encantamento.nome_en,
                    tipo=encantamento.camada,
                    valor=str(encantamento.tier) if encantamento.tier else None,
                )
            )
        if lista:
            saida[slot] = lista
    return saida


def gemas_catalogo() -> list[Candidato]:
    """All known gems as candidates; ``tipo`` carries the gem family."""
    return [
        Candidato(
            slot="gema",
            item_id=gema.item_id,
            fonte=gema.fonte,
            nome_pt=gema.nome_pt,
            nome_en=gema.nome_en,
            tipo=gema.tipo,
        )
        for gema in catalog.gemas()
    ]


def diamantes() -> set[int]:
    """Eversong (prismatic) diamond gem ids, used by the constraint validator."""
    return {
        gema.item_id
        for gema in catalog.gemas()
        if gema.tipo and "diamante" in gema.tipo.lower()
    }


def talentos_disponiveis(
    personagem: Personagem, extras: Iterable[str] | None = None
) -> list[Candidato]:
    """Current build + saved loadouts + extra import strings supplied by the UI."""
    saida: list[Candidato] = []
    vistos: set[str] = set()
    if personagem.talents_atual:
        vistos.add(personagem.talents_atual)
        saida.append(
            Candidato(
                slot="talentos",
                fonte="personagem.talents_atual",
                nome_pt="build atual",
                tipo="loadout",
                valor=personagem.talents_atual,
            )
        )
    for nome, codigo in personagem.loadouts.items():
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        saida.append(
            Candidato(
                slot="talentos",
                fonte="personagem.loadouts",
                nome_pt=nome,
                tipo="loadout",
                valor=codigo,
            )
        )
    for indice, codigo in enumerate(extras or (), start=1):
        codigo = (codigo or "").strip()
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        saida.append(
            Candidato(
                slot="talentos",
                fonte="request.talentos_extra",
                nome_pt=f"build extra {indice}",
                tipo="loadout",
                valor=codigo,
            )
        )
    return saida


def consumiveis() -> dict[str, list[Candidato]]:
    """Flask/potion/food/augment options as candidates for the consumable stage."""
    saida: dict[str, list[Candidato]] = {}
    for categoria, opcoes in consumables.CONSUMIVEIS.items():
        saida[categoria] = [
            Candidato(
                slot=categoria,
                item_id=opcao.get("item_id"),
                fonte=consumables.FONTE,
                nome_pt=opcao.get("nome_pt"),
                nome_en=opcao.get("nome_en"),
                tipo=categoria,
                valor=opcao.get("token"),
            )
            for opcao in opcoes
        ]
    return saida


def combinacoes_folio() -> list[list[str]]:
    """Cartesian product of the runes: one per line, 72 combinations today."""
    por_linha: dict[str, list[str]] = {}
    for runa in catalog.runas_folio():
        if runa.linha <= 0 or not runa.escolha:
            continue
        por_linha.setdefault(str(runa.linha), []).append(runa.escolha)

    linhas = sorted(por_linha)
    if not linhas:
        return []
    return [list(combo) for combo in itertools.product(*(por_linha[linha] for linha in linhas))]


def construir_contexto(
    *,
    classe: str | None = None,
    spec: str | None = None,
    tipo_armadura: str | None = None,
    tipo_arma: str = "desconhecido",
    embelezamentos: Iterable[int] | None = None,
    trinkets_on_use: Iterable[int] | None = None,
    tier_ids: Iterable[int] | None = None,
    offs_validos: Iterable[int] | None = None,
) -> ContextoSpec:
    """Build the constraint context from the catalog indexes."""
    conjunto_emb = set(embelezamentos or ())
    # Only crafted items with the embellishment built in count toward the cap.
    conjunto_emb.update(
        registro["item_id"]
        for registro in embellishments.listar_craftados()
        if registro.get("embutido") and registro.get("item_id") is not None
    )

    on_use = set(trinkets_on_use or ())
    on_use.update(
        loot.item_id
        for loot in catalog.berloques_conjurador()
        if loot.tipo_efeito == "ativo"
    )

    offs = set(offs_validos or ())
    offs.update(loot.item_id for loot in catalog.itens_mplus("off_hand"))
    offs.update(
        loot.item_id for loot in catalog.itens_monitor(341) if loot.slot == "off_hand"
    )

    return ContextoSpec(
        classe=classe,
        spec=spec,
        tipo_arma=tipo_arma,  # type: ignore[arg-type]
        tipo_armadura=tipo_armadura,
        embelezamentos=conjunto_emb,
        diamantes=diamantes(),
        trinkets_on_use=on_use,
        tier_ids=set(tier_ids or ()),
        offs_validos=offs,
    )
