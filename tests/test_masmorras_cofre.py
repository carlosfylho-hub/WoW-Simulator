"""T8: opções do Grande Cofre a partir do .gv (tokens sintéticos via codec)."""

from __future__ import annotations

import pytest

from wowsim.masmorras.cofre import opcoes_do_cofre
from wowsim.parser.amr import ImportAMR
from wowsim.parser.amr_codec import ItemAmr, codificar_itens

pytestmark = pytest.mark.unit


def _importacao(items: list[ItemAmr]) -> ImportAMR:
    # O .gv tem o mesmo formato de diferença acumulada do .inv; codificar_itens
    # produz tokens equivalentes aos que o addon grava.
    return ImportAMR(versao="181", gv=codificar_itens(items), texto_original="")


def test_opcoes_resolvem_slot_ilvl_e_bonus() -> None:
    amr = _importacao(
        [
            ItemAmr(item_id=271483, bonus_ids=[12854]),  # head, 334
            ItemAmr(item_id=239648, bonus_ids=[8790]),   # wrist
        ]
    )
    opcoes = opcoes_do_cofre(amr)
    por_id = {op["item_id"]: op for op in opcoes}

    assert por_id[271483]["slots"] == ["head"]
    assert por_id[271483]["ilvl"] == 334  # bônus 12854 (raidbots)
    assert por_id[271483]["bonus_ids"] == [12854]

    assert por_id[239648]["slots"] == ["wrist"]
    assert por_id[239648]["bonus_ids"] == [8790]


def test_gv_vazio_nao_gera_opcoes() -> None:
    assert opcoes_do_cofre(ImportAMR(versao="181", texto_original="")) == []
