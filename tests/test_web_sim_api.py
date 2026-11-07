"""Real SimC bridge and its HTTP routes."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.simc_runner import SimcFalhou, find_simc  # noqa: E402
from wowsim.web import sim_api  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def test_classificar_vale_a_troca() -> None:
    veredito, limiar = sim_api.classificar(1.2, 0.2, 0.3)
    assert veredito == "Vale a troca"
    assert limiar == pytest.approx(0.3)


def test_classificar_empate_tecnico() -> None:
    veredito, limiar = sim_api.classificar(0.05, 0.1, 0.12)
    assert veredito == "Empate técnico — simular"
    assert limiar == pytest.approx(0.15)


def test_classificar_nao_vale() -> None:
    veredito, _ = sim_api.classificar(-2.0, 0.2, 0.2)
    assert veredito == "Não vale"


def test_parametros_cenario_patchwerk_e_mplus() -> None:
    patch = sim_api.parametros_cenario("patchwerk", 100)
    assert patch["fight_style"] == "Patchwerk"
    assert patch["desired_targets"] == 1
    assert patch["iterations"] == 100
    mplus = sim_api.parametros_cenario("mplus", 50)
    assert mplus["fight_style"] == "DungeonSlice"


def test_rota_profile_usa_sim_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sim_api,
        "rodar_perfil",
        lambda *a, **k: {"dps": 1234.5, "erro_pct": 0.1, "amostras": 200, "cenario": "patchwerk", "meta": {}},
    )
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/sim/profile", json={"profile": "x" * 40, "iterations": 50})
    assert resposta.status_code == 200
    assert resposta.json()["dps"] == pytest.approx(1234.5)


def test_rota_compare_usa_sim_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sim_api,
        "comparar",
        lambda *a, **k: {
            "cenario": "patchwerk",
            "base_dps": 1000.0,
            "candidate_dps": 1010.0,
            "delta_pct": 1.0,
            "limiar_pct": 0.2,
            "veredito": "Vale a troca",
        },
    )
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/api/sim/compare",
            json={"base": "a" * 40, "candidate": "b" * 40},
        )
    assert resposta.status_code == 200
    assert resposta.json()["veredito"] == "Vale a troca"


def test_rota_profile_falha_do_simc_retorna_502(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args, **kwargs):
        raise SimcFalhou("simc quebrou")

    monkeypatch.setattr(sim_api, "rodar_perfil", explode)
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/sim/profile", json={"profile": "x" * 40})
    assert resposta.status_code == 502


def _simc_disponivel() -> bool:
    try:
        find_simc()
    except Exception:  # noqa: BLE001
        return False
    return True


@pytest.mark.skipif(not _simc_disponivel(), reason="binário simc ausente")
def test_integracao_perfil_real() -> None:
    texto = FIXTURE.read_text(encoding="utf-8")
    resultado = sim_api.rodar_perfil(texto, "patchwerk", iterations=20)
    assert resultado["dps"] > 0
    assert resultado["meta"]["build"]


@pytest.mark.skipif(not _simc_disponivel(), reason="binário simc ausente")
def test_integracao_compare_mesmo_perfil_empata() -> None:
    texto = FIXTURE.read_text(encoding="utf-8")
    resultado = sim_api.comparar(texto, texto, "patchwerk", iterations=20)
    assert resultado["base_dps"] > 0
    assert resultado["candidate_dps"] > 0
    assert resultado["veredito"] == "Empate técnico — simular"
    assert abs(resultado["delta_pct"]) < 0.15
