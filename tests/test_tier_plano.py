"""T23: plano de 4 peças de tier medido junto (bônus de conjunto entra no número)."""

from __future__ import annotations

import pytest

from wowsim.data import tier as dados_tier
from wowsim.data import trilhas
from wowsim.masmorras.avaliar import Avaliacao
from wowsim.masmorras.catalogo import ItemDeMasmorra
from wowsim.masmorras.tier import plano_tier
from wowsim.topgear.models import Candidato, Conjunto
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit

CLASSE = "druid"
IDS = dados_tier.conjunto_da_classe(CLASSE).slots  # head/shoulder/chest/hands/legs -> ids


def _base(com_tier: tuple[str, ...]) -> Conjunto:
    itens = {}
    for i, slot in enumerate(("head", "shoulder", "chest", "hands", "legs")):
        item_id = IDS[slot][0] if slot in com_tier else 1000 + i
        itens[slot] = Candidato(slot=slot, item_id=item_id, fonte="x")
    return Conjunto(itens=itens)


def _av(item_id: int, slot: str, masmorra: str, d_cat: float) -> Avaliacao:
    return Avaliacao(ItemDeMasmorra(item_id, f"Item {item_id}", slot, masmorra, "x", None), 0.0, 0.15, d_cat, 0.15, slot)


class _Sim:
    """+1% por peça trocada; +5% extra quando o conjunto tem 4 peças de tier."""

    def __init__(self) -> None:
        self.chamadas = 0

    def __call__(self, conjuntos, it):
        self.chamadas += 1
        ids = dados_tier.ids_tier(CLASSE)
        r = {}
        for nome, c in conjuntos.items():
            n = sum(1 for x in c.itens.values() if x.item_id in ids)
            trocas = sum(1 for x in c.itens.values() if x.redirected_base_stats)
            r[nome] = 100.0 + trocas + (5.0 if n >= 4 else 0.0)
        return LeituraSim(base_dps=100.0, resultados=r)


def test_com_tres_pecas_mede_cada_quarta_peca_com_o_bonus() -> None:
    base = _base(("head", "shoulder", "legs"))
    avs = [_av(10, "chest", "Templo", 2.0), _av(11, "chest", "Murder Row", 3.0), _av(12, "hands", "Descanso", 1.0)]
    sim = _Sim()
    plano = plano_tier(base, avs, classe=CLASSE, degrau=trilhas.degrau("heroi", 6), simular=sim, iteracoes=100)
    assert plano["faltam"] == 1 and plano["ja_equipadas"] == ["head", "legs", "shoulder"]
    assert len(plano["combinacoes"]) == 2 and sim.chamadas == 1  # tudo numa leitura (P4)
    melhor = plano["melhor"]
    assert melhor["ganho_pct"] == pytest.approx(6.0)  # 1 troca + bônus de 4 peças
    # Fonte do peito = a de maior delta_cat (Murder Row)
    peito = next(c for c in plano["combinacoes"] if c["slots"] == ["chest"])
    assert peito["pecas"][0]["masmorra"] == "Murder Row"
    assert plano["masmorras_do_plano"] in ({"Murder Row": 1}, {"Descanso": 1})


def test_sem_tier_precisa_de_quatro_e_usa_o_nivel_pedido() -> None:
    base = _base(())
    avs = [_av(10 + i, s, f"D{i}", 1.0) for i, s in enumerate(("head", "shoulder", "chest", "hands", "legs"))]
    plano = plano_tier(base, avs, classe=CLASSE, degrau=trilhas.degrau("mito", 4), simular=_Sim(), iteracoes=100)
    assert plano["faltam"] == 4 and len(plano["combinacoes"]) == 5  # C(5,4)
    assert plano["melhor"]["conversoes"] == 4
    assert plano["nivel"] == "Mito 4/6 (328)"


def test_faltam_fontes() -> None:
    base = _base(())
    plano = plano_tier(base, [_av(10, "chest", "D", 1.0)], classe=CLASSE, degrau=trilhas.degrau("mito", 6), simular=_Sim(), iteracoes=10)
    assert plano["combinacoes"] == [] and "Faltam 4" in plano["motivo"]
    assert set(plano["sem_fonte"]) == {"head", "shoulder", "hands", "legs"}


def test_ja_tem_quatro() -> None:
    plano = plano_tier(_base(("head", "shoulder", "chest", "legs")), [], classe=CLASSE,
                       degrau=trilhas.degrau("mito", 6), simular=_Sim(), iteracoes=10)
    assert plano["faltam"] == 0 and "já usa 4" in plano["motivo"]
