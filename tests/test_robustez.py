"""Testes de robustez: preferências, validação, cache, threads e erro-alvo.

Cobrem os pontos tocados pelas correções de concorrência/orçamento/persistência
sem depender do binário do simc.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from wowsim import simc_runner as sr
from wowsim.droptimizer.models import DropRequest
from wowsim.topgear.runner import (
    LIMITE_PROFILESETS_TARGET_ERROR,
    erro_alvo_efetivo,
)
from wowsim.web import perfil_store, worker

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Cenário tipado (DropRequest)
# --------------------------------------------------------------------------- #
def test_drop_scenario_valido():
    pedido = DropRequest(addon="x" * 40, scenario="dungeon_slice")
    assert pedido.scenario == "dungeon_slice"


def test_drop_scenario_invalido_falha():
    with pytest.raises(ValidationError):
        DropRequest(addon="x" * 40, scenario="cenario_que_nao_existe")


# --------------------------------------------------------------------------- #
# erro-alvo só em lotes pequenos (evita runaway do simc)
# --------------------------------------------------------------------------- #
def test_erro_alvo_lote_grande_desliga():
    assert erro_alvo_efetivo(0.2, LIMITE_PROFILESETS_TARGET_ERROR + 1) is None


def test_erro_alvo_lote_pequeno_mantem():
    assert erro_alvo_efetivo(0.2, 1) == 0.2
    assert erro_alvo_efetivo(0.2, LIMITE_PROFILESETS_TARGET_ERROR) == 0.2


def test_erro_alvo_none_permanece_none():
    assert erro_alvo_efetivo(None, 100) is None


# --------------------------------------------------------------------------- #
# Preferências no SQLite
# --------------------------------------------------------------------------- #
def test_preferencias_roundtrip(tmp_path):
    db = tmp_path / "wowsim.db"
    perfil_store.init_db(db)
    perfil_store.salvar_preferencia("wowsim.drop.preset", '"padrao"', caminho=db)
    assert perfil_store.obter_preferencia("wowsim.drop.preset", caminho=db) == '"padrao"'

    perfil_store.salvar_preferencia("wowsim.drop.preset", '"overnight"', caminho=db)
    todas = perfil_store.obter_preferencias(caminho=db)
    assert todas["wowsim.drop.preset"] == '"overnight"'


def test_preferencia_inexistente_retorna_none(tmp_path):
    db = tmp_path / "wowsim.db"
    perfil_store.init_db(db)
    assert perfil_store.obter_preferencia("nao.existe", caminho=db) is None


# --------------------------------------------------------------------------- #
# API de preferências em lote
# --------------------------------------------------------------------------- #
def test_api_preferencias_lote(monkeypatch):
    store: dict[str, str] = {}

    monkeypatch.setattr(
        perfil_store, "salvar_preferencia", lambda chave, valor: store.__setitem__(chave, valor)
    )
    monkeypatch.setattr(perfil_store, "obter_preferencias", lambda: dict(store))

    from wowsim.web.app import app

    cliente = TestClient(app)
    resposta = cliente.put(
        "/api/preferencias",
        json={"preferencias": {"a": "1", "b": "2"}},
    )
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 2

    lista = cliente.get("/api/preferencias")
    assert lista.status_code == 200
    assert lista.json()["preferencias"] == {"a": "1", "b": "2"}


# --------------------------------------------------------------------------- #
# Poda de cache
# --------------------------------------------------------------------------- #
def test_podar_cache_respeita_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("WOWSIM_CACHE_MAX_MB", "0.001")  # ~1 KB

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text("x" * 2000)
    b.write_text("x" * 2000)
    (tmp_path / "a.meta.json").write_text("{}")

    sr._podar_cache()

    sobreviventes = [p for p in (a, b) if p.exists()]
    total = sum(p.stat().st_size for p in sobreviventes)
    assert total <= 1024 * 1024 * 0.001 or not sobreviventes


def test_podar_cache_desligado(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("WOWSIM_CACHE_MAX_MB", "0")
    a = tmp_path / "a.json"
    a.write_text("x" * 5000)
    sr._podar_cache()
    assert a.exists()


# --------------------------------------------------------------------------- #
# Rateio de threads
# --------------------------------------------------------------------------- #
def test_threads_para_job_um_job(monkeypatch):
    monkeypatch.setattr(worker, "NUCLEOS", 20)
    monkeypatch.setattr(worker, "_ativos", 1)
    assert worker.threads_para_job() == 19


def test_threads_para_job_dois_jobs(monkeypatch):
    monkeypatch.setattr(worker, "NUCLEOS", 20)
    monkeypatch.setattr(worker, "_ativos", 2)
    assert worker.threads_para_job() == 9


def test_threads_para_job_nunca_zero(monkeypatch):
    monkeypatch.setattr(worker, "NUCLEOS", 2)
    monkeypatch.setattr(worker, "_ativos", 5)
    assert worker.threads_para_job() >= 1


def test_vagas_simulacao_positiva():
    assert worker.VAGAS_SIMULACAO >= 1
