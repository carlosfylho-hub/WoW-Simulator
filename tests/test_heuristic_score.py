"""Unit tests for the heuristic pruner. No SimulationCraft is involved."""

from __future__ import annotations

from wowsim.data import pesos as pesos_mod
from wowsim.heuristic.score import (
    PontuacaoCandidato,
    podar_por_slot,
    pontuar_candidato,
)
from wowsim.topgear.models import Candidato


def _cand(slot: str, item_id: int, ilvl: int, stats: dict[str, int], **extra) -> Candidato:
    return Candidato(
        slot=slot,
        item_id=item_id,
        ilvl=ilvl,
        fonte="teste",
        stats=stats,
        **extra,
    )


def test_score_e_soma_ponderada_dos_secundarios() -> None:
    cand = _cand("chest", 1, 330, {"haste": 100, "crit": 50, "stamina": 999})
    pesos = {"haste": 1.0, "crit": 0.5, "mastery": 0.9}
    p = pontuar_candidato(cand, pesos, fonte="teste")
    assert isinstance(p, PontuacaoCandidato)
    assert p.heuristico is True
    assert p.score == 100 * 1.0 + 50 * 0.5
    assert p.breakdown["haste"] == 100.0
    assert "stamina" not in p.breakdown
    assert p.fonte_pesos == "teste"


def test_score_sem_stats_e_zero_mas_preservado() -> None:
    cand = _cand("chest", 2, 330, {})
    p = pontuar_candidato(cand, {"haste": 1.0})
    assert p.score == 0.0
    poda = podar_por_slot({"chest": [cand]}, {"haste": 1.0}, top_k=1)
    assert cand in poda.mantidos["chest"]
    assert poda.descartados == 0


def test_poda_mantem_top_k_e_descarta_resto() -> None:
    lista = [
        _cand("chest", 10, 330, {"haste": 100}),
        _cand("chest", 11, 330, {"haste": 50}),
        _cand("chest", 12, 330, {"haste": 10}),
        _cand("chest", 13, 330, {"haste": 1}),
    ]
    poda = podar_por_slot({"chest": lista}, {"haste": 1.0}, top_k=2)
    mantidos = [c.item_id for c in poda.mantidos["chest"]]
    assert mantidos[0] == 10
    assert mantidos[1] == 11
    assert poda.descartados == 2
    assert poda.detalhe["chest"] == 2


def test_poda_preserva_berloques_e_armas() -> None:
    trinkets = [
        _cand("trinket1", 20, 330, {"haste": 1}),
        _cand("trinket1", 21, 330, {"haste": 2}),
        _cand("trinket1", 22, 330, {"haste": 3}),
    ]
    armas = [
        _cand("main_hand", 30, 330, {"haste": 1}),
        _cand("main_hand", 31, 330, {"haste": 2}),
    ]
    poda = podar_por_slot(
        {"trinket1": trinkets, "main_hand": armas}, {"haste": 1.0}, top_k=1
    )
    assert len(poda.mantidos["trinket1"]) == 3
    assert len(poda.mantidos["main_hand"]) == 2
    assert poda.descartados == 0


def test_poda_preserva_item_com_efeito() -> None:
    com_efeito = _cand("chest", 40, 330, {"haste": 1}, tipo_efeito="ativo")
    normal = _cand("chest", 41, 330, {"haste": 100})
    outro = _cand("chest", 42, 330, {"haste": 90})
    poda = podar_por_slot({"chest": [com_efeito, normal, outro]}, {"haste": 1.0}, top_k=1)
    ids = [c.item_id for c in poda.mantidos["chest"]]
    assert 40 in ids  # efeito sempre preservado
    assert 41 in ids  # melhor por score
    assert 42 not in ids


def test_top_k_zero_desliga_poda() -> None:
    lista = [_cand("chest", 50, 330, {"haste": 5}), _cand("chest", 51, 330, {"haste": 1})]
    poda = podar_por_slot({"chest": lista}, {"haste": 1.0}, top_k=0)
    assert len(poda.mantidos["chest"]) == 2
    assert poda.descartados == 0


def test_pesos_por_spec_classe_e_padrao() -> None:
    pesos_mod.limpar_cache()
    spec = pesos_mod.pesos_para("Bruxo", "Demonology")
    assert spec.conhecido is True
    assert spec.fonte.endswith("spec:demonology")
    assert spec.valores["haste"] == 1.0

    classe = pesos_mod.pesos_para("Druida", "SpecInexistente")
    assert classe.conhecido is True
    assert classe.fonte.endswith("classe:druida")

    padrao = pesos_mod.pesos_para("ClasseX", "SpecY")
    assert padrao.fonte.endswith("padrao")
    assert "haste" in padrao.valores
