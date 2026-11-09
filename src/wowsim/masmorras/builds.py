"""Comparação por build (loadout): cenário, matriz, média ponderada e montagem.

P4 preservado: a referência de cada build é um profileset ``ref`` (a base com os
talentos daquela build) medido NA MESMA leitura em que os candidatos são medidos.
O conjunto montado é medido de novo numa execução de confirmação (``ref`` ×
``montado``), porque tier, dois berloques de uso e embelezamentos só aparecem na
combinação. Nenhum número de dano nasce aqui além do que o simc mediu.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Mapping

from ..topgear.constraints import validar
from ..topgear.models import Candidato, Conjunto, ContextoSpec
from ..topgear.runner import LeituraSim
from ..topgear.search import _limiar_por_erro
from .avaliar import LIMIAR_PCT, Avaliacao, Opcao, avaliar

Simulador = Callable[[Mapping[str, Conjunto], int], LeituraSim]

# Slots que formam par: o item pode ir para qualquer um dos dois lados.
PARES = {"finger1": "finger", "finger2": "finger", "trinket1": "trinket", "trinket2": "trinket"}


def conjuntos_da_build(
    base: Conjunto, codigo: str | None, conjuntos: dict[str, Conjunto]
) -> dict[str, Conjunto]:
    """Cópia dos conjuntos com os talentos da build e um ``ref`` de referência."""
    saida: dict[str, Conjunto] = {"ref": base.model_copy(update={"talentos": codigo})}
    for nome, conjunto in conjuntos.items():
        saida[nome] = conjunto.model_copy(update={"talentos": codigo})
    return saida


def cenario_da_build(nome: str) -> str:
    """Cenário pelo nome da build; medir 'single/raid' em M+ dá ranking sem sentido."""
    n = (nome or "").lower()
    if any(p in n for p in ("single", "raid", "boss")):
        return "patchwerk"
    return "dungeon_slice"  # m+, delves e o resto


def pesos_normalizados(builds: list[str], pesos: Mapping[str, float]) -> dict[str, float]:
    """Pesos das builds somando 1; ausentes ou todos zero viram pesos iguais."""
    brutos = {b: max(0.0, float(pesos.get(b, 0.0))) for b in builds}
    total = sum(brutos.values())
    if total <= 0:
        return {b: 1.0 / len(builds) for b in builds} if builds else {}
    return {b: v / total for b, v in brutos.items()}


def media_ponderada(deltas: dict[str, float], pesos: dict[str, float]) -> float:
    """Média do % de cada build ponderada pelos pesos do usuário (soma 1)."""
    total = sum(pesos.get(b, 0.0) for b in deltas)
    if total <= 0:
        raise ValueError("Pesos das builds somam zero.")
    return sum(d * pesos.get(b, 0.0) for b, d in deltas.items()) / total


def divergente(deltas: dict[str, float], limiares: dict[str, float]) -> bool:
    """True quando o item é ganho numa build e perda em outra (acima do limiar)."""
    return any(d > limiares[b] for b, d in deltas.items()) and any(
        d < -limiares[b] for b, d in deltas.items()
    )


# ------------------------------------------------------------------ montagem


def _nome_vencedor(avaliacao: Avaliacao, opcoes: dict[str, Opcao]) -> str | None:
    """Profileset da versão escolhida (catalisada quando a etiqueta manda)."""
    quer_cat = avaliacao.usa_catalisado
    nome = avaliacao.nome_cat if quer_cat else avaliacao.nome_cru
    if nome and nome in opcoes:
        return nome
    # Avaliação construída sem os nomes (testes antigos): procura pela opção.
    return next(
        (
            n
            for n, op in opcoes.items()
            if op.item.item_id == avaliacao.item.item_id
            and op.slot == avaliacao.slot
            and op.catalisado == quer_cat
        ),
        None,
    )


def escolhas_por_slot(
    avaliacoes: list[Avaliacao],
    opcoes: dict[str, Opcao],
    conjuntos: Mapping[str, Conjunto],
) -> dict[str, tuple[float, Candidato]]:
    """Melhor opção por slot físico, com o ganho medido que a justificou.

    Anéis e berloques disputam os dois lados: o melhor fica no slot onde foi
    medido, o segundo vai para o outro, e o mesmo item nunca ocupa os dois.
    """
    por_grupo: dict[str, list[tuple[float, str, Candidato]]] = defaultdict(list)
    for avaliacao in avaliacoes:
        if avaliacao.etiqueta == "nao_serve":
            continue
        nome = _nome_vencedor(avaliacao, opcoes)
        if nome is None or nome not in conjuntos:
            continue
        slot = opcoes[nome].slot
        candidato = conjuntos[nome].itens[slot]
        grupo = PARES.get(slot, slot)
        por_grupo[grupo].append((avaliacao.ganho_escolhido, slot, candidato))

    escolhas: dict[str, tuple[float, Candidato]] = {}
    for grupo, lista in por_grupo.items():
        lista.sort(key=lambda t: -t[0])
        if grupo not in ("finger", "trinket"):
            ganho, slot, candidato = lista[0]
            escolhas[slot] = (ganho, candidato)
            continue
        livres = [f"{grupo}1", f"{grupo}2"]
        usados: set[int | None] = set()
        for ganho, slot, candidato in lista:
            if not livres:
                break
            if candidato.item_id in usados:
                continue
            destino = slot if slot in livres else livres[0]
            livres.remove(destino)
            usados.add(candidato.item_id)
            escolhas[destino] = (ganho, candidato.model_copy(update={"slot": destino}))
    return escolhas


def melhores_por_slot(
    avaliacoes: list[Avaliacao],
    opcoes: dict[str, Opcao],
    conjuntos: Mapping[str, Conjunto],
) -> dict[str, Candidato]:
    """Melhor opção por slot (etiqueta != nao_serve), para montar o conjunto."""
    return {
        slot: candidato
        for slot, (_, candidato) in escolhas_por_slot(avaliacoes, opcoes, conjuntos).items()
    }


def montar_conjunto(base: Conjunto, escolhas: dict[str, Candidato]) -> Conjunto:
    """Conjunto completo: base com os slots escolhidos trocados."""
    itens = dict(base.itens)
    itens.update(escolhas)
    return base.model_copy(update={"itens": itens})


def montar_valido(
    base: Conjunto,
    escolhas: dict[str, tuple[float, Candidato]],
    ctx: ContextoSpec,
) -> tuple[Conjunto, list[tuple[str, float, Candidato]], list[tuple[str, list[str]]]]:
    """Monta e tira a troca de menor ganho até ``constraints.validar`` aceitar.

    Se o equipado já quebra alguma regra (ex.: dois berloques de uso), só os
    problemas NOVOS contam. Devolve o conjunto, as trocas mantidas em ordem de
    ganho e as descartadas com o motivo.
    """
    _, motivos_base = validar(base, ctx)
    ja_existiam = set(motivos_base)
    restantes = dict(escolhas)
    descartadas: list[tuple[str, list[str]]] = []
    while True:
        conjunto = montar_conjunto(base, {s: c for s, (_, c) in restantes.items()})
        ok, motivos = validar(conjunto, ctx)
        novos = [m for m in motivos if m not in ja_existiam]
        if ok or not novos or not restantes:
            break
        pior = min(restantes, key=lambda s: restantes[s][0])
        descartadas.append((pior, novos))
        del restantes[pior]
    trocas = sorted(
        ((s, g, c) for s, (g, c) in restantes.items()), key=lambda t: -t[1]
    )
    return conjunto, trocas, descartadas


# ------------------------------------------------------------------ execução


@dataclass
class ResultadoBuild:
    nome: str
    codigo: str | None
    cenario: str
    ref_dps: float | None
    avaliacoes: list[Avaliacao]
    conjunto: Conjunto
    trocas: list[tuple[str, float, Candidato]]
    delta_conjunto: float | None
    limiar_conjunto: float | None
    avisos: list[str] = field(default_factory=list)


def rodar_build(
    base: Conjunto,
    conjuntos: dict[str, Conjunto],
    opcoes: dict[str, Opcao],
    *,
    nome: str,
    codigo: str | None,
    cenario: str,
    ctx: ContextoSpec,
    simular: Simulador,
    it_triagem: int,
    it_refino: int,
) -> ResultadoBuild:
    """Triagem, refino, montagem e confirmação de UMA build (até 3 execuções)."""
    com_build = conjuntos_da_build(base, codigo, conjuntos)
    ref = com_build["ref"]

    leitura = simular(com_build, it_triagem)                            # execução 1
    triagem = avaliar(leitura, opcoes, referencia="ref")
    ref_dps = leitura.resultados.get("ref")

    vivos = {a.item.item_id for a in triagem if a.ganho > -a.limiar_cru}
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    avaliacoes = triagem
    if nomes:
        leitura = simular({"ref": ref, **{n: com_build[n] for n in nomes}}, it_refino)  # 2
        refino = avaliar(leitura, {n: opcoes[n] for n in nomes}, referencia="ref")
        ref_dps = leitura.resultados.get("ref", ref_dps)
        refinados = {a.item.item_id for a in refino}
        avaliacoes = refino + [a for a in triagem if a.item.item_id not in refinados]

    escolhas = escolhas_por_slot(avaliacoes, opcoes, com_build)
    montado, trocas, descartadas = montar_valido(ref, escolhas, ctx)
    avisos = [
        f"{slot}: troca retirada na montagem ({'; '.join(motivos)})"
        for slot, motivos in descartadas
    ]
    if not trocas:
        return ResultadoBuild(nome, codigo, cenario, ref_dps, avaliacoes, montado, [], 0.0, None, avisos)

    confirmacao = simular({"ref": ref, "montado": montado}, it_refino)  # execução 3
    r = confirmacao.resultados.get("ref")
    m = confirmacao.resultados.get("montado")
    if not r or m is None:
        avisos.append("A execução de confirmação não trouxe o DPS do conjunto montado.")
        return ResultadoBuild(nome, codigo, cenario, ref_dps, avaliacoes, montado, trocas, None, None, avisos)
    delta = 100.0 * (m - r) / r
    limiar = _limiar_por_erro(
        LIMIAR_PCT, confirmacao.erros.get("ref"), confirmacao.erros.get("montado")
    )
    return ResultadoBuild(nome, codigo, cenario, r, avaliacoes, montado, trocas, delta, limiar, avisos)


# ------------------------------------------------------------------ matriz


def _por_item(por_build: Mapping[str, list[Avaliacao]]) -> dict[int, dict[str, Avaliacao]]:
    saida: dict[int, dict[str, Avaliacao]] = defaultdict(dict)
    for build, avaliacoes in por_build.items():
        for a in avaliacoes:
            saida[a.item.item_id][build] = a
    return saida


def matriz_builds(
    por_build: Mapping[str, list[Avaliacao]], pesos: Mapping[str, float]
) -> list[dict]:
    """Uma linha por item: % por build (versão escolhida), média e divergência."""
    normal = pesos_normalizados(list(por_build), pesos)
    linhas: list[dict] = []
    for item_id, por in _por_item(por_build).items():
        deltas = {b: a.ganho_escolhido for b, a in por.items()}
        limiares = {b: a.limiar_cru for b, a in por.items()}
        qualquer = next(iter(por.values()))
        linhas.append(
            {
                "item_id": item_id,
                "item": qualquer.item,
                "slot": qualquer.slot,
                "deltas": deltas,
                "limiares": limiares,
                "etiquetas": {b: a.etiqueta for b, a in por.items()},
                "media_pct": media_ponderada(deltas, normal),
                "divergente": divergente(deltas, limiares),
            }
        )
    linhas.sort(key=lambda l: -l["media_pct"])
    return linhas


def avaliacoes_medias(
    por_build: Mapping[str, list[Avaliacao]], pesos: Mapping[str, float]
) -> list[Avaliacao]:
    """Avaliação "do conjunto de builds": deltas e limiares pela média ponderada.

    É o que alimenta o ranking das masmorras no modo builds: "serve" passa a
    significar "serve, na média, para as builds que você joga".
    """
    normal = pesos_normalizados(list(por_build), pesos)
    saida: list[Avaliacao] = []
    for por in _por_item(por_build).values():
        w = {b: normal[b] for b in por}

        def media(valores: dict[str, float]) -> float:
            return media_ponderada(valores, w)

        qualquer = next(iter(por.values()))
        tem_cat = all(a.delta_cat is not None for a in por.values())
        saida.append(
            Avaliacao(
                qualquer.item,
                media({b: a.delta_cru for b, a in por.items()}),
                media({b: a.limiar_cru for b, a in por.items()}),
                media({b: a.delta_cat for b, a in por.items()}) if tem_cat else None,
                media({b: a.limiar_cat or a.limiar_cru for b, a in por.items()}) if tem_cat else None,
                qualquer.slot,
                qualquer.ilvl,
            )
        )
    return saida
