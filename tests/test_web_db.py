"""SQLite job store tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.web import db

pytestmark = pytest.mark.unit


def test_ciclo_do_job(tmp_path: Path) -> None:
    caminho = tmp_path / "jobs.db"
    db.init_db(caminho)

    job_id = db.criar_job("addon de teste", iterations=50, max_variacoes=3, caminho=caminho)
    job = db.obter_job(job_id, caminho=caminho)
    assert job is not None
    assert job["status"] == "pending"
    assert job["iterations"] == 50
    assert job["max_variacoes"] == 3
    assert job_id in db.jobs_pendentes(caminho=caminho)

    db.atualizar_job(job_id, status="running", caminho=caminho)
    assert db.obter_job(job_id, caminho=caminho)["status"] == "running"

    db.atualizar_job(
        job_id,
        status="done",
        resultado_json='{"base_dps": 1000}',
        relatorio_md=str(tmp_path / "relatorio.md"),
        caminho=caminho,
    )
    final = db.obter_job(job_id, caminho=caminho)
    assert final["status"] == "done"
    assert final["resultado"] == {"base_dps": 1000}
    assert job_id not in db.jobs_pendentes(caminho=caminho)


def test_status_invalido(tmp_path: Path) -> None:
    caminho = tmp_path / "jobs.db"
    db.init_db(caminho)
    job_id = db.criar_job("x", caminho=caminho)
    with pytest.raises(ValueError):
        db.atualizar_job(job_id, status="talvez", caminho=caminho)
    with pytest.raises(ValueError):
        db.atualizar_job(job_id, addon_text="proibido", caminho=caminho)


def test_job_inexistente(tmp_path: Path) -> None:
    db.init_db(tmp_path / "jobs.db")
    assert db.obter_job("nao-existe", caminho=tmp_path / "jobs.db") is None
