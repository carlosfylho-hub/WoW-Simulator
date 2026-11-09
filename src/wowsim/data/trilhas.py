"""Trilhas de upgrade (Herói/Mito), ranks, ilvl, bônus e custo em brasões.

Fonte dos níveis: ``dados/derivados/bonus_ilvl.json`` (Raidbots
``bonus-upgrade-sets``; confere com Method.gg). Custo: 20 brasões da trilha por
etapa (Icy Veins, Midnight S2). Forja do Veneno: só no 6/6 (bônus 12848/12856);
o custo dela (Ascendant Venomstones) não é conhecido e não é estimado.
Ver docs/WORKFLOW-IMPLEMENTACAO.md §8B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from . import catalog

Trilha = Literal["heroi", "mito"]

# Rótulo do bonus_ilvl.json -> chave interna
_TRILHAS = {"Heroi": "heroi", "Herói": "heroi", "Mito": "mito", "Mítico": "mito"}
ROTULO = {"heroi": "Herói", "mito": "Mito"}
MOEDA = {"heroi": "Brasão de Herói", "mito": "Brasão Mítico"}
BRASOES_POR_ETAPA = 20
FORJA = {"heroi": 12848, "mito": 12856}
# Craft no nível Mítico (318–331 pela qualidade): 80 Brasões Míticos — confirmado
# pelo usuário em 2026-11-09 (sem fonte pública encontrada).
BRASOES_CRAFT = {"heroi": 80, "mito": 80}
CENTELHAS_CRAFT = {"armadura_e_uma_mao": 2, "duas_maos": 4}


@dataclass(frozen=True)
class Degrau:
    trilha: Trilha
    rank: int          # 1..6
    ilvl: int
    bonus_id: int
    forja: bool = False

    @property
    def rotulo(self) -> str:
        base = f"{ROTULO[self.trilha]} {self.rank}/6"
        return f"{base} + Forja" if self.forja else base


def escada() -> list[Degrau]:
    """Os degraus Herói e Mito conhecidos (sem a forja), em ordem de ilvl."""
    saida: list[Degrau] = []
    for chave, reg in catalog._derivado("bonus_ilvl.json").get("bonus", {}).items():
        trilha = _TRILHAS.get(str(reg.get("trilha")))
        rank = str(reg.get("rank") or "")
        if trilha and "/" in rank and reg.get("ilvl"):
            saida.append(Degrau(trilha, int(rank.split("/")[0]), int(reg["ilvl"]), int(chave)))
    return sorted(saida, key=lambda d: (d.trilha, d.rank))


def degrau(trilha: Trilha, rank: int, forja: bool = False) -> Degrau:
    """Degrau pedido; a forja só existe no 6/6."""
    if forja:
        if rank != 6:
            raise ValueError("A Forja do Veneno só existe no rank 6/6.")
        bonus = FORJA[trilha]
        ilvl = catalog.bonus_para_ilvl(bonus).ilvl
        if ilvl is None:
            raise ValueError(f"Bônus da forja {bonus} sem ilvl conhecido.")
        return Degrau(trilha, 6, int(ilvl), bonus, forja=True)
    for d in escada():
        if d.trilha == trilha and d.rank == rank:
            return d
    raise ValueError(f"Degrau {ROTULO.get(trilha, trilha)} {rank}/6 não está nos dados.")


# Atalhos antigos do pedido (ilvl): continuam aceitos.
_ATALHOS = {321: ("heroi", 6, False), 328: ("heroi", 6, True), 334: ("mito", 6, False), 341: ("mito", 6, True)}


def degrau_do_ilvl(ilvl: int) -> Degrau:
    if ilvl not in _ATALHOS:
        raise ValueError(f"ilvl {ilvl} é ambíguo ou desconhecido; informe trilha e rank.")
    t, r, f = _ATALHOS[ilvl]
    return degrau(t, r, f)  # type: ignore[arg-type]


def degrau_dos_bonus(bonus_ids: Iterable[int]) -> Degrau | None:
    """Trilha/rank de um item a partir dos bônus dele (forja conta como 6/6)."""
    ids = set(bonus_ids or ())
    for t, b in FORJA.items():
        if b in ids:
            return degrau(t, 6, True)  # type: ignore[arg-type]
    for d in escada():
        if d.bonus_id in ids:
            return d
    return None


def degrau_no_slot(d: Degrau, slot: str | None) -> Degrau:
    """A forja só existe em arma, berloque e colar; nos outros slots vale o 6/6."""
    from . import regras

    if d.forja and not regras.slot_aceita_forja(slot):
        return degrau(d.trilha, 6)
    return d


def custo_upgrade(
    d: Degrau | None, *, slot: str | None = None, marcas: dict[str, int] | None = None
) -> dict | None:
    """Brasões para levar o item do degrau atual ao 6/6 da mesma trilha.

    Desconto da marca do slot (WowCarry): as etapas até o maior nível que o
    personagem já teve naquele slot saem sem brasão. ``marcas`` vem de
    ``slot_high_watermarks`` do export do SimC; sem ele, o custo é o cheio.
    """
    from . import regras

    if d is None:
        return None
    por_etapa = int(regras.upgrade().get("brasoes_por_etapa") or BRASOES_POR_ETAPA)
    topo = degrau(d.trilha, 6)
    if d.forja:  # V-3: forjado já está no máximo
        return {
            "moeda": MOEDA[d.trilha], "brasoes": 0, "etapas": 0, "etapas_gratis": 0,
            "ate": f"{d.rotulo} ({d.ilvl}) — máximo", "forja": regras.custo_forja(),
            "nota": "Forjado: não sobe mais.",
        }
    marca = (marcas or {}).get(slot) if slot else None
    pagas = gratis = 0
    for r in range(d.rank + 1, 7):
        if marca is not None and degrau(d.trilha, r).ilvl <= marca:
            gratis += 1
        else:
            pagas += 1
    if marca is None:
        nota = "Custo cheio (o export não trouxe a marca de nível deste slot)."
    elif gratis:
        nota = f"{gratis} etapa(s) sem brasão: você já teve nível {marca} neste slot."
    else:
        nota = f"Sem desconto: a marca do slot ({marca}) está abaixo das próximas etapas."
    desconto = regras.upgrade().get("desconto_bando_pct")
    if desconto and pagas:
        nota += f" Com a conquista da trilha no bando, cada etapa paga custa {desconto}% menos."
    return {
        "moeda": MOEDA[d.trilha],
        "brasoes": pagas * por_etapa,
        "etapas": pagas + gratis,
        "etapas_gratis": gratis,
        "ate": f"{ROTULO[d.trilha]} 6/6 ({topo.ilvl})",
        "nota": nota,
    }
