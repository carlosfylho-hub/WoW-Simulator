"""The desktop launcher starts the local server and answers /api/health."""

from __future__ import annotations

import json
import urllib.request

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from wowsim.web.desktop import porta_livre, servidor_local  # noqa: E402

pytestmark = pytest.mark.unit


def test_porta_livre_retorna_porta_concreta() -> None:
    porta = porta_livre("127.0.0.1", 0)
    assert isinstance(porta, int)
    assert porta > 0


def test_servidor_local_responde_health() -> None:
    with servidor_local("127.0.0.1", 0) as base:
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8"))
    assert dados["status"] == "ok"
    assert dados["patch"] == "12.1.5"


def test_verificar_frontend_quando_build_existir() -> None:
    from wowsim.web.desktop import _verificar_frontend
    from wowsim.web.static import dist_dir

    if not (dist_dir() / "index.html").is_file():
        pytest.skip("dist do React ausente")
    with servidor_local("127.0.0.1", 0) as base:
        _verificar_frontend(base)
