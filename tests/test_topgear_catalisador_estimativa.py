"""P-032: custo do Catalisador na estimativa (gêmeos + pacotes de 2/4 peças).

Testa a função pura ``estimar_pacotes_max``, o parâmetro ``extras_profilesets``
de ``estimar_custo`` e o contrato de ``GET /api/topgear/estimativa`` com
``catalisador``. Nada aqui roda o simc (P1 preservado: só contagem de profilesets).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.topgear.catalisador import estimar_pacotes_max  # noqa: E402
from wowsim.topgear.runner import estimar_custo  # noqa: E402
from wowsim.web import db, topgear_api, topgear_db  # noqa: E402
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"

# Pools "cheios": só importa se o slot tem candidatos (o estimador conta slots).
_SLOTS_TIER = ("head", "shoulder", "chest", "hands", "legs")


def _pools(slots: tuple[str, ...]) -> dict[str, list[object]]:
    return {slot: [object()] for slot in slots}


# --------------------------------------------------------------- função pura


def test_classe_sem_tier_nao_estima_pacotes() -> None:
    assert estimar_pacotes_max(_pools(_SLOTS_TIER), "classe_inexistente") == 0


def test_pacotes_de_2_e_4_pecas_com_os_cinco_slots() -> None:
    # ja_tier=0: faltam 2 -> C(5,2)=10; faltam 4 -> C(5,4)=5; total 15.
    assert estimar_pacotes_max(_pools(_SLOTS_TIER), "warlock", ja_tier=0) == 10 + 5


def test_ja_tier_reduz_o_que_falta() -> None:
    # ja_tier=1: faltam 1 -> C(5,1)=5; faltam 3 -> C(5,3)=10; total 15.
    assert estimar_pacotes_max(_pools(_SLOTS_TIER), "warlock", ja_tier=1) == 5 + 10


def test_teto_de_cargas_corta_os_pacotes_caros() -> None:
    # max_catalisados=2: faltam 2 (10) entra; faltam 4 (>2) sai.
    assert (
        estimar_pacotes_max(
            _pools(_SLOTS_TIER), "warlock", ja_tier=0, max_catalisados=2
        )
        == 10
    )


def test_poucos_slots_de_tier() -> None:
    # Só 2 slots de tier: faltam 2 -> C(2,2)=1; faltam 4 impossível.
    assert estimar_pacotes_max(_pools(("head", "chest")), "warlock", ja_tier=0) == 1


def test_sem_slots_de_tier_na_pool() -> None:
    assert estimar_pacotes_max({"main_hand": [object()]}, "warlock") == 0


def test_estimar_custo_soma_extras_de_profilesets() -> None:
    pools = {"head": [object(), object()], "chest": [object()]}
    base = estimar_custo(
        pools, iterations=200, orcamento_segundos=600, target_error=None,
        max_profilesets_rodada=300,
    )
    com_extra = estimar_custo(
        pools, iterations=200, orcamento_segundos=600, target_error=None,
        max_profilesets_rodada=300, extras_profilesets=15,
    )
    # 3 candidatos + 2 slots * 4 = 11; o extra entra em cima.
    assert base["profilesets_total_estimado"] == 3 + 2 * 4
    assert com_extra["profilesets_total_estimado"] == base["profilesets_total_estimado"] + 15


# --------------------------------------------------------------- API


def _cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(topgear_db, "DB_PATH", tmp_path / "topgear.db")
    monkeypatch.setattr(topgear_api, "enfileirar_topgear", lambda job_id: None)
    return TestClient(app)


def test_api_estimativa_catalisador_com_tier_completo_sem_pacotes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O fixture veste o tier set completo (5 peças): nada a catalisar, então
    # gêmeos e pacotes dão zero — o custo não pode aumentar nem diminuir.
    cliente = _cliente(tmp_path, monkeypatch)
    addon = FIXTURE.read_text(encoding="utf-8")
    with cliente:
        sem = cliente.get(
            "/api/topgear/estimativa", params={"addon": addon, "catalisador": "false"}
        )
        assert sem.status_code == 200
        corpo_sem = sem.json()
        assert corpo_sem["catalisador"] is False
        assert corpo_sem["extras_catalisador"] == 0

        com = cliente.get(
            "/api/topgear/estimativa", params={"addon": addon, "catalisador": "true"}
        )
        assert com.status_code == 200
        corpo_com = com.json()
        assert corpo_com["catalisador"] is True
        assert corpo_com["extras_catalisador"] == 0
        assert (
            corpo_com["profilesets_total_estimado"]
            >= corpo_sem["profilesets_total_estimado"]
        )


def test_api_estimativa_catalisador_respeita_teto_de_cargas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente = _cliente(tmp_path, monkeypatch)
    addon = FIXTURE.read_text(encoding="utf-8")
    with cliente:
        livre = cliente.get(
            "/api/topgear/estimativa", params={"addon": addon, "catalisador": "true"}
        ).json()
        teto = cliente.get(
            "/api/topgear/estimativa",
            params={"addon": addon, "catalisador": "true", "max_catalisados": 2},
        ).json()
        # Limitar cargas nunca aumenta a contagem de pacotes.
        assert teto["extras_catalisador"] <= livre["extras_catalisador"]
        assert teto["extras_catalisador"] >= 0
        assert not math.isnan(teto["extras_catalisador"])
