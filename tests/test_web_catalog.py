"""The catalog API exposes the authoritative Python catalog as JSON."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit


def _itens() -> list[dict]:
    with TestClient(app) as cliente:
        resposta = cliente.get("/api/catalog/items")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total"] == len(dados["itens"])
    assert dados["total"] > 0
    return dados["itens"]


def test_catalogo_tem_campos_obrigatorios() -> None:
    itens = _itens()
    amostra = itens[0]
    for chave in ("id", "nome_pt", "nome_en", "slot", "ilvl", "bonus_id", "fonte"):
        assert chave in amostra


def test_catalogo_tem_alvos_com_bonus_de_trilha() -> None:
    itens = _itens()
    alvos = [i for i in itens if i["alvo"]]
    assert alvos
    bonuses = {i["bonus_id"] for i in alvos if i["bonus_id"]}
    assert bonuses & {12846, 12848, 12854, 12856}


def test_catalogo_traz_nome_pt_e_en_do_monitor() -> None:
    itens = _itens()
    altaluz = [i for i in itens if i["id"] == 250214]
    assert altaluz, "Núcleo Altaluz deveria estar no catálogo"
    nomes_pt = {i["nome_pt"] for i in altaluz}
    nomes_en = {i["nome_en"] for i in altaluz}
    assert any(n and "Altaluz" in n for n in nomes_pt)
    assert any(n and "Lightspire" in n for n in nomes_en)
