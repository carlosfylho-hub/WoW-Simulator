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

from ..models import Gema, IlvlBonus, ItemEquipado, ItemLoot, NomeItem, Runa
from ..paths import DADOS_DIR, DERIVADOS_DIR, SIMC_SRC_DIR
from .enchants import encantamentos_por_slot as _encantamentos_por_slot

ITEM_DATA = SIMC_SRC_DIR / "engine" / "dbc" / "generated" / "item_data.inc"
_ITEM_RE = re.compile(r'\{\s*"([^"]+)",\s*(\d+)')

# The user only cares about these ceilings: Hero 6/6, Mythic 6/6 and the two
# forged upgrades.
ILVLS_ALVO = (321, 334, 341, 328)

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


def _dados_opcional(nome: str) -> dict:
    """Like ``_dados`` but returns ``{}`` when the file is absent/invalid."""
    try:
        return _dados(nome)
    except (OSError, json.JSONDecodeError):
        return {}


def _derivado(nome: str) -> dict:
    return _json(str(DERIVADOS_DIR / nome))


@lru_cache(maxsize=2)
def _item_data(caminho: str, mtime: float) -> dict[int, str]:
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    return {int(item_id): nome for nome, item_id in _ITEM_RE.findall(texto)}


_LINHA_ITEM = re.compile(r'\{\s*"((?:[^"\\]|\\.)*)",\s*(\d+),(.*)\},?\s*$')
_INVTYPE_SLOTS: dict[int, tuple[str, ...]] = {
    1: ("head",),
    2: ("neck",),
    3: ("shoulder",),
    4: ("shirt",),
    5: ("chest",),
    6: ("waist",),
    7: ("legs",),
    8: ("feet",),
    9: ("wrist",),
    10: ("hands",),
    11: ("finger1", "finger2"),
    12: ("trinket1", "trinket2"),
    13: ("main_hand",),
    14: ("off_hand",),
    15: ("main_hand",),
    16: ("back",),
    17: ("main_hand",),
    20: ("chest",),
    21: ("main_hand",),
    22: ("off_hand",),
    23: ("off_hand",),
    25: ("main_hand",),
}


@lru_cache(maxsize=2)
def _item_inv_types(caminho: str, mtime: float) -> dict[int, int]:
    """item_id -> InventoryType a partir do ``item_data.inc`` do simc.

    O 8º token (0-based) do restante da linha é o InventoryType; validado em
    251199 (head=1), 271483 (head=1) e 239648 (wrist=9).
    """
    texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
    tipos: dict[int, int] = {}
    for linha in texto.splitlines():
        casamento = _LINHA_ITEM.search(linha)
        if casamento is None:
            continue
        resto = casamento.group(3).split(",")
        if len(resto) <= 8:
            continue
        try:
            tipos[int(casamento.group(2))] = int(resto[8].strip())
        except ValueError:
            continue
    return tipos


_SOCKETS_RE = re.compile(r'^\s*\{\s*"[^"]*",\s*(\d+),.*?\{\s*(\d+),\s*(\d+),\s*(\d+)\s*\}')


@lru_cache(maxsize=2)
def _item_sockets(caminho: str, mtime: float) -> dict[int, int]:
    """item_id -> nº de engastes (``socket_color[3]`` do ``item_data.inc``).

    Ex.: Loa Worshiper's Band 251513 ``{ 7, 0, 0 }`` = 1 engaste (prismático).
    """
    saida: dict[int, int] = {}
    for linha in Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines():
        m = _SOCKETS_RE.match(linha)
        if m:
            saida[int(m.group(1))] = sum(1 for g in m.groups()[1:] if int(g))
    return saida


def engastes(item_id: int) -> int | None:
    """Quantos engastes o item tem no jogo (via simc), ou None se desconhecido."""
    if not ITEM_DATA.is_file():
        return None
    return _item_sockets(str(ITEM_DATA), ITEM_DATA.stat().st_mtime).get(item_id)


def inventory_type(item_id: int) -> int | None:
    """InventoryType do item (via simc), ou None se desconhecido."""
    if not ITEM_DATA.is_file():
        return None
    return _item_inv_types(str(ITEM_DATA), ITEM_DATA.stat().st_mtime).get(item_id)


def slots_do_item(item_id: int) -> list[str]:
    """Slots internos que o item pode ocupar (anéis/berloques têm dois)."""
    tipo = inventory_type(item_id)
    if tipo is None:
        return []
    return list(_INVTYPE_SLOTS.get(tipo, ()))


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


def ilvl_do_item(item: ItemEquipado) -> int | None:
    """Best known item level for an equipped or bag item."""
    if item.ilvl_comentario in ILVLS_ALVO:
        return item.ilvl_comentario
    for bonus_id in item.bonus_ids:
        ilvl = bonus_para_ilvl(bonus_id).ilvl
        if ilvl in ILVLS_ALVO:
            return ilvl
    return item.ilvl_comentario


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
    atributos_bruto = item.get("atributos")
    atributos = (
        [str(atributo) for atributo in atributos_bruto]
        if isinstance(atributos_bruto, list)
        else []
    )
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
        atributos=atributos,
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


def itens_da_secao(secao: str) -> list[ItemLoot]:
    """Every catalog item inside a loot section, keeping provenance.

    Armor sections are also merged from ``armaduras_malha_placa.json`` (scraped
    from Wowhead), which lives outside the MANIFEST snapshot.
    """
    fontes = (
        ("mplus_loot_database.json", _dados("mplus_loot_database.json")),
        ("armaduras_malha_placa.json", _dados_opcional("armaduras_malha_placa.json")),
    )
    saida: list[ItemLoot] = []
    vistos: set[int] = set()
    for fonte, base in fontes:
        dados = base.get(secao, {}) if isinstance(base, dict) else {}
        if not isinstance(dados, dict):
            continue
        for sub, itens in dados.items():
            if not isinstance(itens, list):
                continue
            for item in itens:
                if not isinstance(item, dict) or not isinstance(item.get("item_id"), int):
                    continue
                if item["item_id"] in vistos:
                    continue
                vistos.add(item["item_id"])
                saida.append(_loot_de_item(sub, item, fonte=fonte))
    return saida


