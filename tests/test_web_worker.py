"""Worker integration: one real job through the SQLite queue and simc."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.web import db, worker

pytestmark = pytest.mark.integration_simc

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def test_processar_job_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(worker, "SAIDA_DIR", tmp_path / "saida")
    db.init_db()

    job_id = db.criar_job(
        FIXTURE.read_text(encoding="utf-8"), iterations=20, max_variacoes=1
    )
    worker.processar(job_id)

    job = db.obter_job(job_id)
    assert job is not None
    assert job["status"] == "done", job.get("erro")
    assert job["resultado"]["base_dps"] > 0
    assert Path(job["relatorio_md"]).is_file()
    assert Path(job["relatorio_html"]).is_file()
