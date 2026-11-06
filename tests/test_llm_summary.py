"""LLM summary tests with a fake client. No network and no API key."""

from __future__ import annotations

from types import SimpleNamespace

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


class _FakeCompletions:
    def __init__(self, texto: str) -> None:
        self.texto = texto

    def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))]
        )


class _FakeCliente:
    def __init__(self, texto: str) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(texto))


def test_contexto_tem_base_e_delta() -> None:
    contexto = _contexto()
    assert contexto["base_dps"] == 200_000.0
    assert contexto["variacoes"][0]["delta_pct"] == 2.14
    assert contexto["variacoes"][0]["veredito"] == "ganho"


def test_aceita_texto_com_numeros_do_contexto() -> None:
    texto = "A base ficou em 200.000 DPS e up_head ganhou 2.14%."
    assert summary.resumir(_contexto(), cliente=_FakeCliente(texto)) == texto


def test_rejeita_numero_inventado() -> None:
    texto = "A base ficou em 200.000 DPS e a troca rendeu 999%."
    assert summary.resumir(_contexto(), cliente=_FakeCliente(texto)) is None


def test_rejeita_texto_longo() -> None:
    texto = "\n".join(["linha"] * 12)
    assert summary.resumir(_contexto(), cliente=_FakeCliente(texto)) is None


def test_sem_chave_retorna_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert summary.resumir(_contexto()) is None


def test_fallback_deterministico() -> None:
    texto = summary.resumo_deterministico(_contexto())
    assert "200.000 DPS" in texto
    assert "up_head" in texto
    assert "Números medidos" in texto