_BONUS_POR_NIVEL = {341: 12856, 334: 12854, 328: 12848, 321: 12846}


def _tipo_do_slot_monitor(slot_texto: str) -> str | None:
    minusculo = slot_texto.lower()
    if "2m" in minusculo or "duas" in minusculo:
        return "2h"
    if "1m" in minusculo or "uma" in minusculo:
        return "1h"
    return None


def itens_monitor(nivel: int) -> list[ItemLoot]:
    """Every monitor item at a target level, with its upgrade bonus.

    The monitor holds weapons, neck and trinkets (no armor). Slot names are
    normalized; ``atributos`` keeps the raw attribute text so callers can filter
    by spec (Intelecto/Força/Agilidade).
    """
    bonus_nivel = _BONUS_POR_NIVEL.get(nivel)
    if bonus_nivel is None:
        return []
    saida: list[ItemLoot] = []
    for item in _dados("monitor_upgrades_s2.json").get("teto_341", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        slot_texto = str(item.get("slot") or "")
        slot = normalizar_slot(slot_texto)
        if slot is None:
            continue
        atributos = item.get("atributos") or []
        saida.append(
            ItemLoot(
                item_id=item["id"],
                nome_pt=item.get("nome_pt"),
                nome_en=item.get("nome_en"),
                slot=slot,
                ilvl=nivel,
                origem="monitor de upgrades",
                bonus_id=bonus_nivel,
                peconha=item.get("peconha"),
                fonte="monitor_upgrades_s2.json",
                atributos=(
                    [str(atributo) for atributo in atributos]
                    if isinstance(atributos, list)
                    else []
                ),
                tipo=_tipo_do_slot_monitor(slot_texto),
            )
        )
    return saida


_MAPA_STATS = {
    "Intelecto": "intellect",
    "Força": "strength",
    "Agilidade": "agility",
    "Vigor": "stamina",
    "Aceleração": "haste",
    "Aceleracao": "haste",  # o snapshot oficial grava sem acento (88 itens)
    "Forca": "strength",
    "Critico": "crit",
    "Crítico": "crit",
    "Maestria": "mastery",
    "Versatilidade": "versatility",
}


def itens_stats_index() -> dict[str, dict]:
    """Every item in the official stats snapshot, keyed by id string.

    Used so the UI can name/icon items that are outside the M+ database (delve,
    world drops) without inventing anything: only what the snapshot declares.
    """
    dados = _dados_opcional("stats_oficiais_itens.json").get("itens")
    return dados if isinstance(dados, dict) else {}


def stats_item(item_id: int) -> dict[str, int]:
    """Item attributes in English keys (for the UI tooltip), or empty dict."""
    registro = _dados("stats_oficiais_itens.json").get("itens", {}).get(str(item_id))
    if not isinstance(registro, dict):
        return {}
    saida: dict[str, int] = {}
    for chave, valor in registro.items():
        campo = _MAPA_STATS.get(chave)
        if campo and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            saida[campo] = int(valor)
    return saida


def visual_item(item_id: int) -> dict:
    """Attributes + texture slug so the UI can show an icon and a rich tooltip."""
    from . import icons

    from . import tooltips

    return {"stats": stats_item(item_id), "icone": icons.icone(item_id), **tooltips.info(item_id)}


def atributo_primario(item_id: int) -> str | None:
    """Primary attribute from the official stats snapshot, or None if unknown."""
    registro = _dados("stats_oficiais_itens.json").get("itens", {}).get(str(item_id))
    if not isinstance(registro, dict):
        return None
    for nome in ("Intelecto", "Força", "Agilidade"):
        if registro.get(nome):
            return nome
    return None


def berloques_monitor(nivel: int) -> list[ItemLoot]:
    """Trinkets at one of the four target levels (321/334/341/328).

    A raid/M+ trinket has a single item id; its track (heroic vs mythic) and its
    forge state are expressed purely through the upgrade ``bonus_id``. The
    monitor only lists trinkets inside the ``teto_341`` bucket (the
    ``teto_328`` bucket holds weapons/necks, no trinkets). So we take the
    trinkets from ``teto_341`` and apply the bonus matching the requested level:

    * ``12856`` = mythic 6/6 + venom forge = 341
    * ``12854`` = mythic 6/6           = 334
    * ``12848`` = heroic 6/6 + venom forge = 328
    * ``12846`` = heroic 6/6           = 321

    Only the monitor's own items are eligible, which keeps a forged bonus off
    old items and avoids inflating their stats.
    """
    bonus_por_nivel = {341: 12856, 334: 12854, 328: 12848, 321: 12846}
    bonus_nivel = bonus_por_nivel.get(nivel)
    if bonus_nivel is None:
        return []
    dados = _dados("monitor_upgrades_s2.json").get("teto_341", [])
    saida: list[ItemLoot] = []
    for item in dados:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        if normalizar_slot(item.get("slot")) != "trinket":
            continue
        saida.append(
            ItemLoot(
                item_id=item["id"],
                nome_pt=item.get("nome_pt"),
                nome_en=item.get("nome_en"),
                slot="trinket",
                ilvl=nivel,
                origem="monitor de upgrades",
                usavel_conjurador=True,
                bonus_id=bonus_nivel,
                peconha=item.get("peconha"),
                fonte="monitor_upgrades_s2.json",
            )
        )
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
