"""Ranking de trocas single-slot medido pelo SimulationCraft.

Reaproveita o runner, o chunking e o limiar por erro do Top Gear. Cada candidato
é simulado contra o conjunto equipado; o ranking é ordenado conforme o modo.
"""

from __future__ import annotations

from typing import Callable, Mapping

from .. import simc_runner as sr
from ..data import catalog
from ..data import pesos as pesos_mod
from ..data import pesos_medidos
from ..heuristic.score import podar_por_slot
from ..models import Personagem
from ..topgear.constraints import validar
from ..topgear.models import Candidato, Conjunto, ContextoSpec
from ..topgear.pools import construir_contexto
from ..topgear.runner import LeituraSim, SimuladorTopGear
from ..topgear.search import (
    _avaliar_opcoes,
    _limiar_por_erro,
    _simular_em_chunks,
    beam_search,
    conjunto_do_personagem,
)
from .models import DropRankingItem, DropRequest, DropResult, VereditoDrop

ProgressoDrop = Callable[[dict], None]
LIMIAR_PCT = 0.15
_MAX_VENCEDORES_POR_SLOT = 5


def _veredito(delta_pct: float, limiar: float) -> VereditoDrop:
    if delta_pct > limiar:
        return "ganho"
    if delta_pct < -limiar:
        return "perda"
    return "empate"


def _montar_conjunto(
    base: Conjunto,
    base_dps: float,
    opcoes: Mapping[str, tuple[str, Candidato, Conjunto]],
    itens: list[DropRankingItem],
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    ctx: ContextoSpec,
    limiar_pct: float,
) -> tuple[Conjunto, float]:
    """Monta o conjunto final do ``best_in_bags`` (guloso + beam).

    O ranking single-slot é ótimo por slot, mas dois berloques/aneis podem ser
    mutuamente exclusivos; por isso o conjunto final é montado e remedido, com
    exclusividade garantida por ``validar``.
    """
    cand_por_chave: dict[tuple[str, int], Candidato] = {}
    for _nome, (slot, cand, _conj) in opcoes.items():
        if cand.item_id is not None:
            cand_por_chave[(slot, cand.item_id)] = cand

    pools_venc: dict[str, list[Candidato]] = {}
    for item in itens:
        if item.item_id is None or item.delta_pct <= 0:
            continue
        cand = cand_por_chave.get((item.slot, item.item_id))
        if cand is None:
            continue
        pools_venc.setdefault(item.slot, []).append(cand)

    for slot, lista in list(pools_venc.items()):
        vistos: set[tuple] = set()
        unicos: list[Candidato] = []
        for cand in lista:
            chave = (cand.item_id, tuple(sorted(cand.bonus_ids)))
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(cand)
        if unicos:
            pools_venc[slot] = unicos[:_MAX_VENCEDORES_POR_SLOT]
        else:
            del pools_venc[slot]

    if not pools_venc:
        return base, base_dps

    melhor = base
    melhor_dps = base_dps
    numero = 1
    # Passo 1: montagem gulosa, um slot por vez.
    for slot, lista in pools_venc.items():
        opcoes_slot: dict[str, Conjunto] = {}
        for cand in lista:
            if melhor.item_id(slot) == cand.item_id:
                continue
            novo = melhor.com_troca(slot, cand)
            ok, _motivos = validar(novo, ctx)
            if not ok:
                continue
            nome = f"g_{slot}_{cand.item_id}_{len(opcoes_slot)}"
            opcoes_slot[nome] = novo
        melhor, melhor_dps, _ = _avaliar_opcoes(
            melhor,
            melhor_dps,
            opcoes_slot,
            simulador=simulador,
            iterations=iterations,
            estagio="gulosa",
            limiar_pct=limiar_pct,
            numero=numero,
        )
        numero += 1

    # Passo 2: beam para capturar efeitos de par (ex.: dois berloques).
    melhor, melhor_dps, _ = beam_search(
        melhor,
        melhor_dps,
        pools_venc,
        set(),
        ctx,
        simulador=simulador,
        iterations=iterations,
        limiar_pct=limiar_pct,
        numero=numero,
        top_k=3,
        profundidade=2,
        max_por_slot=_MAX_VENCEDORES_POR_SLOT,
    )
    return melhor, melhor_dps


