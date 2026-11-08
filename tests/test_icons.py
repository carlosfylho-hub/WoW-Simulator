"""Icon coverage for every item used by the backend and the React app."""

from __future__ import annotations

import pytest

from wowsim.data import icons
from wowsim.web.catalog_api import itens_catalogo, mapa_icones

pytestmark = pytest.mark.schema


def test_icones_de_tier_e_raid() -> None:
    assert icons.icone(271549) == "inv_robe_cloth_raidwarlockulatek_d_01"
    assert icons.icone(271092).startswith("inv_knife_1h_ulatekfang")
    # Wowhead devolveu o fileDataID para este item novo; o zamimg serve o .jpg.
    assert icons.icone(281029) == "8268560"


def test_todo_item_do_catalogo_tem_icone() -> None:
    faltando = [item["id"] for item in itens_catalogo() if not item.get("icon")]
    assert faltando == []


def test_mapa_completo_inclui_itens_fora_do_catalogo_mplus() -> None:
    mapa = mapa_icones()
    assert mapa["271549"].startswith("inv_robe_cloth_raidwarlock")
    assert mapa["271092"].startswith("inv_knife")
