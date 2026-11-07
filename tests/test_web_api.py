"""FastAPI surface tests without running simc."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import db, worker  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def test_health_e_post_sem_executar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    enfileirados: list[str] = []
    monkeypatch.setattr(worker, "enfileirar", lambda job_id: enfileirados.append(job_id))

    with TestClient(app) as cliente:
        health = cliente.get("/health")
        assert health.status_code == 200
        assert health.json()["workers"] >= 1

        resposta = cliente.post(
            "/sim",
            json={
                "addon": FIXTURE.read_text(encoding="utf-8"),
                "iterations": 20,
                "max_variacoes": 2,
            },
        )
        assert resposta.status_code == 202
        job_id = resposta.json()["id"]
        assert enfileirados == [job_id]

        consulta = cliente.get(f"/sim/{job_id}")
        assert consulta.status_code == 200
        assert consulta.json()["status"] == "pending"
        assert "addon_text" not in consulta.json()

        relatorio = cliente.get(f"/sim/{job_id}/relatorio")
        assert relatorio.status_code == 409

        assert cliente.get("/sim/nao-existe").status_code == 404


def test_addon_muito_curto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(worker, "enfileirar", lambda job_id: None)
    with TestClient(app) as cliente:
        resposta = cliente.post("/sim", json={"addon": "curto"})
        assert resposta.status_code == 422
