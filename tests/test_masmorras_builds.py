"""T9 (núcleo): funções puras da comparação por build."""

from __future__ import annotations

import pytest

from wowsim.masmorras.builds import (
    cenario_da_build,
    conjuntos_da_build,
    divergente,
    media_ponderada,
)
from wowsim.topgear.models import Candidato, Conjunto

pytestmark = pytest.mark.unit


def _conjunto(item_id: int) -> Conjunto:
    return Conjunto(
        itens={"head": Candidato(slot="head", item_id=item_id, fonte="teste")}
    )


def test_conjuntos_da_build_aplica_talentos_em_ref_e_candidatos() -> None:
    base = _conjunto(1)
    candidatos = {"c_10_head": _conjunto(10), "c_11_head": _conjunto(11)}
    saida = conjuntos_da_build(base, "CODIGO", candidatos)

    assert set(saida) == {"ref", "c_10_head", "c_11_head"}
    assert all(conjunto.talentos == "CODIGO" for conjunto in saida.values())
    assert saida["ref"].item_id("head") == 1
    assert saida["c_10_head"].item_id("head") == 10
    # A base original não é mutada.
    assert base.talentos is None


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("single icy", "patchwerk"),
        ("raid maxroll", "patchwerk"),
        ("Single Target", "patchwerk"),
        ("m+ icy", "dungeon_slice"),
        ("Diabolist Delves", "dungeon_slice"),
        ("delves icy", "dungeon_slice"),
    ],
)
def test_cenario_da_build(nome: str, esperado: str) -> None:
    assert cenario_da_build(nome) == esperado


def test_media_ponderada() -> None:
    deltas = {"a": 2.0, "b": 0.0}
    assert media_ponderada(deltas, {"a": 0.75, "b": 0.25}) == pytest.approx(1.5)


def test_media_ponderada_pesos_zerados_levanta() -> None:
    with pytest.raises(ValueError):
        media_ponderada({"a": 1.0}, {"a": 0.0})


def test_divergente_ganho_numa_build_e_perda_em_outra() -> None:
    limiares = {"a": 0.15, "b": 0.15}
    assert divergente({"a": 1.0, "b": -1.0}, limiares) is True
    assert divergente({"a": 1.0, "b": 0.5}, limiares) is False
    assert divergente({"a": 0.1, "b": -0.1}, limiares) is False
