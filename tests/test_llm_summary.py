"""LLM summary tests with a fake client. No network and no API key."""

from __future__ import annotations


import pytest

from wowsim.llm import summary
from wowsim.models import Variacao
from wowsim.simc_runner import ResultadoDps, SimcResultado

pytestmark = pytest.mark.unit


def _contexto() -> dict:
    base = ResultadoDps(nome="base", dps=200_000.0, erro_abs=400.0, eh_base=True)
    variacoes = [
        Variacao(
            nome="up_head",
            categoria="upgrade",
            linhas_override=["head=,id=271546,bonus_id=12854"],
            item_ids=[271546],
            fonte="bonus_ids_s2.json",
        )
    ]
    resultado = SimcResultado(
        json_path=None,  # type: ignore[arg-type]
        base=base,
        variacoes=(ResultadoDps(nome="up_head", dps=204_280.0, erro_abs=500.0),),
    )
    return summary.montar_contexto(
        resultado, variacoes, iterations=1000, fight_style="DungeonSlice"
    )


def test_contexto_tem_base_e_delta() -> None:
    contexto = _contexto()
    assert contexto["base_dps"] == 200_000.0
    assert contexto["variacoes"][0]["delta_pct"] == 2.14
    assert contexto["variacoes"][0]["veredito"] == "ganho"


def test_fallback_deterministico() -> None:
    texto = summary.resumo_deterministico(_contexto())
    assert "200.000 DPS" in texto
    assert "up_head" in texto
    assert "Números medidos" in texto
