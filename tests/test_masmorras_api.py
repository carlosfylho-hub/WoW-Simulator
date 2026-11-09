"""Contratos da API do ranking de masmorras, sem rodar simc."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import (  # noqa: E402
    db,
    drop_db,
    masmorras_api,
    masmorras_db,
    perfil_store,
    topgear_db,
)
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def _cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[str]]:
    for modulo, nome in (
        (db, "jobs.db"),
        (drop_db, "drop.db"),
        (perfil_store, "perfil.db"),
        (topgear_db, "topgear.db"),
        (masmorras_db, "masmorras.db"),
    ):
        monkeypatch.setattr(modulo, "DB_PATH", tmp_path / nome)
    enfileirados: list[str] = []
    monkeypatch.setattr(
        masmorras_api, "enfileirar_masmorras", lambda job_id: enfileirados.append(job_id)
    )
    return TestClient(app), enfileirados


def _pedido() -> dict:
    return {
        "addon": FIXTURE.read_text(encoding="utf-8"),
        "scenario": "dungeon_slice",
        "ilvl": 341,
        "iteracoes_triagem": 50,
        "iteracoes_refino": 200,
        "orcamento_segundos": 60,
    }


def test_criar_consultar_cancelar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        resposta = cliente.post("/api/masmorras", json=_pedido())
        assert resposta.status_code == 202
        job_id = resposta.json()["id"]
        assert enfileirados == [job_id]

        consulta = cliente.get(f"/api/masmorras/{job_id}")
        assert consulta.status_code == 200
        corpo = consulta.json()
        assert corpo["status"] == "pending"
        assert corpo["request"]["scenario"] == "dungeon_slice"
        assert "addon" not in corpo["request"]

        assert cliente.get(f"/api/masmorras/{job_id}/resultado").status_code == 409

        cancelar = cliente.post(f"/api/masmorras/{job_id}/cancelar")
        assert cancelar.status_code == 200
        assert cancelar.json()["cancelado"] is True
        assert masmorras_db.esta_cancelado(job_id) is True

        assert cliente.get("/api/masmorras/nao-existe").status_code == 404


def test_resultado_disponivel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        job_id = cliente.post("/api/masmorras", json=_pedido()).json()["id"]
        masmorras_db.atualizar_job(
            job_id,
            status="done",
            resultado_json=json.dumps(
                {
                    "base_dps": 250000.0,
                    "cenario": "dungeon_slice",
                    "ilvl": 341,
                    "iteracoes": 200,
                    "masmorras": [],
                }
            ),
        )
        resposta = cliente.get(f"/api/masmorras/{job_id}/resultado")
        assert resposta.status_code == 200
        assert resposta.json()["base_dps"] == 250000.0


def test_listar_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        a = cliente.post("/api/masmorras", json=_pedido()).json()["id"]
        b = cliente.post("/api/masmorras", json=_pedido()).json()["id"]
        resposta = cliente.get("/api/masmorras")
        assert resposta.status_code == 200
        jobs = resposta.json()["jobs"]
        assert {job["id"] for job in jobs} == {a, b}
        assert all("resultado" not in job for job in jobs)


def test_post_invalido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, enfileirados = _cliente(tmp_path, monkeypatch)
    with cliente:
        curto = _pedido()
        curto["addon"] = "curto"
        assert cliente.post("/api/masmorras", json=curto).status_code == 422
        assert enfileirados == []


def test_estimativa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _ = _cliente(tmp_path, monkeypatch)
    with cliente:
        resposta = cliente.get(
            "/api/masmorras/estimativa",
            params={"addon": FIXTURE.read_text(encoding="utf-8"), "ilvl": 341},
        )
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["profilesets_total_estimado"] > 0
        assert corpo["elegiveis_total"] == 51
        assert set(corpo["contagens"]) == {
            "Altar das Presas",
            "Templo de Sethraliss",
            "Murder Row",
            "Descanso do Rei",
            "Arena da Chaga do Caos",
            "Covil de Nalorakk",
            "O Vale Ofuscante",
            "Piscinas da Vida Rubi",
        }
