"""A-03: cada lote de profilesets tem a sua própria base; o delta não as mistura."""

from __future__ import annotations

import pytest

from wowsim.topgear.models import Conjunto
from wowsim.topgear.runner import LeituraSim
from wowsim.topgear.search import _simular_em_chunks

pytestmark = pytest.mark.unit


def test_delta_contra_a_base_do_proprio_lote() -> None:
    chamadas = {"n": 0}

    def simulador(conjuntos, iterations):
        if not conjuntos:
            return LeituraSim(base_dps=None, resultados={})
        chamadas["n"] += 1
        base = 100.0 + 10.0 * chamadas["n"]  # base DIFERENTE por lote: 110, 120, 130...
        return LeituraSim(
            base_dps=base,
            resultados={nome: base * 1.10 for nome in conjuntos},  # sempre +10%
        )

    conjuntos = {f"c{i}": Conjunto() for i in range(5)}
    leitura = _simular_em_chunks(simulador, conjuntos, 10, limite=2)

    assert leitura.base_dps == pytest.approx(110.0)
    for nome, dps in leitura.resultados.items():
        delta = 100.0 * (dps - leitura.base_dps) / leitura.base_dps
        assert delta == pytest.approx(10.0), nome
