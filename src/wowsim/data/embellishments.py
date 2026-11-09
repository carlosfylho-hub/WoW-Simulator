"""Embellishment knowledge extracted from the crafting data.

The catalog must say, for every craftable item:
- whether the embellishment is built into the craft (``embelezado_embutido``);
- whether it is a craftable base that accepts an optional embellishment;
- which embellishment the spec guides recommend.

Nothing is guessed: unknown items return ``craftado=False`` and no recommendation.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from ..models import EmbelezamentoInfo
from ..paths import DADOS_DIR

LIMITE_EMBELEZAMENTOS = 2
FONTES_CRAFT = ("craft_receitas_s2.json", "craft_armas_s2.json", "craft_sistemas_s2.json")
FONTES_SPEC = (
    "affliction_warlock.json",
    "demonology_warlock.json",
    "destruction_warlock.json",
    "balance_druid.json",
    "shadow_priest.json",
)


@lru_cache(maxsize=8)
def _json(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def limpar_cache() -> None:
    _json.cache_clear()


def _dados(nome: str) -> dict:
    return _json(str(DADOS_DIR / nome))


def _slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())


def _percorrer(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        if isinstance(node.get("id"), int) and (node.get("nome_en") or node.get("nome_pt")):
            yield node
        for valor in node.values():
            yield from _percorrer(valor)
    elif isinstance(node, list):
        for valor in node:
            yield from _percorrer(valor)


def _coletar_por_id(node: object, dentro_embeleza: bool, saida: dict[int, str]) -> None:
    if isinstance(node, dict):
        for chave, valor in node.items():
            filho = dentro_embeleza or "embeleza" in str(chave).lower()
            _coletar_por_id(valor, filho, saida)
        item_id = node.get("item_id")
        nome = node.get("nome_pt") or node.get("nome_en")
        if dentro_embeleza and isinstance(item_id, int) and nome:
            saida[item_id] = nome
    elif isinstance(node, list):
        for valor in node:
            _coletar_por_id(valor, dentro_embeleza, saida)


def _recomendados_por_id() -> dict[int, str]:
    """Spec guides map a craftable base item id to its used embellishment."""
    saida: dict[int, str] = {}
    for arquivo in FONTES_SPEC:
        try:
            _coletar_por_id(_dados(arquivo), False, saida)
        except (OSError, json.JSONDecodeError):
            continue
    return saida


def _recomendados() -> dict[str, str]:
    """Map lower-case EN item name to the recommended embellishment name."""
    dados = _dados("mplus_loot_database.json")
    principais = (
        dados.get("gear_craftado_bis", {}).get("itens_craftados_principais", {})
    )
    saida: dict[str, str] = {}
    for registro in principais.values():
        if not isinstance(registro, dict):
            continue
        nome = registro.get("nome_en")
        recomendado = registro.get("embellishment_bis")
        if nome and recomendado:
            saida[_slug(nome)] = recomendado
    return saida


@lru_cache(maxsize=1)
def _indice() -> dict[int, dict]:
    recomendados = _recomendados()
    recomendados_id = _recomendados_por_id()
    indice: dict[int, dict] = {}
    for arquivo in FONTES_CRAFT:
        dados = _dados(arquivo)
        for item in _percorrer(dados):
            item_id = item["id"]
            nome_en = item.get("nome_en")
            embutido = bool(item.get("embelezado_embutido"))
            atual = indice.get(item_id, {})
            indice[item_id] = {
                "item_id": item_id,
                "nome_pt": item.get("nome_pt") or atual.get("nome_pt"),
                "nome_en": nome_en or atual.get("nome_en"),
                "slot": item.get("slot") or atual.get("slot"),
                "embutido": embutido or atual.get("embutido", False),
                "recomendado": (
                    recomendados_id.get(item_id)
                    or (recomendados.get(_slug(nome_en)) if nome_en else None)
                    or atual.get("recomendado")
                ),
                "fonte": arquivo,
            }
    return indice


def info(item_id: int) -> EmbelezamentoInfo:
    """Embellishment facts for one item id."""
    registro = _indice().get(item_id)
    if registro is None:
        return EmbelezamentoInfo(item_id=item_id, fonte="desconhecido")
    embutido = bool(registro["embutido"])
    return EmbelezamentoInfo(
        item_id=item_id,
        craftado=True,
        embutido=embutido,
        aceita=not embutido,
        recomendado=registro.get("recomendado"),
        nome_pt=registro.get("nome_pt"),
        nome_en=registro.get("nome_en"),
        fonte=registro.get("fonte") or "craft_receitas_s2.json",
    )


def efeito_embutido(item_id: int) -> str | None:
    """Texto do embelezamento que JÁ VEM no item craftado (``efeitos_embutidos.json``).

    Gerado por ``scripts/raspar_efeitos_embutidos.py`` (tooltip PT-BR do Wowhead).
    Junta o efeito "Equipar/Uso" e, se houver, o bônus do conjunto craftado.
    Só para a tela (P1); sem dado, None.
    """
    try:
        dados = _derivado_json("efeitos_embutidos.json")
    except (OSError, ValueError):
        return None
    reg = (dados.get("itens") or {}).get(str(item_id))
    if not reg:
        return None
    partes = [reg["efeito"]] if reg.get("efeito") else []
    conjunto = reg.get("conjunto")
    if conjunto:
        for b in conjunto.get("bonus", []):
            partes.append(
                f"Conjunto {conjunto.get('nome') or ''} ({b['pecas']} peças): {b['efeito']}".replace("  ", " ")
            )
    return " ".join(partes) or None


def _derivado_json(nome: str) -> dict:
    from . import catalog

    return catalog._derivado(nome)


def listar_craftados() -> list[dict]:
    """All craftable items with their embellishment facts, for the catalog API."""
    return [dict(registro) for registro in _indice().values()]


_CAMPOS_WOWHEAD = (
    "icone",
    "icone_url",
    "texto_completo",
    "texto_en",
    "qualidade",
    "materiais",
    "usado_em",
)


def mesclar_wowhead(embelezamentos: list[dict], wowhead: dict) -> list[dict]:
    """Mescla ícone/texto/materiais do Wowhead em cada embelezamento (por reagente).

    O texto do Wowhead é só descritivo (tela); nenhum número dele entra em
    cálculo de DPS (P1). Campos ausentes/vazios do Wowhead não sobrescrevem nada.
    """
    por_id: dict[int, dict] = {}
    for entrada in wowhead.get("embelezamentos", []) or []:
        if isinstance(entrada, dict) and entrada.get("reagente_id") is not None:
            por_id[int(entrada["reagente_id"])] = entrada
    for item in embelezamentos:
        extra = por_id.get(int(item["reagente_id"]))
        if not extra:
            continue
        for campo in _CAMPOS_WOWHEAD:
            valor = extra.get(campo)
            if valor not in (None, "", []):
                item[campo] = valor
    return embelezamentos
