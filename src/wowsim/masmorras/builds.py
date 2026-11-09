"""Comparação por build (loadout): cenário por nome, média ponderada, divergência.

P4 preservado: a referência de cada build é um profileset ``ref`` (a base com os
talentos daquela build) medido NA MESMA leitura em que os candidatos são medidos.
"""

from __future__ import annotations

from ..topgear.models import Conjunto


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
