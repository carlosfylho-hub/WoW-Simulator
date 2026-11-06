"""Resolve SimC enchant ids and classify their layer.

enchant_id is a SpellItemEnchantment row, one per quality. It is not an item id.
Gloves can carry a Hash'ey Battle Art and legs carry a spellthread; both are
different layers and must not be treated as a regular enchantment.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..models import EncantamentoResolvido
from ..paths import DADOS_DIR

PREFIXOS_SLOT = {
    "enchant chest": "peitoral",
    "enchant helm": "cabeça",
    "enchant shoulders": "ombros",
    "enchant shoulder": "ombros",
    "enchant boots": "pés",
    "enchant ring": "anel",
    "enchant weapon": "arma",
    "enchant bracer": "pulsos",
    "enchant gloves": "mãos",
    "enchant cloak": "capa",
    "enchant off-hand": "mão secundária",
    "enchant shield": "escudo",
    "enchant tool": "ferramenta",
    "enchant fishing": "ferramenta",
}

ESPECIAIS: dict[int, dict] = {
    7934: {
        "nome_en": "Spellthread - Intellect and Stamina (Tier 1)",
        "camada": "magilinha",
        "slot": "pernas",
        "tier": 1,
        "spell_id": 1229449,
        "fonte": "dados_enchant_ids.csv",
    },
    7935: {
        "nome_en": "Spellthread - Intellect and Stamina (Tier 2)",
        "camada": "magilinha",
        "slot": "pernas",
        "tier": 2,
        "spell_id": 1229450,
        "fonte": "dados_enchant_ids.csv",
    },
    8730: {
        "nome_en": "Ancient Hash'ey Battle Art: Eye of the Lynx",
        "camada": "arte_de_batalha",
        "slot": "mãos",
        "tier": 4,
        "spell_id": 1315099,
        "fonte": "dados_enchant_ids.csv",
    },
    8702: {
        "nome_en": "R0CKY",
        "camada": "tinker",
        "slot": "cabeça",
        "tier": None,
        "spell_id": None,
        "item_id": 275676,
        "fonte": "pendencias.md",
    },
}


@lru_cache(maxsize=4)
def _mapa(caminho: str) -> dict[str, dict]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return dados.get("enchants", {})


def _mapa_atual() -> dict[str, dict]:
    return _mapa(str(DADOS_DIR / "enchant_ids_s2.json"))


def limpar_cache() -> None:
    _mapa.cache_clear()


def _slot_por_nome(nome_en: str | None) -> str | None:
    if not nome_en:
        return None
    minusculo = nome_en.lower()
    for prefixo, slot in PREFIXOS_SLOT.items():
        if minusculo.startswith(prefixo):
            return slot
    return None


def _camada(enchant_id: int, nome_en: str | None) -> str:
    if enchant_id in ESPECIAIS:
        return ESPECIAIS[enchant_id]["camada"]
    if 8051 <= enchant_id <= 8056 or enchant_id in {8612, 8613}:
        return "oleo_temporario"
    if nome_en and "tool" in nome_en.lower():
        return "ferramenta"
    return "encantamento"


def resolver(enchant_id: int | None) -> EncantamentoResolvido | None:
    """Resolve an enchant id to name, layer and slot. Never guesses an unknown id."""
    if enchant_id is None:
        return None

    if enchant_id in ESPECIAIS:
        especial = ESPECIAIS[enchant_id]
        return EncantamentoResolvido(
            enchant_id=enchant_id,
            nome_pt=None,
            nome_en=especial.get("nome_en"),
            camada=especial["camada"],
            slot=especial.get("slot"),
            tier=especial.get("tier"),
            item_id=especial.get("item_id"),
            spell_id=especial.get("spell_id"),
            fonte=especial["fonte"],
        )

    entrada = _mapa_atual().get(str(enchant_id))
    if entrada is None:
        if 8051 <= enchant_id <= 8056 or enchant_id in {8612, 8613}:
            return EncantamentoResolvido(
                enchant_id=enchant_id,
                camada="oleo_temporario",
                slot="arma",
                fonte="faixa de enchant_id temporario",
            )
        return None

    nome_en = entrada.get("nome_en") or entrada.get("nome_db2")
    return EncantamentoResolvido(
        enchant_id=enchant_id,
        nome_pt=entrada.get("nome_pt"),
        nome_en=nome_en,
        camada=_camada(enchant_id, nome_en),
        slot=_slot_por_nome(nome_en),
        tier=entrada.get("tier"),
        item_id=entrada.get("item_id"),
        spell_id=entrada.get("spell_id"),
        fonte="enchant_ids_s2.json",
    )


def encantamentos_por_slot(slot: str) -> list[EncantamentoResolvido]:
    """All known enchants for a slot, including special layers."""
    alvo = slot.strip().lower()
    saida: list[EncantamentoResolvido] = []
    for chave in _mapa_atual():
        resolvido = resolver(int(chave))
        if resolvido is not None and (resolvido.slot or "").lower() == alvo:
            saida.append(resolvido)
    for enchant_id in ESPECIAIS:
        resolvido = resolver(enchant_id)
        if resolvido is not None and (resolvido.slot or "").lower() == alvo:
            saida.append(resolvido)
    saida.sort(key=lambda item: (item.nome_en or "", item.tier or 0))
    return saida
