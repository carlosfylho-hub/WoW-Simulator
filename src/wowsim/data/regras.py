"""Regras da temporada raspadas (``dados/derivados/regras_temporada.json``).

Gerado por ``scripts/raspar_regras_temporada.py`` (Crawl4AI/Firecrawl). Se o
arquivo faltar, cada função devolve ``None``/vazio e a tela mostra "sem dado"
— nunca um valor estimado (P1).
"""

from __future__ import annotations

from functools import lru_cache

from . import catalog


@lru_cache(maxsize=1)
def regras() -> dict:
    try:
        return catalog._derivado("regras_temporada.json")
    except (FileNotFoundError, OSError, ValueError):
        return {}


def forja() -> dict:
    return regras().get("forja") or {}


def slot_aceita_forja(slot: str | None) -> bool:
    """Forja do Veneno: só armas, berloques e colar (Method.gg). Sem dado: aceita."""
    slots = forja().get("slots")
    if not slots or slot is None:
        return True
    base = {"finger1": "finger", "finger2": "finger"}.get(slot, slot)
    return any(base == s or (base == "trinket" and s.startswith("trinket")) for s in slots)


def custo_forja() -> dict | None:
    f = forja()
    if not f.get("custo"):
        return None
    return {"quantidade": int(f["custo"]), "moeda": f.get("moeda") or "Ascendant Venomstone"}


def craft() -> dict:
    return regras().get("craft") or {}


def upgrade() -> dict:
    return regras().get("upgrade") or {}


# ItemRedundancySlot do jogo, usado em ``slot_high_watermarks`` do export do SimC.
INDICE_MARCA = {
    "head": (0,), "neck": (1,), "shoulder": (2,), "chest": (3,), "waist": (4,),
    "legs": (5,), "feet": (6,), "wrist": (7,), "hands": (8,), "finger": (9,),
    "finger1": (9,), "finger2": (9,), "trinket": (10,), "trinket1": (10,),
    "trinket2": (10,), "back": (11,), "main_hand": (12, 13, 14), "off_hand": (15, 16),
}


def marcas_por_slot(marcas) -> dict[str, int]:
    """Slot -> maior ilvl já alcançado pelo personagem naquele slot."""
    por_indice = {m.indice: m.ilvl_atual for m in (marcas or [])}
    saida: dict[str, int] = {}
    for slot, indices in INDICE_MARCA.items():
        valores = [por_indice[i] for i in indices if i in por_indice]
        if valores:
            saida[slot] = max(valores)
    return saida
