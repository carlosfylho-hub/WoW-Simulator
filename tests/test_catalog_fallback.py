"""Catalog endpoint must name/icon items outside the M+ database (delve/craft)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from wowsim.web import catalog_api  # noqa: E402

pytestmark = pytest.mark.unit


def _por_id() -> dict[int, dict]:
    return {item["id"]: item for item in catalog_api.itens_catalogo()}


def test_delve_item_tem_nome_e_icone() -> None:
    itens = _por_id()
    # Miststalker's Wristbands: delve item known only by the stats snapshot.
    item = itens.get(272246)
    assert item is not None
    assert item["nome_pt"] == "Pulseiras do Espreitador das Brumas"
    assert item["nome_en"] == "Miststalker's Wristbands"
    assert item["icon"]


def test_craft_item_tem_nome_e_icone() -> None:
    itens = _por_id()
    item = itens.get(244613)
    assert item is not None
    assert item["nome_pt"]
    assert item["icon"]
