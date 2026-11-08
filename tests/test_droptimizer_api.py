"""Contratos da API do Droptimizer, sem rodar simc."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import db, drop_api, drop_db  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def _cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[str]]:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(drop_db, "DB_PATH", tmp_path / "drop.db")
    enfileirados: list[str] = []
    monkeypatch.setattr(
        drop_api, "enfileirar_drop", lambda job_id: enfileirados.append(job_id)
    )
    return TestClient(app), enfileirados


def _pedido() -> dict:
    return {
        "addon": FIXTURE.read_text(encoding="utf-8"),
        "modo": "best_in_bags",
        "scenario": "patchwerk",
        "iterations": 10,
        "orcamento_segundos": 60,
    }


def test_criar_consultar_cancelar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        resposta = cliente.post("/api/droptimizer", json=_pedido())
        assert resposta.status_code == 202
        job_id = resposta.json()["id"]
        assert enfileirados == [job_id]

        consulta = cliente.get(f"/api/droptimizer/{job_id}")
        assert consulta.status_code == 200
        corpo = consulta.json()
        assert corpo["status"] == "pending"
        assert corpo["request"]["modo"] == "best_in_bags"
        assert "addon" not in corpo["request"]

        assert cliente.get(f"/api/droptimizer/{job_id}/resultado").status_code == 409

        cancelar = cliente.post(f"/api/droptimizer/{job_id}/cancelar")
        assert cancelar.status_code == 200
        assert cancelar.json()["cancelado"] is True
        assert drop_db.esta_cancelado(job_id) is True

        assert cliente.get("/api/droptimizer/nao-existe").status_code == 404


def test_resultado_disponivel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        job_id = cliente.post("/api/droptimizer", json=_pedido()).json()["id"]
        drop_db.atualizar_job(
            job_id,
            status="done",
            resultado_json=json.dumps({"base_dps": 1000.0, "itens": []}),
        )
        resposta = cliente.get(f"/api/droptimizer/{job_id}/resultado")
        assert resposta.status_code == 200
        assert resposta.json()["base_dps"] == 1000.0


def test_listar_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        a = cliente.post("/api/droptimizer", json=_pedido()).json()["id"]
        b = cliente.post("/api/droptimizer", json=_pedido()).json()["id"]
        resposta = cliente.get("/api/droptimizer")
        assert resposta.status_code == 200
        jobs = resposta.json()["jobs"]
        assert {job["id"] for job in jobs} == {a, b}
        assert all("resultado" not in job for job in jobs)


def test_post_invalido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        curto = _pedido()
        curto["addon"] = "curto"
        assert cliente.post("/api/droptimizer", json=curto).status_code == 422

        modo = _pedido()
        modo["modo"] = "invalido"
        assert cliente.post("/api/droptimizer", json=modo).status_code == 422
        assert enfileirados == []
