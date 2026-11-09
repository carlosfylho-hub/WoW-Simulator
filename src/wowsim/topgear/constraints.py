"""Constraint validator for Top Gear sets.

Runs *before* SimulationCraft to discard illegal combinations and save time.
Returned messages are user-facing PT-BR strings; tests cover every rule.
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import Candidato, Conjunto, ContextoSpec

_SLOTS_BERLOQUE = ("trinket1", "trinket2")
_PADRAO_RUNA = re.compile(r"^([1-5])([A-Z])$")
_DOIS_MAOS = ("2h", "2m", "staff", "cajado", "bastao")
_UMA_MAO = ("1h", "1m", "dagger", "adaga", "wand", "varinha")


def _eh_dois_maos(candidato: Candidato) -> bool:
    if candidato.tipo_arma == "2h":
        return True
    texto = (candidato.tipo or "").lower()
    return any(marca in texto for marca in _DOIS_MAOS)


def _eh_uma_mao(candidato: Candidato) -> bool:
    if candidato.tipo_arma == "1h":
        return True
    texto = (candidato.tipo or "").lower()
    return any(marca in texto for marca in _UMA_MAO)


def _conta_embelezamentos(itens: Iterable[Candidato], ctx: ContextoSpec) -> int:
    return sum(
        1
        for candidato in itens
        if candidato.embelezamento
        or (candidato.item_id is not None and candidato.item_id in ctx.embelezamentos)
    )


def _conta_diamantes(itens: Iterable[Candidato], ctx: ContextoSpec) -> int:
    total = 0
    for candidato in itens:
        for gema in candidato.gem_ids:
            if gema in ctx.diamantes:
                total += 1
    return total


def _berloques_on_use(conjunto: Conjunto, ctx: ContextoSpec) -> list[str]:
    ativos: list[str] = []
    for slot in _SLOTS_BERLOQUE:
        candidato = conjunto.itens.get(slot)
        if candidato is None:
            continue
        if candidato.tipo_efeito == "ativo" or (
            candidato.item_id is not None and candidato.item_id in ctx.trinkets_on_use
        ):
            ativos.append(slot)
    return ativos


def _erros_armas(conjunto: Conjunto, ctx: ContextoSpec) -> list[str]:
    motivos: list[str] = []
    principal = conjunto.itens.get("main_hand")
    secundaria = conjunto.itens.get("off_hand")
    if principal is None:
        return motivos

    if _eh_dois_maos(principal):
        if secundaria is not None:
            motivos.append(
                "Arma de duas mãos não pode ser combinada com item de mão secundária."
            )
        return motivos

    if _eh_uma_mao(principal) and secundaria is not None:
        if ctx.offs_validos and secundaria.item_id not in ctx.offs_validos:
            motivos.append(
                "Item de mão secundária incompatível com a arma de uma mão."
            )
    elif (
        _eh_uma_mao(principal)
        and secundaria is None
        and ctx.exige_offhand_com_1h
        and ctx.offs_validos
    ):
        motivos.append("Arma de uma mão exige um item de mão secundária válido.")

    return motivos


def _erros_folio(conjunto: Conjunto) -> list[str]:
    runas = conjunto.runas_folio
    if not runas:
        return []

    motivos: list[str] = []
    linhas: list[str] = []
    for runa in runas:
        casamento = _PADRAO_RUNA.match(runa)
        if casamento is None:
            motivos.append(f"Runa do Folio inválida: {runa!r}.")
            continue
        linhas.append(casamento.group(1))

    if motivos:
        return motivos

    if len(runas) != 5:
        motivos.append("Folio exige exatamente 5 runas, uma por linha.")
    if sorted(linhas) != ["1", "2", "3", "4", "5"]:
        motivos.append("Folio exige exatamente uma runa por linha (1 a 5).")

    # Preserva a mensagem de duplicidade mesmo que a contagem esteja correta.
    if len(set(linhas)) != len(linhas) and not motivos:
        motivos.append("Folio repetiu uma linha; cada linha aceita uma única runa.")

    return motivos


def _erros_craft(itens: Iterable[Candidato], ctx: ContextoSpec) -> list[str]:
    motivos: list[str] = []
    for candidato in itens:
        if not candidato.craftado or candidato.ilvl is None:
            continue
        if candidato.ilvl > ctx.craft_ilvl_teto:
            motivos.append(
                f"Item craftado acima do teto de {ctx.craft_ilvl_teto}: "
                f"{candidato.rotulo}."
            )
    return motivos


def _conversoes_novas(itens: Iterable[Candidato], ctx: ContextoSpec) -> int:
    """Peças catalisadas que ainda não estavam equipadas (gastam carga)."""
    return sum(
        1
        for candidato in itens
        if candidato.catalisado
        and (candidato.item_id, candidato.redirected_base_stats)
        not in ctx.catalisados_equipados
    )


def _erros_catalisador(itens: Iterable[Candidato], ctx: ContextoSpec) -> list[str]:
    if ctx.max_catalisados is None:
        return []
    novas = _conversoes_novas(itens, ctx)
    if novas > ctx.max_catalisados:
        return [
            f"Conjunto usa {novas} conversão(ões) do Catalisador; o máximo é "
            f"{ctx.max_catalisados}."
        ]
    return []


def validar(conjunto: Conjunto, ctx: ContextoSpec) -> tuple[bool, list[str]]:
    """Return ``(True, [])`` when the set is legal, else ``(False, motivos)``."""
    itens = list(conjunto.itens.values())
    motivos: list[str] = []

    embelezamentos = _conta_embelezamentos(itens, ctx)
    if embelezamentos > ctx.max_embelezamentos:
        motivos.append(
            f"Conjunto tem {embelezamentos} embelezamentos; o máximo é "
            f"{ctx.max_embelezamentos}."
        )

    diamantes = _conta_diamantes(itens, ctx)
    if diamantes > ctx.max_diamantes:
        motivos.append(
            f"Conjunto tem {diamantes} diamantes de Eversong; o máximo é "
            f"{ctx.max_diamantes}."
        )

    on_use = _berloques_on_use(conjunto, ctx)
    if ctx.max_on_use is not None and len(on_use) > ctx.max_on_use:
        motivos.append(
            f"Berloques on-use em {', '.join(on_use)}: o máximo é "
            f"{ctx.max_on_use} efeito ativo (regra R4)."
        )

    motivos.extend(_erros_armas(conjunto, ctx))
    motivos.extend(_erros_folio(conjunto))
    motivos.extend(_erros_craft(itens, ctx))
    motivos.extend(_erros_catalisador(itens, ctx))

    return (not motivos, motivos)


def avisos(conjunto: Conjunto, ctx: ContextoSpec) -> list[str]:
    """Advisory checks that never block a set (tier breakpoints, Catalyst use)."""
    saida: list[str] = []
    if len(_berloques_on_use(conjunto, ctx)) >= 2:
        saida.append("Dois berloques de uso: o jogo permite e o SimC mede o par, mas costuma render menos que 1 de uso + 1 passivo.")
    novas = _conversoes_novas(conjunto.itens.values(), ctx)
    if novas:
        slots = ", ".join(
            slot
            for slot, candidato in conjunto.itens.items()
            if candidato.catalisado
            and (candidato.item_id, candidato.redirected_base_stats)
            not in ctx.catalisados_equipados
        )
        saida.append(
            f"Usa {novas} conversão(ões) do Catalisador ({slots}). Pressupõe que o "
            "Catalisador mantém trilha, nível e stats base do item original."
        )
    if not ctx.tier_ids:
        return saida
    pecas = sum(
        1
        for candidato in conjunto.itens.values()
        if candidato.item_id is not None and candidato.item_id in ctx.tier_ids
    )
    if pecas == 1:
        saida.append("Conjunto tier com 1 peça: o bônus de 2 peças fica inativo.")
    elif pecas == 3:
        saida.append("Conjunto tier com 3 peças: o bônus de 4 peças fica inativo.")
    return saida
