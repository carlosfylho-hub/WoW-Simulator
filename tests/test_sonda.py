"""P-051 (A4): sonda de atributos das peças craftadas via players[i].gear."""

from __future__ import annotations

import pytest

from wowsim.masmorras import craft, sonda
from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit


def test_stats_do_gear_le_chaves_do_simc() -> None:
    gear = {
        "id": 239656,
        "ilevel": 331,
        "intellect": 1404,
        "stamina": 2000,
        "crit_rating": 812,
        "haste_rating": 640,
    }
    assert sonda.stats_do_gear(gear) == {
        "intellect": 1404,
        "stamina": 2000,
        "crit": 812,
        "haste": 640,
    }


def test_stats_do_gear_aceita_bloco_aninhado_stats() -> None:
    gear = {"stats": {"mastery_rating": 500, "versatility_rating": 300}}
    assert sonda.stats_do_gear(gear) == {"mastery": 500, "versatility": 300}


def test_stats_das_players_mapeia_por_copy() -> None:
    players = [
        {"gear": {}},  # original
        {"gear": {"shoulder": {"intellect": 1000, "crit_rating": 400}}},
    ]
    candidatos = {"x": Candidato(slot="shoulder", item_id=1, fonte="craft")}
    assert sonda.stats_das_players(players, candidatos) == {
        "x": {"intellect": 1000, "crit": 400}
    }


class _SimAtributos:
    """Só fase 1: missiva Ace+Mae no ombro vale 1%."""

    def __call__(self, conjuntos, iterations):
        return LeituraSim(
            base_dps=100.0,
            resultados={n: 100.0 + (1.0 if _tem_missiva(c) else 0.0) for n, c in conjuntos.items()},
        )


def _tem_missiva(conjunto) -> bool:
    return any(c.crafted_stats == [36, 49] for c in conjunto.itens.values())


def test_rodar_craft_anexa_stats_da_sonda_as_pecas() -> None:
    base = Conjunto(itens={})
    item = craft.ItemCraft(244572, "Dragonas", "Mantle", "shoulder", False)
    capturado: dict = {}

    def sondar(alvo):
        capturado.update(alvo)
        return {nome: {"intellect": 1404, "haste": 640} for nome in alvo}

    r = craft.rodar_craft(
        base,
        [item],
        ctx=ContextoSpec(),
        simular=_SimAtributos(),
        it_triagem=10,
        it_refino=10,
        sondar=sondar,
    )
    assert capturado  # a sonda recebeu o candidato do ombro
    assert r.pecas[0]["stats"] == {"intellect": 1404, "haste": 640}
