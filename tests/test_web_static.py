"""The FastAPI app serves the built React app and the frontend health route."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web.app import app  # noqa: E402
from wowsim.web.static import dist_dir  # noqa: E402

pytestmark = pytest.mark.unit

DIST = dist_dir()
tem_build = (DIST / "index.html").is_file()


def test_api_health_espelha_frontend() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.get("/api/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "patch": "12.1.5", "season": 2}


@pytest.mark.skipif(not tem_build, reason="dist do React ausente; rode npm run build")
def test_raiz_serve_index_do_react() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "<div id=\"root\"" in resposta.text or "id=\"root\"" in resposta.text


@pytest.mark.skipif(not tem_build, reason="dist do React ausente; rode npm run build")
def test_rota_desconhecida_cai_no_index() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.get("/alguma/rota/do/spa")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "id=\"root\"" in resposta.text


@pytest.mark.skipif(not tem_build, reason="dist do React ausente; rode npm run build")
def test_api_nao_e_capturada_pela_spa() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.get("/api/health")
    assert resposta.headers["content-type"].startswith("application/json")
