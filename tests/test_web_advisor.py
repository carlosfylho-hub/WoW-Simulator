"""Tactical advisor: Gemini parsing plus local fallback behaviour."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import advisor  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit


def test_extrair_texto_de_resposta_valida() -> None:
    resposta = {
        "candidates": [
            {"content": {"parts": [{"text": "Olá "}, {"text": "mundo"}]}}
        ]
    }
    assert advisor.extrair_texto(resposta) == "Olá mundo"


def test_extrair_texto_invalido_retorna_none() -> None:
    assert advisor.extrair_texto({}) is None
    assert advisor.extrair_texto({"candidates": []}) is None


def test_advisor_sem_chave_usa_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/api/advisor",
            json={"prompt": "Qual masmorra priorizar?", "specId": "shadow"},
        )
    assert resposta.status_code == 200
    texto = resposta.json()["response"]
    assert "Consultor Local" in texto
    assert "Sacerdote das Sombras" in texto
    assert "Altar das Presas" in texto


def test_advisor_usa_gemini_quando_disponivel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "chave-teste")

    async def falso_chamar_gemini(*args, **kwargs):
        return "Resposta vinda do modelo."

    monkeypatch.setattr(advisor, "chamar_gemini", falso_chamar_gemini)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/advisor", json={"prompt": "oi"})
    assert resposta.status_code == 200
    assert resposta.json()["response"] == "Resposta vinda do modelo."


def test_advisor_cai_no_fallback_quando_gemini_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "chave-teste")

    async def falso_chamar_gemini(*args, **kwargs):
        return None

    monkeypatch.setattr(advisor, "chamar_gemini", falso_chamar_gemini)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/advisor", json={"prompt": "oi", "specId": "balance"})
    assert resposta.status_code == 200
    assert "Consultor Local" in resposta.json()["response"]


def test_advisor_prompt_vazio_retorna_422() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/advisor", json={"prompt": ""})
    assert resposta.status_code == 422
