"""T6: motor do ranking de masmorras (etiquetas, delta por leitura, ordens)."""

from __future__ import annotations

import pytest

from wowsim.masmorras.avaliar import (
    Avaliacao,
    Opcao,
    agrupar,
    avaliar,
    montar_opcoes,
    ordenar,
)
from wowsim.masmorras.catalogo import ItemDeMasmorra
from wowsim.topgear.models import Conjunto
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit


def _item(masmorra: str = "D", slot: str = "head", item_id: int = 100) -> ItemDeMasmorra:
    return ItemDeMasmorra(
        item_id=item_id,
        nome_pt="X",
        slot=slot,
        masmorra=masmorra,
        secao="armadura_tecido_mplus",
        usavel_conjurador=None,
    )


def _avaliar_um(d_cru: float, d_cat: float | None = None) -> Avaliacao:
    item = _item()
    opcoes = {"c": Opcao("c", item, "head", False)}
    resultados = {"c": 100.0 + d_cru}
    if d_cat is not None:
        opcoes["k"] = Opcao("k", item, "head", True)
        resultados["k"] = 100.0 + d_cat
    leitura = LeituraSim(base_dps=100.0, resultados=resultados)
    avaliacoes = avaliar(leitura, opcoes)
    assert len(avaliacoes) == 1
    return avaliacoes[0]


def test_etiquetas_dos_quatro_casos() -> None:
    assert _avaliar_um(2.4).etiqueta == "direto"
    assert _avaliar_um(0.1, 1.9).etiqueta == "catalisar"
    assert _avaliar_um(1.2, 2.6).etiqueta == "ambos"
    assert _avaliar_um(-0.3).etiqueta == "nao_serve"


def test_anel_em_dois_slots_vira_uma_avaliacao_com_o_melhor() -> None:
    item = _item(slot="finger", item_id=200)
    opcoes = {
        "c_finger1": Opcao("c_finger1", item, "finger1", False),
        "c_finger2": Opcao("c_finger2", item, "finger2", False),
    }
    leitura = LeituraSim(base_dps=100.0, resultados={"c_finger1": 101.0, "c_finger2": 103.0})
    avaliacoes = avaliar(leitura, opcoes)
    assert len(avaliacoes) == 1
    assert avaliacoes[0].delta_cru == pytest.approx(3.0)
    assert avaliacoes[0].slot == "finger2"


def test_delta_usa_a_base_da_propria_leitura() -> None:
    item = _item()
    opcoes = {"c": Opcao("c", item, "head", False)}
    l1 = LeituraSim(base_dps=100.0, resultados={"c": 110.0})
    l2 = LeituraSim(base_dps=200.0, resultados={"c": 210.0})
    assert avaliar(l1, opcoes)[0].delta_cru == pytest.approx(10.0)
    assert avaliar(l2, opcoes)[0].delta_cru == pytest.approx(5.0)


def _av(item_id: int, masmorra: str, delta: float) -> Avaliacao:
    return Avaliacao(_item(masmorra=masmorra, item_id=item_id), delta, 0.15)


def test_ordenar_por_quantidade_e_por_maior() -> None:
    avaliacoes = [
        _av(1, "Altar das Presas", 1.0),
        _av(2, "Altar das Presas", 1.2),
        _av(3, "Altar das Presas", 0.8),
        _av(4, "Murder Row", 5.0),
    ]
    linhas = agrupar(avaliacoes, {})
    assert ordenar(linhas, por="quantidade")[0]["masmorra"] == "Altar das Presas"
    assert ordenar(linhas, por="maior")[0]["masmorra"] == "Murder Row"


def test_montar_opcoes_ilvl_invalido_levanta() -> None:
    with pytest.raises(ValueError):
        montar_opcoes(Conjunto(), [_item()], ilvl=999, classe="warlock")
