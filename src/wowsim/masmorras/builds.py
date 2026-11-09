"""Comparação por build (loadout): cenário por nome, média ponderada, divergência.

P4 preservado: a referência de cada build é um profileset ``ref`` (a base com os
talentos daquela build) medido NA MESMA leitura em que os candidatos são medidos.
"""

from __future__ import annotations

from ..topgear.models import Candidato, Conjunto
from .avaliar import Avaliacao, Opcao


def conjuntos_da_build(
    base: Conjunto, codigo: str, conjuntos: dict[str, Conjunto]
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


def melhores_por_slot(
    avaliacoes: list[Avaliacao],
    opcoes: dict[str, Opcao],
    conjuntos: dict[str, Conjunto],
) -> dict[str, Candidato]:
    """Melhor opção por slot (etiqueta != nao_serve), para montar o conjunto."""
    melhor: dict[str, tuple[float, Candidato]] = {}
    for avaliacao in avaliacoes:
        if avaliacao.etiqueta == "nao_serve":
            continue
        nome = next(
            (
                n
                for n, op in opcoes.items()
                if op.item.item_id == avaliacao.item.item_id and op.slot == avaliacao.slot
            ),
            None,
        )
        if nome is None:
            continue
        candidato = conjuntos[nome].itens[opcoes[nome].slot]
        if avaliacao.slot not in melhor or avaliacao.ganho > melhor[avaliacao.slot][0]:
            melhor[avaliacao.slot] = (avaliacao.ganho, candidato)
    return {slot: candidato for slot, (_, candidato) in melhor.items()}


def montar_conjunto(base: Conjunto, escolhas: dict[str, Candidato]) -> Conjunto:
    """Conjunto completo: base com os slots escolhidos trocados."""
    itens = dict(base.itens)
    itens.update(escolhas)
    return base.model_copy(update={"itens": itens})
