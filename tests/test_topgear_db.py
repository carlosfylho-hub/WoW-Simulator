"""SQLite store tests for Top Gear jobs."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.web import topgear_db

pytestmark = pytest.mark.unit


def test_ciclo_do_job(tmp_path: Path) -> None:
    caminho = tmp_path / "topgear.db"
    topgear_db.init_db(caminho)

    job_id = topgear_db.criar_job('{"addon": "x"}', caminho=caminho)
    job = topgear_db.obter_job(job_id, caminho=caminho)
    assert job is not None
    assert job["status"] == "pending"
    assert job["request"] == {"addon": "x"}
    assert job_id in topgear_db.jobs_pendentes(caminho=caminho)

    topgear_db.atualizar_job(
        job_id, status="running", started_at="agora", caminho=caminho
    )
    assert topgear_db.obter_job(job_id, caminho=caminho)["status"] == "running"
    # Um job "running" é retomado no próximo início do worker.
    assert job_id in topgear_db.jobs_pendentes(caminho=caminho)

    topgear_db.atualizar_job(
        job_id,
        status="done",
        resultado_json='{"base_dps": 1000}',
        progresso_json='{"rodada": 2}',
        caminho=caminho,
    )
    final = topgear_db.obter_job(job_id, caminho=caminho)
    assert final["status"] == "done"
    assert final["resultado"] == {"base_dps": 1000}
    assert final["progresso"] == {"rodada": 2}
    assert job_id not in topgear_db.jobs_pendentes(caminho=caminho)


def test_cancelamento(tmp_path: Path) -> None:
    caminho = tmp_path / "topgear.db"
    topgear_db.init_db(caminho)
    job_id = topgear_db.criar_job("{}", caminho=caminho)

    assert topgear_db.esta_cancelado(job_id, caminho=caminho) is False
    assert topgear_db.marcar_cancelamento(job_id, caminho=caminho) is True
    assert topgear_db.esta_cancelado(job_id, caminho=caminho) is True
    assert job_id not in topgear_db.jobs_pendentes(caminho=caminho)
    assert topgear_db.marcar_cancelamento("nao-existe", caminho=caminho) is False


def test_status_e_campos_invalidos(tmp_path: Path) -> None:
    caminho = tmp_path / "topgear.db"
    topgear_db.init_db(caminho)
    job_id = topgear_db.criar_job("{}", caminho=caminho)

    with pytest.raises(ValueError):
        topgear_db.atualizar_job(job_id, status="talvez", caminho=caminho)
    with pytest.raises(ValueError):
        topgear_db.atualizar_job(job_id, request_json="proibido", caminho=caminho)
