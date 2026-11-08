"""Cheap, deterministic candidate scoring used only to prune before SimC.

Golden rule: this module NEVER produces DPS. It ranks candidates by the weighted
sum of their secondary stats (optionally with item level as a tie-breaker) so the
staged search can hand a small top-K per slot to SimulationCraft. Every score is
a ``heuristico=True`` estimate and must never be shown as damage.

Missing stats are treated conservatively: a candidate whose stats are unknown is
never pruned, because it may win through a proc or effect we cannot model here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Mapping

from ..data import catalog

if TYPE_CHECKING:
    from ..topgear.models import Candidato

# Secondary attributes produced by ``catalog.stats_item`` (English keys).
SECUNDARIOS = ("haste", "crit", "mastery", "versatility")
# Attributes that never drive pruning: primary stat is spec-defined and stamina
# is survivability, not throughput.
_IGNORAR = ("stamina", "intellect", "strength", "agility")

# Slots whose value can come from on-use/proc effects that stats cannot capture.
SLOTS_SEMPRE_PRESERVADOS = frozenset(
    {
        "trinket1",
        "trinket2",
        "main_hand",
        "off_hand",
        "talentos",
        "folio",
        "flask",
        "potion",
        "food",
        "augmentation",
    }
)


@dataclass(frozen=True)
class PontuacaoCandidato:
    """A pruning score. ``heuristico`` is always True; never a DPS number."""

    candidato: Candidato
    score: float
    breakdown: dict[str, float]
    fonte_pesos: str
    heuristico: bool = True


@dataclass(frozen=True)
class PodaResultado:
    """Kept candidates per slot plus what was dropped, for transparency."""

    mantidos: dict[str, list[Candidato]]
    descartados: int
    detalhe: dict[str, int] = field(default_factory=dict)
    # Dropped candidates per slot, kept so an optional verification stage can
    # re-measure them and recover a gain the heuristic might have missed.
    descartados_itens: dict[str, list[Candidato]] = field(default_factory=dict)


def _stats(candidato: Candidato) -> dict[str, int]:
    """Candidate stats, falling back to the catalog when not pre-enriched."""
    if candidato.stats:
        return candidato.stats
    if candidato.item_id is not None:
        return catalog.stats_item(candidato.item_id)
    return {}


def pontuar_candidato(
    candidato: Candidato,
    pesos: Mapping[str, float],
    *,
    fonte: str = "pesos_secundarios.json",
) -> PontuacaoCandidato:
    """Weighted secondary-stat score. Pure: no catalog lookup beyond stats."""
    stats = _stats(candidato)
    breakdown: dict[str, float] = {}
    score = 0.0
    for chave, valor in stats.items():
        if chave in _IGNORAR:
            continue
        multiplicador = pesos.get(chave)
        if multiplicador is None or not valor:
            continue
        contribuicao = float(valor) * float(multiplicador)
        breakdown[chave] = contribuicao
        score += contribuicao
    return PontuacaoCandidato(
        candidato=candidato,
        score=score,
        breakdown=breakdown,
        fonte_pesos=fonte,
    )


def _deve_preservar(candidato: Candidato, slot: str) -> bool:
    """Candidates that must never be pruned (effects, weapons, unknown stats)."""
    if slot in SLOTS_SEMPRE_PRESERVADOS:
        return True
    if candidato.tipo_efeito:
        return True
    if not _stats(candidato):
        return True
    return False


def _chave_ordenacao(p: PontuacaoCandidato) -> tuple[float, int, int]:
    cand = p.candidato
    return (p.score, cand.ilvl or 0, cand.item_id or 0)


def _dedupe(lista: Iterable[Candidato]) -> list[Candidato]:
    vistos: set[tuple] = set()
    saida: list[Candidato] = []
    for cand in lista:
        chave = (
            cand.slot,
            cand.item_id,
            cand.redirected_base_stats,
            cand.ilvl,
            tuple(cand.bonus_ids),
            cand.enchant_id,
        )
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(cand)
    return saida


def podar_por_slot(
    candidatos_por_slot: Mapping[str, list[Candidato]],
    pesos: Mapping[str, float],
    top_k: int,
    *,
    fonte: str = "pesos_secundarios.json",
) -> PodaResultado:
    """Keep a top-K per slot, always preserving effect/weapon/unknown-stat items.

    ``top_k`` counts only the *scored* candidates; preserved candidates are
    added on top, so a slot can legitimately keep more than ``top_k``. A
    non-positive ``top_k`` disables pruning for that batch.
    """
    mantidos: dict[str, list[Candidato]] = {}
    descartados = 0
    detalhe: dict[str, int] = {}
    descartados_itens: dict[str, list[Candidato]] = {}

    for slot, lista in candidatos_por_slot.items():
        if top_k <= 0:
            mantidos[slot] = list(lista)
            continue

        preservados: list[Candidato] = []
        pontuaveis: list[Candidato] = []
        for cand in lista:
            if _deve_preservar(cand, slot):
                preservados.append(cand)
            else:
                pontuaveis.append(cand)

        if len(pontuaveis) <= top_k:
            mantidos[slot] = _dedupe(preservados + pontuaveis)
            continue

        pontuados = sorted(
            (pontuar_candidato(c, pesos, fonte=fonte) for c in pontuaveis),
            key=_chave_ordenacao,
            reverse=True,
        )
        top = [p.candidato for p in pontuados[:top_k]]
        removidos = [p.candidato for p in pontuados[top_k:]]
        descartados += len(removidos)
        detalhe[slot] = len(removidos)
        descartados_itens[slot] = removidos
        mantidos[slot] = _dedupe(preservados + top)

    return PodaResultado(
        mantidos=mantidos,
        descartados=descartados,
        detalhe=detalhe,
        descartados_itens=descartados_itens,
    )
