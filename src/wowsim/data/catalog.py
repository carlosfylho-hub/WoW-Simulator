"""Catalog access with mandatory provenance.

Every function returns a model carrying `fonte` with the file it came from.
Missing data becomes None, never an estimate.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from ..models import Gema, IlvlBonus, ItemLoot, NomeItem, Runa
from ..paths import DADOS_DIR, DERIVADOS_DIR, SIMC_SRC_DIR
from .enchants import encantamentos_por_slot as _encantamentos_por_slot

ITEM_DATA = SIMC_SRC_DIR / "engine" / "dbc" / "generated" / "item_data.inc"
_ITEM_RE = re.compile(r'\{\s*"([^"]+)",\s*(\d+)')

ALIASES_SLOT: dict[str, tuple[str, ...]] = {
    "off_hand": ("offhand", "maosecundaria", "escudo", "lanterna", "maosecund"),
    "main_hand": ("mainhand", "arma", "weapon", "cajado", "adaga", "espada", "machado"),
    "head": ("head", "helm", "cabeca", "elmo"),
    "neck": ("neck", "pescoco", "colar"),
    "shoulder": ("shoulder", "ombro", "omoplata"),
    "back": ("back", "cloak", "capa", "costas", "manto"),
    "chest": ("chest", "torso", "peitoral", "vestes"),
    "wrist": ("wrist", "pulso", "bracelete"),
    "hands": ("hands", "glove", "luva", "maos"),
    "waist": ("waist", "belt", "cinto", "cintura"),
    "legs": ("legs", "perna", "calca"),
    "feet": ("feet", "boot", "bota", "pes"),
    "finger": ("finger", "ring", "anel", "dedo"),
    "trinket": ("trinket", "berloque"),
}


@lru_cache(maxsize=16)
def _json(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def _dados(nome: str) -> dict:
    return _json(str(DADOS_DIR / nome))


def _derivado(nome: str) -> dict:
    return _json(str(DERIVADOS_DIR / nome))


@lru_cache(maxsize=2)
def _item_data(caminho: str, mtime: float) -> dict[int, str]:
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    return {int(item_id): nome for nome, item_id in _ITEM_RE.findall(texto)}


def _indice_itens() -> dict[int, str]:
    if not ITEM_DATA.is_file():
        return {}
    return _item_data(str(ITEM_DATA), ITEM_DATA.stat().st_mtime)


def limpar_cache() -> None:
    _json.cache_clear()
    _item_data.cache_clear()


def nome_item(item_id: int) -> NomeItem:
    """PT-BR and EN name, with the source file and whether simc can load it."""
    stats = _dados("stats_oficiais_itens.json").get("itens", {})
    registro = stats.get(str(item_id))
    indice = _indice_itens()
    simulavel = (item_id in indice) if indice else None
    fonte_simulavel = "item_data.inc" if indice else None

    if registro:
        return NomeItem(
            item_id=item_id,
            nome_pt=registro.get("nome_pt"),
            nome_en=registro.get("nome_en"),
            fonte="stats_oficiais_itens.json",
            simulavel=simulavel,
            fonte_simulavel=fonte_simulavel,
        )

    nome_en = indice.get(item_id)
    return NomeItem(
        item_id=item_id,
        nome_pt=None,
        nome_en=nome_en,
        fonte="item_data.inc" if nome_en else "desconhecido",
        simulavel=False if indice else None,
        fonte_simulavel=fonte_simulavel,
    )


def bonus_para_ilvl(bonus_id: int) -> IlvlBonus:
    """Item level for an upgrade bonus id. Returns ilvl=None when not validated."""
    bonus = _derivado("bonus_ilvl.json").get("bonus", {})
    registro = bonus.get(str(bonus_id))
    if not registro:
        return IlvlBonus(bonus_id=bonus_id, fonte="desconhecido")
    return IlvlBonus(
        bonus_id=bonus_id,
        trilha=registro.get("trilha"),
        rank=registro.get("rank"),
        ilvl=registro.get("ilvl"),
        evidencia=registro.get("evidencia"),
        fonte=registro.get("fonte") or "raidbots:bonus-upgrade-sets",
    )


def encantamentos_por_slot(slot: str):
    return _encantamentos_por_slot(slot)


def gemas(tipo: str | None = None) -> list[Gema]:
    dados = _dados("encantamentos_e_gemas_s2.json").get("gemas", {})
    filtro = (tipo or "").lower()
    saida: list[Gema] = []
    for chave, registro in dados.items():
        tipo_gema = registro.get("tipo") or ""
        texto = " ".join(
            [
                tipo_gema,
                registro.get("nome_pt") or "",
                registro.get("nome_en") or "",
            ]
        ).lower()
        if filtro and filtro not in texto:
            continue
        texto_pt = registro.get("texto_pt") or ""
        texto_en = registro.get("texto_en") or ""
        unica = "Único-equipado" in texto_pt or "Unique-Equipped" in texto_en
        saida.append(
            Gema(
                item_id=int(chave),
                nome_pt=registro.get("nome_pt"),
                nome_en=registro.get("nome_en"),
                tipo=tipo_gema or None,
                qualidade=registro.get("qualidade"),
                atributos=list(registro.get("atributos") or []),
                unica=unica,
                fonte="encantamentos_e_gemas_s2.json",
            )
        )
    saida.sort(key=lambda gema: (gema.nome_pt or "", gema.item_id))
    return saida


def runas_folio() -> list[Runa]:
    runas = _dados("rune_ids_s2.json").get("runas", [])
    entradas = {
        entrada.get("spell_id"): entrada.get("entry_id")
        for entrada in _derivado("omnium_entries.json").get("entradas", [])
    }
    saida: list[Runa] = []
    for registro in runas:
        id_base = registro.get("id_base")
        saida.append(
            Runa(
                linha=int(registro.get("linha") or 0),
                escolha=str(registro.get("escolha") or ""),
                id_base=int(id_base) if id_base is not None else 0,
                id_buff=registro.get("id_buff"),
                id_entrada=entradas.get(id_base) or entradas.get(registro.get("id_buff")),
                nome_pt=registro.get("nome_pt"),
                nome_en=registro.get("nome_en"),
                efeito_pt=registro.get("efeito_pt"),
                fonte="rune_ids_s2.json",
            )
        )
    return saida


def _slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(char for char in decomposto if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())


def normalizar_slot(valor: str | None) -> str | None:
    if not valor:
        return None
    alvo = _slug(valor)
    for slot, aliases in ALIASES_SLOT.items():
        if any(alias in alvo for alias in aliases):
            return slot
    return None


def _flatten_mplus() -> Iterator[tuple[str, str, dict]]:
    dados = _dados("mplus_loot_database.json")
    for secao_nome, secao in dados.items():
        if not isinstance(secao, dict):
            continue
        for sub, itens in secao.items():
            if not isinstance(itens, list):
                continue
            for item in itens:
                if isinstance(item, dict) and isinstance(item.get("item_id"), int):
                    yield secao_nome, sub, item


def _loot_de_item(
    sub: str, item: dict, *, fonte: str, tipo_efeito: str | None = None
) -> ItemLoot:
    stats_bruto = item.get("stats")
    stats: dict = stats_bruto if isinstance(stats_bruto, dict) else {}
    return ItemLoot(
        item_id=int(item["item_id"]),
        nome_pt=item.get("nome_pt"),
        nome_en=item.get("nome_en"),
        slot=normalizar_slot(item.get("slot") or sub),
        ilvl=stats.get("ilvl_referencia"),
        origem=sub,
        tipo_efeito=tipo_efeito or item.get("tipo_efeito"),
        usavel_conjurador=item.get("usavel_por_conjurador"),
        fonte=fonte,
    )


def itens_mplus(slot: str) -> list[ItemLoot]:
    """Loot from the M+ database for a normalized slot."""
    alvo = normalizar_slot(slot) or slot.lower()
    saida: list[ItemLoot] = []
    vistos: set[int] = set()
    for _secao, sub, item in _flatten_mplus():
        candidato = item.get("slot") or sub
        if normalizar_slot(candidato) != alvo:
            continue
        if item["item_id"] in vistos:
            continue
        vistos.add(item["item_id"])
        saida.append(_loot_de_item(sub, item, fonte="mplus_loot_database.json"))
    return saida


def berloques_conjurador() -> list[ItemLoot]:
    """Caster-usable trinkets. Explicit usavel_por_conjurador=false is excluded."""
    saida: list[ItemLoot] = []
    vistos: set[int] = set()
    for secao, sub, item in _flatten_mplus():
        if secao != "trinkets_mplus":
            continue
        if item.get("usavel_por_conjurador") is False:
            continue
        if item["item_id"] in vistos:
            continue
        vistos.add(item["item_id"])
        loot = _loot_de_item(sub, item, fonte="mplus_loot_database.json")
        loot.slot = "trinket"
        loot.usavel_conjurador = True
        saida.append(loot)
    return saida
