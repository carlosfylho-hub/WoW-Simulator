"""Omnium Folio resolution.

The addon field omnium_talents carries one choice entry per line. The entry ids
are the 1368xx family and map to rune codes 1A..5C by spell id, using the
derived table built from Raidbots plus rune_ids_s2.json.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..models import Personagem, RunasFolio
from ..paths import DERIVADOS_DIR

TOTAL_LINHAS = 5
TOTAL_RUNAS = 13


@lru_cache(maxsize=4)
def _carregar(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def _dados() -> dict:
    return _carregar(str(DERIVADOS_DIR / "omnium_entries.json"))


def entradas() -> dict[int, dict]:
    """entry_id -> record with escolha, linha, spell_id and PT-BR name."""
    saida: dict[int, dict] = {}
    for entrada in _dados().get("entradas", []):
        entry_id = entrada.get("entry_id")
        if isinstance(entry_id, int):
            saida[entry_id] = entrada
    return saida


def linhas() -> dict[int, list[dict]]:
    """line number -> choices, sorted by choice index."""
    agrupado: dict[int, list[dict]] = {}
    for entrada in entradas().values():
        linha = entrada.get("linha")
        if isinstance(linha, int):
            agrupado.setdefault(linha, []).append(entrada)
    for escolhas in agrupado.values():
        escolhas.sort(key=lambda item: item.get("index") or 0)
    return agrupado


def codigo_para_ids(codigo: str) -> list[int]:
    """Convert '1A-2B-3A-4A-5A' to the five entry ids."""
    escolhas = [parte.strip().upper() for parte in codigo.split("-") if parte.strip()]
    indice = {entrada["escolha"]: entrada["entry_id"] for entrada in entradas().values()}
    ids: list[int] = []
    for escolha in escolhas:
        if escolha not in indice:
            raise ValueError(f"Runa desconhecida no código: {escolha}")
        ids.append(indice[escolha])
    if len(ids) != TOTAL_LINHAS:
        raise ValueError(f"Código com {len(ids)} runas; esperado {TOTAL_LINHAS}.")
    return ids


def selecao_de_ids(ids: list[int], *, fonte: str = "dados/derivados/omnium_entries.json") -> RunasFolio:
    tabela = entradas()
    por_linha: dict[str, str] = {}
    ids_por_linha: dict[str, list[int]] = {}
    invalido = False

    for entry_id in ids:
        registro = tabela.get(entry_id)
        if registro is None or not registro.get("mapeado"):
            invalido = True
            continue
        chave = str(registro["linha"])
        if chave in por_linha:
            invalido = True
            continue
        por_linha[chave] = str(registro["escolha"])
        ids_por_linha[chave] = [entry_id]

    codigo = None
    if len(por_linha) == TOTAL_LINHAS:
        codigo = "-".join(por_linha[str(linha)] for linha in range(1, TOTAL_LINHAS + 1))
    else:
        invalido = True

    return RunasFolio(
        codigo=codigo,
        por_linha=por_linha,
        ids_por_linha=ids_por_linha,
        confianca="alta" if not invalido else "baixa",
        fonte=fonte,
    )


def selecao_atual(personagem: Personagem, override: str | None = None) -> RunasFolio:
    """Selection from --runas, else from the export, else empty with low confidence."""
    if override:
        try:
            ids = codigo_para_ids(override)
        except ValueError:
            return RunasFolio(fonte="--runas inválido", confianca="baixa")
        return selecao_de_ids(ids, fonte="--runas")

    if personagem.omnium_ids_brutos:
        return selecao_de_ids(personagem.omnium_ids_brutos)
    return RunasFolio(fonte="export sem omnium_talents", confianca="baixa")


def variacoes_de_linha(selecao: RunasFolio) -> list[tuple[str, str, int]]:
    """One change at a time inside the same line.

    Returns (nome, codigo_novo, entry_id_novo) for every alternative.
    """
    if not selecao.codigo:
        return []
    atuais = {int(linha): escolha for linha, escolha in selecao.por_linha.items()}
    saida: list[tuple[str, str, int]] = []
    for linha, escolhas in linhas().items():
        atual = atuais.get(linha)
        for escolha in escolhas:
            if escolha["escolha"] == atual:
                continue
            novo = dict(atuais)
            novo[linha] = escolha["escolha"]
            codigo = "-".join(novo[n] for n in range(1, TOTAL_LINHAS + 1))
            saida.append((f"folio_{escolha['escolha'].lower()}", codigo, escolha["entry_id"]))
    return saida
