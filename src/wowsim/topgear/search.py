"""Staged Top Gear search: marginal scan, greedy assembly and fine stages.

Stages 1-2 (items) run until convergence; stages 4-7 then optimise enchantments,
gems, talents and Folio runes over the winning set. Every accepted step is
measured by SimulationCraft and must beat the current set by the error floor.
Beam search and final refinement arrive in a later phase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from .. import simc_runner as sr
from ..data import catalog, consumables
from ..data import pesos as pesos_mod
from ..data import pesos_medidos
from ..heuristic.score import podar_por_slot
from ..models import Personagem
from .constraints import avisos as avisos_de_conjunto
from .constraints import validar
from .models import (
    Candidato,
    Conjunto,
    ContextoSpec,
    Estagio,
    Rodada,
    TopGearRequest,
    TopGearResult,
    Troca,
)
from .pools import (
    combinacoes_folio,
    construir_contexto,
    consumiveis,
    encantos_por_slot,
    gemas_catalogo,
    talentos_disponiveis,
)
from .runner import LeituraSim, SimuladorTopGear

LIMIAR_PCT = 0.15
# Teto de candidatos re-medidos no modo verificação (evita custo descontrolado).
MAX_CANDIDATOS_VERIFICACAO = 60
Progresso = Callable[[dict], None]
CAMPOS_CONSUMIVEIS = ("flask", "potion", "food", "augmentation")


def _limiar_por_erro(limiar_pct: float, *erros: float | None) -> float:
    """Acceptance floor: the larger of the fixed floor and the measured error."""
    return max([limiar_pct, *[abs(erro) for erro in erros if erro is not None]])


def _simular_em_chunks(
    simulador: SimuladorTopGear,
    conjuntos: Mapping[str, Conjunto],
    iterations: int,
    limite: int | None,
) -> LeituraSim:
    """Split a batch into ``limite``-sized runs and merge the measured readings.

    This enforces ``max_profilesets_rodada`` so a large pool never writes a
    single enormous profileset file (memory/simc blow-up).
    """
    if not limite or limite <= 0 or len(conjuntos) <= limite:
        return simulador(conjuntos, iterations)

    itens = list(conjuntos.items())
    base_dps: float | None = None
    base_erro: float | None = None
    resultados: dict[str, float] = {}
    erros: dict[str, float] = {}
    for inicio in range(0, len(itens), limite):
        parte = dict(itens[inicio : inicio + limite])
        leitura = simulador(parte, iterations)
        if base_dps is None:
            base_dps = leitura.base_dps
        if base_erro is None:
            base_erro = leitura.base_erro
        resultados.update(leitura.resultados)
        erros.update(leitura.erros)
    return LeituraSim(
        base_dps=base_dps, resultados=resultados, base_erro=base_erro, erros=erros
    )


@dataclass(frozen=True)
class _CandidatoMarginal:
    slot: str
    candidato: Candidato
    conjunto: Conjunto


def conjunto_do_personagem(personagem: Personagem) -> Conjunto:
    """Base set built from the addon export, with provenance for the report."""
    itens: dict[str, Candidato] = {}
    for slot, item in personagem.equipado.items():
        if slot == "tabard" or item.item_id is None:
            continue
        itens[slot] = Candidato(
            slot=slot,
            item_id=item.item_id,
            enchant_id=item.enchant_id,
            gem_ids=list(item.gem_ids),
            bonus_ids=list(item.bonus_ids),
            ilvl=catalog.ilvl_do_item(item),
            fonte="addon",
            nome_pt=item.nome_pt,
            nome_en=item.nome_en,
        )
    return Conjunto(itens=itens, talentos=personagem.talents_atual)


def _enriquecer_conjunto(conjunto: Conjunto) -> Conjunto:
    """Preenche nome, ícone e atributos (do catálogo) em cada item para a UI."""
    itens: dict[str, Candidato] = {}
    for slot, cand in conjunto.itens.items():
        if cand.item_id is None:
            itens[slot] = cand
            continue
        visual = catalog.visual_item(cand.item_id)
        nomes = catalog.nome_item(cand.item_id)
        itens[slot] = cand.model_copy(
            update={
                "stats": visual.get("stats") or None,
                "icone": visual.get("icone") or cand.icone,
                # Nome nunca fica vazio quando o catálogo o conhece (delve/craft).
                "nome_pt": cand.nome_pt or nomes.nome_pt,
                "nome_en": cand.nome_en or nomes.nome_en,
            }
        )
    return conjunto.model_copy(update={"itens": itens})


def _troca(slot: str, de: Candidato | None, para: Candidato) -> Troca:
    return Troca(
        slot=slot,
        de=de.rotulo if de is not None else None,
        para=para.rotulo,
        de_item_id=de.item_id if de is not None else None,
        para_item_id=para.item_id,
    )


def _trocas_contra(base: Conjunto, melhor: Conjunto) -> list[Troca]:
    trocas: list[Troca] = []
    for slot in sorted(set(base.itens) | set(melhor.itens)):
        anterior = base.itens.get(slot)
        atual = melhor.itens.get(slot)
        if atual is None:
            continue
        if anterior is None:
            trocas.append(_troca(slot, None, atual))
            continue
        if anterior.item_id != atual.item_id:
            trocas.append(_troca(slot, anterior, atual))
            continue
        if anterior.enchant_id != atual.enchant_id:
            trocas.append(
                Troca(
                    slot=slot,
                    de=f"encanto {anterior.enchant_id or '—'}",
                    para=f"encanto {atual.enchant_id or '—'}",
                    de_item_id=anterior.item_id,
                    para_item_id=atual.item_id,
                )
            )
        elif anterior.gem_ids != atual.gem_ids:
            trocas.append(
                Troca(
                    slot=slot,
                    de="gemas " + "/".join(str(g) for g in anterior.gem_ids),
                    para="gemas " + "/".join(str(g) for g in atual.gem_ids),
                    de_item_id=anterior.item_id,
                    para_item_id=atual.item_id,
                )
            )
    if base.talentos != melhor.talentos and melhor.talentos:
        trocas.append(
            Troca(slot="talentos", de="build atual", para="loadout otimizado")
        )
    for campo in CAMPOS_CONSUMIVEIS:
        antes = getattr(base, campo)
        depois = getattr(melhor, campo)
        if depois and depois != antes:
            trocas.append(
                Troca(
                    slot=campo,
                    de=consumables.nome(campo, antes) or antes,
                    para=consumables.nome(campo, depois) or depois,
                )
            )
    if base.runas_folio != melhor.runas_folio and melhor.runas_folio:
        trocas.append(
            Troca(
                slot="folio",
                de=" ".join(base.runas_folio) or "—",
                para=" ".join(melhor.runas_folio),
            )
        )
    return trocas


def _melhor_por_slot(
    marginais: Mapping[str, _CandidatoMarginal],
    leitura: LeituraSim,
) -> dict[str, _CandidatoMarginal]:
    vencedores: dict[str, _CandidatoMarginal] = {}
    melhor_dps: dict[str, float] = {}
    for nome, info in marginais.items():
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        if info.slot not in melhor_dps or dps > melhor_dps[info.slot]:
            melhor_dps[info.slot] = dps
            vencedores[info.slot] = info
    return vencedores


def _avaliar_opcoes(
    melhor: Conjunto,
    melhor_dps: float,
    opcoes: Mapping[str, Conjunto],
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    estagio: Estagio,
    limiar_pct: float,
    numero: int,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Simulate a batch of alternatives; accept the best if it beats the floor."""
    if not opcoes:
        return melhor, melhor_dps, []

    leitura = simulador(opcoes, iterations)
    melhor_nome: str | None = None
    melhor_dps_opcao: float | None = None
    for nome in opcoes:
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        if melhor_dps_opcao is None or dps > melhor_dps_opcao:
            melhor_dps_opcao = dps
            melhor_nome = nome

    if melhor_nome is None or melhor_dps_opcao is None:
        return melhor, melhor_dps, []

    delta_pct = (
        100.0 * (melhor_dps_opcao - melhor_dps) / melhor_dps if melhor_dps else 0.0
    )
    limiar = _limiar_por_erro(
        limiar_pct, leitura.base_erro, leitura.erros.get(melhor_nome)
    )
    aceito = delta_pct > limiar
    rodada = Rodada(
        numero=numero,
        estagio=estagio,
        dps=melhor_dps_opcao,
        delta_pct=delta_pct,
        candidatos=len(opcoes),
        trocas=1 if aceito else 0,
    )
    if aceito:
        return opcoes[melhor_nome], melhor_dps_opcao, [rodada]
    return melhor, melhor_dps, [rodada]