def executar_droptimizer(
    personagem: Personagem,
    candidatos: Mapping[str, list[Candidato]],
    *,
    simulador: SimuladorTopGear,
    request: DropRequest | None = None,
    ctx: ContextoSpec | None = None,
    progresso: ProgressoDrop | None = None,
) -> DropResult:
    """Mede cada candidato contra o conjunto equipado e devolve o ranking."""
    pedido = request or DropRequest(addon="")
    contexto = ctx or construir_contexto(
        classe=personagem.classe, spec=personagem.spec
    )
    limite = pedido.max_profilesets_rodada
    excluir = set(pedido.excluir)

    base = conjunto_do_personagem(personagem)
    avisos: list[str] = []

    # P0 degradação: se o orçamento estourar no meio, retornamos o ranking
    # parcial medido em vez de falhar o job inteiro.
    esgotado = {"flag": False}
    _simulador_original = simulador

    def _simulador_deg(conjuntos, iterations):
        if esgotado["flag"]:
            return LeituraSim(base_dps=None, resultados={})
        try:
            return _simulador_original(conjuntos, iterations)
        except sr.SimcOrcamentoEsgotado:
            esgotado["flag"] = True
            return LeituraSim(base_dps=None, resultados={})

    simulador = _simulador_deg

    primeira = _simular_em_chunks(simulador, {}, pedido.iterations, limite)
    base_dps = primeira.base_dps
    if base_dps is None:
        raise ValueError("O SimulationCraft não retornou o DPS da base.")
    base_erro = primeira.base_erro

    # Poda heurística (Caminho A): pontua barato e deixa o SimC medir só o top-K
    # de cada slot. Nunca poda berloques/armas/efeitos/itens sem stats; o score
    # é sempre estimativa, nunca DPS.
    if pedido.podar and pedido.pool_efetiva_por_slot > 0:
        pesos_heur = pesos_medidos.carregar_pesos_medidos(
            personagem
        ) or pesos_mod.pesos_para(contexto.classe, contexto.spec)
        poda = podar_por_slot(
            dict(candidatos),
            pesos_heur.valores,
            pedido.pool_efetiva_por_slot,
            fonte=pesos_heur.fonte,
        )
        if poda.descartados:
            avisos.append(
                "Poda heurística: "
                f"{poda.descartados} candidato(s) descartado(s) antes do SimC "
                f"(estimativa de pesos, não DPS; fonte: {pesos_heur.fonte})."
            )
        candidatos = poda.mantidos

    opcoes: dict[str, tuple[str, Candidato, Conjunto]] = {}
    for slot, lista in candidatos.items():
        if slot not in base.itens:
            continue
        equipado = base.item_id(slot)
        for candidato in lista:
            if candidato.item_id is not None and candidato.item_id in excluir:
                continue
            if candidato.item_id is not None and candidato.item_id == equipado:
                continue
            novo = base.com_troca(slot, candidato)
            ok, _motivos = validar(novo, contexto)
            if not ok:
                continue
            nome = f"{slot}_{candidato.item_id or 0}_{len(opcoes)}"
            opcoes[nome] = (slot, candidato, novo)

    if not opcoes:
        avisos.append("Nenhum candidato legal para comparar com o equipado.")
        return DropResult(
            modo=pedido.modo,
            base_dps=base_dps,
            iterations=pedido.iterations,
            itens=[],
            avisos=avisos,
        )

    leitura = _simular_em_chunks(
        simulador, {nome: info[2] for nome, info in opcoes.items()}, pedido.iterations, limite
    )

    itens: list[DropRankingItem] = []
    for nome, (slot, candidato, _conjunto) in opcoes.items():
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        delta = 100.0 * (dps - base_dps) / base_dps if base_dps else 0.0
        limiar = _limiar_por_erro(
            LIMIAR_PCT, base_erro, leitura.erros.get(nome)
        )
        nome_pt = candidato.nome_pt
        if nome_pt is None and candidato.item_id is not None:
            nome_pt = catalog.nome_item(candidato.item_id).nome_pt
        itens.append(
            DropRankingItem(
                slot=slot,
                item_id=candidato.item_id,
                nome_pt=nome_pt,
                ilvl=candidato.ilvl,
                dps=dps,
                delta_pct=delta,
                limiar_pct=limiar,
                veredito=_veredito(delta, limiar),
            )
        )

    if pedido.modo == "worst_in_bags":
        itens.sort(key=lambda item: (item.delta_pct, item.slot))
        avisos.append(
            "worst_in_bags: o ranking mede trocas isoladas que pioram o DPS; "
            "as perdas não são somadas em um conjunto."
        )
    else:
        itens.sort(key=lambda item: (-item.delta_pct, item.slot))

    conjunto: Conjunto | None = None
    conjunto_dps: float | None = None
    delta_conjunto_pct: float | None = None
    if pedido.modo == "best_in_bags" and itens:
        # A montagem respeita o chunking da rodada (mesmo limite do ranking).
        def simulador_chunk(conjuntos, iterations):
            return _simular_em_chunks(simulador, conjuntos, iterations, limite)

        conjunto, conjunto_dps = _montar_conjunto(
            base,
            base_dps,
            opcoes,
            itens,
            simulador=simulador_chunk,
            iterations=pedido.iterations,
            ctx=contexto,
            limiar_pct=LIMIAR_PCT,
        )
        if base_dps:
            delta_conjunto_pct = 100.0 * (conjunto_dps - base_dps) / base_dps
        if conjunto_dps <= base_dps:
            avisos.append(
                "Nenhuma combinação superou o conjunto atual; o conjunto final "
                "equivale ao equipado."
            )

    if esgotado["flag"]:
        avisos.append(
            "Orçamento de tempo esgotado: ranking parcial (só os itens "
            "medidos até o limite). Aumente o orçamento para completar."
        )

    if progresso is not None:
        progresso(
            {
                "modo": pedido.modo,
                "candidatos": len(opcoes),
                "base_dps": base_dps,
            }
        )

    return DropResult(
        modo=pedido.modo,
        base_dps=base_dps,
        iterations=pedido.iterations,
        itens=itens,
        conjunto=conjunto,
        conjunto_dps=conjunto_dps,
        delta_conjunto_pct=delta_conjunto_pct,
        avisos=avisos,
    )
