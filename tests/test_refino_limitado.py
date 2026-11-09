"""Refino só dos melhores da triagem (o resto fica com a medição da triagem)."""

from __future__ import annotations

import pytest

from wowsim.masmorras.avaliar import Avaliacao, Opcao, itens_para_refinar
from wowsim.masmorras.catalogo import ItemDeMasmorra

pytestmark = pytest.mark.unit


def _av(item_id: int, ganho: float, limiar: float = 0.5) -> Avaliacao:
    return Avaliacao(ItemDeMasmorra(item_id, None, "head", "D", "x", None), ganho, limiar)


def test_refina_os_melhores_ate_o_maximo() -> None:
    triagem = [_av(i, g) for i, g in [(1, 2.0), (2, -0.2), (3, 0.9), (4, -3.0), (5, 0.1)]]
    assert itens_para_refinar(triagem, maximo=2) == {1, 3}


def test_perdedores_claros_nunca_entram() -> None:
    triagem = [_av(1, -3.0), _av(2, -0.4)]
    assert itens_para_refinar(triagem, maximo=10) == {2}