def otimizar_encantos(
    melhor: Conjunto,
    melhor_dps: float,
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    encantos: Mapping[str, list[Candidato]],
    limiar_pct: float,
    numero: int,
    travados: set[str] | None = None,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Coordinate descent per (slot, layer); rings are always changed together."""
    rodadas: list[Rodada] = []
    bloqueados = travados or set()
    for slot, lista in encantos.items():
        por_camada: dict[str, list[Candidato]] = {}
        for candidato in lista:
            por_camada.setdefault(candidato.tipo or "encantamento", []).append(candidato)

        for camada, opcoes in por_camada.items():
            alvos = ["finger1", "finger2"] if slot == "finger" else [slot]
            alvos = [
                alvo
                for alvo in alvos
                if alvo in melhor.itens
                and melhor.itens[alvo].item_id is not None
                and alvo not in bloqueados
            ]
            if not alvos:
                continue

            conjuntos: dict[str, Conjunto] = {}
            for opcao in opcoes:
                if all(
                    melhor.itens[alvo].enchant_id == opcao.enchant_id for alvo in alvos
                ):
                    continue
                conjunto = melhor
                for alvo in alvos:
                    atual = conjunto.itens[alvo]
                    novo = atual.model_copy(update={"enchant_id": opcao.enchant_id})
                    conjunto = conjunto.com_troca(alvo, novo)
                ok, _motivos = validar(conjunto, ctx)
                if not ok:
                    continue
                nome = f"e_{slot}_{camada}_{opcao.enchant_id}_{len(conjuntos)}"
                conjuntos[nome] = conjunto

            melhor, melhor_dps, novas = _avaliar_opcoes(
                melhor,
                melhor_dps,
                conjuntos,
                simulador=simulador,
                iterations=iterations,
                estagio="encantos",
                limiar_pct=limiar_pct,
                numero=numero,
            )
            rodadas.extend(novas)
    return melhor, melhor_dps, rodadas


def otimizar_gemas(
    melhor: Conjunto,
    melhor_dps: float,
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    gemas: Iterable[Candidato],
    limiar_pct: float,
    numero: int,
    travados: set[str] | None = None,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Swap each socket for a gem of the same family, one slot at a time."""
    indice = {gema.item_id: gema for gema in gemas if gema.item_id is not None}
    rodadas: list[Rodada] = []
    bloqueados = travados or set()

    for slot, atual in list(melhor.itens.items()):
        if slot in bloqueados:
            continue
        if not atual.gem_ids:
            continue
        gema_atual = indice.get(atual.gem_ids[0])
        if gema_atual is None:
            continue
        familia = (gema_atual.tipo or "").lower().split("(")[0].strip()

        conjuntos: dict[str, Conjunto] = {}
        for gema in indice.values():
            if gema.item_id in atual.gem_ids:
                continue
            familia_gema = (gema.tipo or "").lower().split("(")[0].strip()
            if familia_gema != familia:
                continue
            novos = list(atual.gem_ids)
            novos[0] = gema.item_id or novos[0]
            conjunto = melhor.com_troca(
                slot, atual.model_copy(update={"gem_ids": novos})
            )
            ok, _motivos = validar(conjunto, ctx)
            if not ok:
                continue
            nome = f"g_{slot}_{gema.item_id}_{len(conjuntos)}"
            conjuntos[nome] = conjunto

        melhor, melhor_dps, novas = _avaliar_opcoes(
            melhor,
            melhor_dps,
            conjuntos,
            simulador=simulador,
            iterations=iterations,
            estagio="gemas",
            limiar_pct=limiar_pct,
            numero=numero,
        )
        rodadas.extend(novas)
    return melhor, melhor_dps, rodadas


def otimizar_talentos(
    melhor: Conjunto,
    melhor_dps: float,
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    talentos: Iterable[Candidato],
    limiar_pct: float,
    numero: int,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Try each validated loadout; only measured winners are accepted."""
    conjuntos: dict[str, Conjunto] = {}
    for candidato in talentos:
        if not candidato.valor or candidato.valor == melhor.talentos:
            continue
        conjunto = melhor.model_copy(update={"talentos": candidato.valor})
        ok, _motivos = validar(conjunto, ctx)
        if not ok:
            continue
        nome = f"t_{candidato.nome_pt or 'loadout'}_{len(conjuntos)}"
        conjuntos[nome] = conjunto

    return _avaliar_opcoes(
        melhor,
        melhor_dps,
        conjuntos,
        simulador=simulador,
        iterations=iterations,
        estagio="talentos",
        limiar_pct=limiar_pct,
        numero=numero,
    )


def otimizar_folio(
    melhor: Conjunto,
    melhor_dps: float,
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    combinacoes: Iterable[list[str]],
    limiar_pct: float,
    numero: int,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Try every valid Folio combination (72 today)."""
    conjuntos: dict[str, Conjunto] = {}
    for combo in combinacoes:
        if list(combo) == melhor.runas_folio:
            continue
        conjunto = melhor.model_copy(update={"runas_folio": list(combo)})
        ok, _motivos = validar(conjunto, ctx)
        if not ok:
            continue
        nome = f"f_{''.join(combo)}_{len(conjuntos)}"
        conjuntos[nome] = conjunto

    return _avaliar_opcoes(
        melhor,
        melhor_dps,
        conjuntos,
        simulador=simulador,
        iterations=iterations,
        estagio="folio",
        limiar_pct=limiar_pct,
        numero=numero,
    )


def otimizar_consumiveis(
    melhor: Conjunto,
    melhor_dps: float,
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    opcoes: Mapping[str, list[Candidato]],
    limiar_pct: float,
    numero: int,
    categorias: set[str] | None = None,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Test flask, potion, food and augment rune over the winning set.

    ``categorias`` mirrors the request ``incluir`` filter so disabled categories
    are not simulated at all.
    """
    rodadas: list[Rodada] = []
    permitidas = categorias if categorias is not None else set(CAMPOS_CONSUMIVEIS)
    for categoria in CAMPOS_CONSUMIVEIS:
        if categoria not in permitidas:
            continue
        atual = getattr(melhor, categoria)
        conjuntos: dict[str, Conjunto] = {}
        for candidato in opcoes.get(categoria, []):
            if not candidato.valor or candidato.valor == atual:
                continue
            conjunto = melhor.model_copy(update={categoria: candidato.valor})
            ok, _motivos = validar(conjunto, ctx)
            if not ok:
                continue
            nome = f"c_{categoria}_{len(conjuntos)}"
            conjuntos[nome] = conjunto

        melhor, melhor_dps, novas = _avaliar_opcoes(
            melhor,
            melhor_dps,
            conjuntos,
            simulador=simulador,
            iterations=iterations,
            estagio="consumiveis",
            limiar_pct=limiar_pct,
            numero=numero,
        )
        rodadas.extend(novas)
    return melhor, melhor_dps, rodadas


def _chave_conjunto(conjunto: Conjunto) -> tuple:
    return tuple(
        sorted(
            (
                slot,
                candidato.item_id or 0,
                tuple(candidato.bonus_ids),
                candidato.enchant_id or 0,
                tuple(candidato.gem_ids),
            )
            for slot, candidato in conjunto.itens.items()
        )
    )


def beam_search(
    melhor: Conjunto,
    melhor_dps: float,
    pools: Mapping[str, list[Candidato]],
    travados: set[str],
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    limiar_pct: float,
    numero: int,
    top_k: int = 3,
    profundidade: int = 2,
    max_por_slot: int = 5,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Explore interactions between up to ``profundidade`` slots.

    Stage 3 of the plan: a narrow beam keeps the search linear-ish while still
    capturing pair effects (trinket pair, tier breakpoints, weapon + off-hand).
    """
    melhor_atual = melhor
    melhor_atual_dps = melhor_dps
    rodadas: list[Rodada] = []
    feixe: list[tuple[Conjunto, float]] = [(melhor, melhor_dps)]

    for nivel in range(1, profundidade + 1):
        opcoes: dict[str, Conjunto] = {}
        vistos: set[tuple] = set()
        for conjunto, _dps in feixe:
            for slot, candidatos in pools.items():
                if slot in travados:
                    continue
                for candidato in candidatos[:max_por_slot]:
                    novo = conjunto.com_troca(slot, candidato)
                    if novo == conjunto:
                        continue
                    ok, _motivos = validar(novo, ctx)
                    if not ok:
                        continue
                    chave = _chave_conjunto(novo)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    nome = f"b{nivel}_{slot}_{candidato.item_id or 0}_{len(opcoes)}"
                    opcoes[nome] = novo

        if not opcoes:
            break

        leitura = simulador(opcoes, iterations)
        ordenado = sorted(
            (
                (dps, nome)
                for nome in opcoes
                if (dps := leitura.resultados.get(nome)) is not None
            ),
            reverse=True,
        )
        if not ordenado:
            break

        feixe = [(opcoes[nome], dps) for dps, nome in ordenado[:top_k]]
        melhor_nome = ordenado[0][1]
        melhor_nivel_dps = ordenado[0][0]
        delta_pct = (
            100.0 * (melhor_nivel_dps - melhor_dps) / melhor_dps if melhor_dps else 0.0
        )
        limiar = _limiar_por_erro(
            limiar_pct, leitura.base_erro, leitura.erros.get(melhor_nome)
        )
        aceito = melhor_nivel_dps > melhor_atual_dps + (
            melhor_atual_dps * limiar / 100.0
        )
        rodadas.append(
            Rodada(
                numero=numero,
                estagio="beam",
                dps=melhor_nivel_dps,
                delta_pct=delta_pct,
                candidatos=len(opcoes),
                trocas=1 if aceito else 0,
            )
        )
        if aceito:
            melhor_atual = opcoes[melhor_nome]
            melhor_atual_dps = melhor_nivel_dps

    return melhor_atual, melhor_atual_dps, rodadas


def refinar_final(
    melhor: Conjunto,
    melhor_dps: float,
    base: Conjunto,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    numero: int,
) -> tuple[Conjunto, float, list[Rodada]]:
    """Re-measure the final set with the higher iteration count (stage 8)."""
    if melhor == base:
        return melhor, melhor_dps, []

    leitura = simulador({"refino": melhor}, iterations)
    dps = leitura.resultados.get("refino")
    if dps is None:
        return melhor, melhor_dps, []

    # P2-07: a noisier re-measure must never report a lower DPS than triage.
    melhor_dps_final = max(melhor_dps, dps)
    delta_pct = (
        100.0 * (melhor_dps_final - melhor_dps) / melhor_dps if melhor_dps else 0.0
    )

    return (
        melhor,
        melhor_dps_final,
        [
            Rodada(
                numero=numero,
                estagio="refino",
                dps=melhor_dps_final,
                delta_pct=delta_pct,
                candidatos=1,
                trocas=1 if melhor_dps_final > melhor_dps else 0,
            )
        ],
    )


def _verificar_podados(
    melhor: Conjunto,
    melhor_dps: float,
    descartados_itens: Mapping[str, list[Candidato]],
    ctx: ContextoSpec,
    *,
    simulador: SimuladorTopGear,
    iterations: int,
    limiar_pct: float,
    numero: int,
) -> tuple[Conjunto, float, list[Rodada], str | None]:
    """Re-measure dropped candidates; recover a gain the heuristic may have missed."""
    conjuntos: dict[str, Conjunto] = {}
    for slot, lista in descartados_itens.items():
        for cand in lista:
            if len(conjuntos) >= MAX_CANDIDATOS_VERIFICACAO:
                break
            conjunto = melhor.com_troca(slot, cand)
            ok, _motivos = validar(conjunto, ctx)
            if not ok:
                continue
            nome = f"v_{slot}_{cand.item_id or 0}_{len(conjuntos)}"
            conjuntos[nome] = conjunto

    if not conjuntos:
        return melhor, melhor_dps, [], None

    leitura = simulador(conjuntos, iterations)
    melhor_nome: str | None = None
    melhor_dps_poda: float | None = None
    for nome in conjuntos:
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        if melhor_dps_poda is None or dps > melhor_dps_poda:
            melhor_dps_poda = dps
            melhor_nome = nome

    if melhor_nome is None or melhor_dps_poda is None:
        return melhor, melhor_dps, [], "Verificação da poda: nenhum resultado medido."

    limiar = _limiar_por_erro(
        limiar_pct, leitura.base_erro, leitura.erros.get(melhor_nome)
    )
    delta_pct = (
        100.0 * (melhor_dps_poda - melhor_dps) / melhor_dps if melhor_dps else 0.0
    )
    rodada = Rodada(
        numero=numero,
        estagio="verificacao",
        dps=melhor_dps_poda,
        delta_pct=delta_pct,
        candidatos=len(conjuntos),
        trocas=1 if delta_pct > limiar else 0,
    )
    if delta_pct > limiar:
        aviso = (
            "Verificação da poda: um candidato descartado superou o resultado e "
            "foi recuperado. Aumente pool_efetiva_por_slot para evitá-lo."
        )
        return conjuntos[melhor_nome], melhor_dps_poda, [rodada], aviso
    aviso = (
        "Verificação da poda: nenhum candidato descartado superou o resultado "
        "(K da heurística se mostrou suficiente)."
    )
    return melhor, melhor_dps, [rodada], aviso


def executar_topgear(
    personagem: Personagem,
    pools: Mapping[str, list[Candidato]],
    *,
    simulador: SimuladorTopGear,
    request: TopGearRequest | None = None,
    ctx: ContextoSpec | None = None,
    max_rodadas: int = 5,
    progresso: Progresso | None = None,
) -> TopGearResult:
    """Run all enabled stages and return the measured best set."""
    pedido = request or TopGearRequest(
        addon="",
        scenario="patchwerk",
        iterations_triagem=200,
        iterations_refino=2000,
        max_profilesets_rodada=300,
        orcamento_segundos=600,
        pool_por_slot=12,
        podar=True,
        pool_efetiva_por_slot=6,
    )
    contexto = ctx or construir_contexto()
    limiar_pct = LIMIAR_PCT
    incluir = set(pedido.incluir)
    # Multi-fidelidade: a triagem de itens e o beam avaliam centenas de
    # profilesets; rodar as ``iterations`` cheias ali domina o tempo. Usamos
    # ~1/4 das iterações para *escolher* e re-medimos o conjunto montado com as
    # iterações cheias (verificação) — precisão final preservada.
    iteracoes_screen = max(40, pedido.iterations_triagem // 4)

    # P2-08: drop any item the user explicitly excluded from the candidate pools.
    excluir = set(pedido.excluir)
    if excluir:
        pools = {
            slot: [c for c in candidatos if c.item_id not in excluir]
            for slot, candidatos in pools.items()
        }

    # P0-05: enforce max_profilesets_rodada by slicing every batch before simc.
    _limite_profilesets = pedido.max_profilesets_rodada
    _simulador_original = simulador
    # P0 degradação: quando o orçamento estoura no meio de uma rodada, paramos
    # de chamar o simc e deixamos a busca convergir com o melhor parcial medido.
    esgotado = {"flag": False}

    def _simulador_fatiado(conjuntos, iterations):
        if esgotado["flag"]:
            return LeituraSim(base_dps=None, resultados={})
        try:
            return _simular_em_chunks(
                _simulador_original, conjuntos, iterations, _limite_profilesets
            )
        except sr.SimcOrcamentoEsgotado:
            esgotado["flag"] = True
            return LeituraSim(base_dps=None, resultados={})

    simulador = _simulador_fatiado

    base = conjunto_do_personagem(personagem)
    melhor = base
    avisos: list[str] = []

    primeira = simulador({}, pedido.iterations_triagem)
    base_dps = primeira.base_dps
    if base_dps is None:
        raise ValueError("O SimulationCraft não retornou o DPS da base.")
    melhor_dps = base_dps
    rodadas: list[Rodada] = []

    deadline = time.monotonic() + pedido.orcamento_segundos
    travados = set(pedido.slots_travados)

    # Poda heurística (Caminho A): pontua barato e deixa o SimC medir só o top-K
    # de cada slot. Nunca poda berloques/armas/efeitos/itens sem stats; o score
    # é sempre estimativa, nunca DPS.
    descartados_itens: dict[str, list[Candidato]] = {}
    if pedido.podar and pedido.pool_efetiva_por_slot > 0:
        pesos_heur = pesos_medidos.carregar_pesos_medidos(
            personagem
        ) or pesos_mod.pesos_para(contexto.classe, contexto.spec)
        poda = podar_por_slot(
            pools,
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
            rodadas.append(
                Rodada(numero=0, estagio="poda", candidatos=poda.descartados)
            )
        descartados_itens = poda.descartados_itens
        pools = poda.mantidos

    for numero in range(1, max_rodadas + 1):
        if time.monotonic() >= deadline:
            avisos.append("Orçamento de tempo esgotado antes da convergência.")
            break

        marginais: dict[str, _CandidatoMarginal] = {}
        for slot, candidatos in pools.items():
            if slot in travados:
                continue
            for candidato in candidatos:
                conjunto = melhor.com_troca(slot, candidato)
                ok, _motivos = validar(conjunto, contexto)
                if not ok:
                    continue
                nome = (
                    f"r{numero}_{slot}_{candidato.item_id or 0}_"
                    f"{candidato.ilvl or 0}_{len(marginais)}"
                )
                marginais[nome] = _CandidatoMarginal(slot, candidato, conjunto)

        if not marginais:
            avisos.append("Nenhum candidato legal nas pools informadas.")
            break

        inicio = time.monotonic()
        leitura = simulador(
            {nome: info.conjunto for nome, info in marginais.items()},
            iteracoes_screen,
        )
        vencedores = _melhor_por_slot(marginais, leitura)

        conjunto_guloso = melhor
        for info in vencedores.values():
            conjunto_guloso = conjunto_guloso.com_troca(info.slot, info.candidato)

        if conjunto_guloso == melhor:
            rodadas.append(
                Rodada(
                    numero=numero,
                    estagio="gulosa",
                    dps=melhor_dps,
                    delta_pct=0.0,
                    candidatos=len(marginais),
                    trocas=0,
                    duracao_s=time.monotonic() - inicio,
                )
            )
            break

        ok, motivos = validar(conjunto_guloso, contexto)
        if not ok:
            avisos.extend(motivos)
            break

        avaliacao = simulador({"guloso": conjunto_guloso}, pedido.iterations_triagem)
        dps_guloso = avaliacao.resultados.get("guloso")
        if dps_guloso is None:
            avisos.append("A montagem gulosa não retornou DPS.")
            break

        delta_pct = 100.0 * (dps_guloso - melhor_dps) / melhor_dps if melhor_dps else 0.0
        rodadas.append(
            Rodada(
                numero=numero,
                estagio="gulosa",
                dps=dps_guloso,
                delta_pct=delta_pct,
                candidatos=len(marginais),
                trocas=len(vencedores),
                duracao_s=time.monotonic() - inicio,
            )
        )

        limiar_guloso = _limiar_por_erro(
            limiar_pct, avaliacao.base_erro, avaliacao.erros.get("guloso")
        )
        if delta_pct <= limiar_guloso:
            break

        melhor = conjunto_guloso
        melhor_dps = dps_guloso
        if progresso is not None:
            progresso(
                {
                    "rodada": numero,
                    "estagio": "gulosa",
                    "candidatos": len(marginais),
                    "melhor_dps": melhor_dps,
                }
            )

    numero_estagio = len(rodadas) + 1
    etapas: list[tuple[str, Callable[[], tuple[Conjunto, float, list[Rodada]]]]] = []

    def _beam():
        return beam_search(
            melhor,
            melhor_dps,
            pools,
            travados,
            contexto,
            simulador=simulador,
            iterations=pedido.iterations_triagem,
            limiar_pct=limiar_pct,
            numero=numero_estagio,
        )

    etapas.append(("beam", _beam))

    if "encanto" in incluir:
        encantos = encantos_por_slot()

        def _encantos():
            return otimizar_encantos(
                melhor,
                melhor_dps,
                contexto,
                simulador=simulador,
                iterations=pedido.iterations_triagem,
                encantos=encantos,
                limiar_pct=limiar_pct,
                numero=numero_estagio,
                travados=travados,
            )

        etapas.append(("encantos", _encantos))

    if "gema" in incluir:
        gemas = gemas_catalogo()

        def _gemas():
            return otimizar_gemas(
                melhor,
                melhor_dps,
                contexto,
                simulador=simulador,
                iterations=pedido.iterations_triagem,
                gemas=gemas,
                limiar_pct=limiar_pct,
                numero=numero_estagio,
                travados=travados,
            )

        etapas.append(("gemas", _gemas))

    if "talento" in incluir:
        talentos = talentos_disponiveis(personagem, pedido.talentos_extra)

        def _talentos():
            return otimizar_talentos(
                melhor,
                melhor_dps,
                contexto,
                simulador=simulador,
                iterations=pedido.iterations_triagem,
                talentos=talentos,
                limiar_pct=limiar_pct,
                numero=numero_estagio,
            )

        etapas.append(("talentos", _talentos))

    if "folio" in incluir:
        combos = combinacoes_folio()

        def _folio():
            return otimizar_folio(
                melhor,
                melhor_dps,
                contexto,
                simulador=simulador,
                iterations=pedido.iterations_triagem,
                combinacoes=combos,
                limiar_pct=limiar_pct,
                numero=numero_estagio,
            )

        etapas.append(("folio", _folio))

    if any(categoria in incluir for categoria in CAMPOS_CONSUMIVEIS):
        opcoes_consumiveis = consumiveis()

        def _consumiveis():
            return otimizar_consumiveis(
                melhor,
                melhor_dps,
                contexto,
                simulador=simulador,
                iterations=pedido.iterations_triagem,
                opcoes=opcoes_consumiveis,
                limiar_pct=limiar_pct,
                numero=numero_estagio,
                categorias=incluir,
            )

        etapas.append(("consumiveis", _consumiveis))

    for nome_etapa, executar in etapas:
        if time.monotonic() >= deadline:
            avisos.append(
                f"Orçamento esgotado antes da etapa de {nome_etapa}."
            )
            break
        melhor, melhor_dps, novas = executar()
        rodadas.extend(novas)
        numero_estagio += 1
        if progresso is not None:
            progresso(
                {
                    "rodada": numero_estagio,
                    "estagio": nome_etapa,
                    "melhor_dps": melhor_dps,
                }
            )

    if pedido.iterations_refino > pedido.iterations_triagem:
        melhor, melhor_dps, novas = refinar_final(
            melhor,
            melhor_dps,
            base,
            simulador=simulador,
            iterations=pedido.iterations_refino,
            numero=numero_estagio,
        )
        rodadas.extend(novas)

    if pedido.verificar_podados and descartados_itens and not esgotado["flag"]:
        if time.monotonic() < deadline:
            melhor, melhor_dps, novas, aviso_verif = _verificar_podados(
                melhor,
                melhor_dps,
                descartados_itens,
                contexto,
                simulador=simulador,
                iterations=iteracoes_screen,
                limiar_pct=limiar_pct,
                numero=numero_estagio + 1,
            )
            rodadas.extend(novas)
            if aviso_verif:
                avisos.append(aviso_verif)
        else:
            avisos.append("Verificação da poda ignorada: orçamento esgotado.")

    if esgotado["flag"]:
        avisos.append(
            "Orçamento de tempo esgotado: resultado parcial (melhor conjunto "
            "medido até o limite). Aumente o orçamento para convergir."
        )

    if melhor_dps <= base_dps:
        avisos.append("Nenhuma troca superou a base além do limiar de erro.")

    base = _enriquecer_conjunto(base)
    melhor = _enriquecer_conjunto(melhor)

    delta_final = 100.0 * (melhor_dps - base_dps) / base_dps if base_dps else 0.0
    avisos.extend(avisos_de_conjunto(melhor, contexto))

    return TopGearResult(
        melhor=melhor,
        base=base,
        base_dps=base_dps,
        melhor_dps=melhor_dps,
        delta_pct=delta_final,
        limiar_pct=limiar_pct,
        trocas=_trocas_contra(base, melhor),
        rodadas=rodadas,
        avisos=avisos,
    )
