"""Top Gear API contract tests, without running simc."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import db, topgear_api, topgear_db  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def _cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[str]]:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(topgear_db, "DB_PATH", tmp_path / "topgear.db")
    enfileirados: list[str] = []
    monkeypatch.setattr(
        topgear_api, "enfileirar_topgear", lambda job_id: enfileirados.append(job_id)
    )
    return TestClient(app), enfileirados


def _pedido() -> dict:
    return {
        "addon": FIXTURE.read_text(encoding="utf-8"),
        "scenario": "patchwerk",
        "iterations_triagem": 10,
        "iterations_refino": 10,
        "orcamento_segundos": 60,
        "pool_por_slot": 5,
    }


def test_heuristica_retorna_ranking_instantaneo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    addon = FIXTURE.read_text(encoding="utf-8")
    with cliente:
        resposta = cliente.get(
            "/api/topgear/heuristica", params={"addon": addon, "pool": 5, "top": 3}
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["heuristico"] is True
        assert corpo["fonte_pesos"]
        assert corpo["por_slot"]
        algum = next(iter(corpo["por_slot"].values()))
        assert algum and "score" in algum[0] and "breakdown" in algum[0]


def test_criar_consultar_cancelar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        resposta = cliente.post("/api/topgear", json=_pedido())
        assert resposta.status_code == 202
        job_id = resposta.json()["id"]
        assert enfileirados == [job_id]

        consulta = cliente.get(f"/api/topgear/{job_id}")
        assert consulta.status_code == 200
        corpo = consulta.json()
        assert corpo["status"] == "pending"
        assert "addon" not in corpo["request"]

        assert cliente.get(f"/api/topgear/{job_id}/resultado").status_code == 409

        cancelar = cliente.post(f"/api/topgear/{job_id}/cancelar")
        assert cancelar.status_code == 200
        assert cancelar.json()["cancelado"] is True
        assert topgear_db.esta_cancelado(job_id) is True

        assert cliente.get("/api/topgear/nao-existe").status_code == 404


def test_resultado_disponivel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        job_id = cliente.post("/api/topgear", json=_pedido()).json()["id"]
        topgear_db.atualizar_job(
            job_id,
            status="done",
            resultado_json=json.dumps({"base_dps": 1000.0, "melhor_dps": 1010.0}),
        )
        resposta = cliente.get(f"/api/topgear/{job_id}/resultado")
        assert resposta.status_code == 200
        assert resposta.json()["melhor_dps"] == 1010.0


def test_previa_de_pools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        resposta = cliente.get(
            "/api/topgear/pools",
            params={
                "addon": FIXTURE.read_text(encoding="utf-8"),
                "pool": 3,
                "tipo_armadura": "tecido",
                "atributo": "Intelecto",
            },
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["classe"] == "warlock"
        assert corpo["contagens"]["head"] == 3
        assert corpo["itens"]["head"]
        assert all(item["bonus_id"] for item in corpo["itens"]["head"])


def test_addon_curto_na_previa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        assert (
            cliente.get("/api/topgear/pools", params={"addon": "curto"}).status_code
            == 422
        )


def test_perfil_exportado_inclui_gemas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-03: the canonical profile keeps the gems/enchants that were measured."""
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        job_id = cliente.post("/api/topgear", json=_pedido()).json()["id"]
        resultado = {
            "melhor": {
                "itens": {
                    "head": {
                        "slot": "head",
                        "item_id": 1,
                        "enchant_id": 100,
                        "gem_ids": [123],
                        "fonte": "teste",
                    }
                },
                "talentos": None,
                "runas_folio": [],
            },
            "base_dps": 1000.0,
            "melhor_dps": 1010.0,
            "delta_pct": 1.0,
            "limiar_pct": 0.15,
            "trocas": [],
            "rodadas": [],
            "avisos": [],
        }
        topgear_db.atualizar_job(
            job_id, status="done", resultado_json=json.dumps(resultado)
        )

        resposta = cliente.get(f"/api/topgear/{job_id}/perfil")
        assert resposta.status_code == 200
        simc = resposta.json()["simc"]
        assert "gem_id=123" in simc
        assert "enchant_id=100" in simc


def test_post_invalido_nao_enfileira(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        curto = _pedido()
        curto["addon"] = "curto"
        assert cliente.post("/api/topgear", json=curto).status_code == 422

        cenario = _pedido()
        cenario["scenario"] = "invalido"
        assert cliente.post("/api/topgear", json=cenario).status_code == 422

        iteracoes = _pedido()
        iteracoes["iterations_triagem"] = 1
        assert cliente.post("/api/topgear", json=iteracoes).status_code == 422

        assert enfileirados == []


def test_listar_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        a = cliente.post("/api/topgear", json=_pedido()).json()["id"]
        b = cliente.post("/api/topgear", json=_pedido()).json()["id"]

        resposta = cliente.get("/api/topgear")
        assert resposta.status_code == 200
        jobs = resposta.json()["jobs"]
        assert {job["id"] for job in jobs} == {a, b}
        # The list does not carry the heavy result payload.
        assert all("resultado" not in job for job in jobs)
