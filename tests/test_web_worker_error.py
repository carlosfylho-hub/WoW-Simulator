"""P0-03: exceção inesperada no worker legado nunca deixa o job em 'running'."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.web import db, worker

pytestmark = pytest.mark.unit


def test_excecao_inesperada_vira_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    db.init_db()
    job_id = db.criar_job("x" * 20, iterations=10, max_variacoes=1)

    def explodir(*_args, **_kwargs):
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr(worker, "parse_texto", explodir)
    worker.processar(job_id)

    job = db.obter_job(job_id)
    assert job is not None
    assert job["status"] == "error"
    assert "RuntimeError" in (job["erro"] or "")
