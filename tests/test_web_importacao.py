"""The last /simc import survives an app restart (same SQLite file)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web import db, perfil_store, topgear_db  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def _bancos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "wowsim.db")
    monkeypatch.setattr(perfil_store, "DB_PATH", tmp_path / "wowsim.db")
    monkeypatch.setattr(topgear_db, "DB_PATH", tmp_path / "wowsim.db")


def test_importacao_persiste_entre_aberturas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bancos(tmp_path, monkeypatch)
    texto = FIXTURE.read_text(encoding="utf-8")

    with TestClient(app) as cliente:
        inicial = cliente.get("/api/perfil/importacao")
        assert inicial.status_code == 200
        assert inicial.json()["texto"] is None

        salvo = cliente.put("/api/perfil/importacao", json={"texto": texto})
        assert salvo.status_code == 200
        assert salvo.json()["ok"] is True

    # "Fecha e abre o app": novo lifespan, mesmo arquivo SQLite.
    with TestClient(app) as cliente:
        recuperado = cliente.get("/api/perfil/importacao")
        assert recuperado.status_code == 200
        assert recuperado.json()["texto"] == texto
        assert recuperado.json()["atualizado_em"]


def test_texto_curto_e_rejeitado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bancos(tmp_path, monkeypatch)
    with TestClient(app) as cliente:
        assert cliente.put("/api/perfil/importacao", json={"texto": "curto"}).status_code == 422


def test_combinar_rejeita_payload_grande(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-02: 'amr' acima de max_length (20_000) é rejeitado com 422."""
    _bancos(tmp_path, monkeypatch)
    grande = "$1" + "x" * 20_000
    with TestClient(app) as cliente:
        resposta = cliente.post("/api/import/combinar", json={"amr": grande})
        assert resposta.status_code == 422


def test_combinar_primario_amr_sem_amr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-04: primario='amr' sem export AMR é rejeitado com 422."""
    _bancos(tmp_path, monkeypatch)
    texto = FIXTURE.read_text(encoding="utf-8")
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/api/import/combinar", json={"simc": texto, "primario": "amr"}
        )
        assert resposta.status_code == 422
