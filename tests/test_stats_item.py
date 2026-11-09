"""Atributos oficiais por item: o snapshot grava 'Aceleracao'/'Forca' sem acento."""

from __future__ import annotations

import pytest

from wowsim.data import catalog

pytestmark = pytest.mark.unit


def test_pelego_da_pestilencia_tem_os_secundarios() -> None:
    stats = catalog.stats_item(251226)
    assert stats["crit"] == 118 and stats["versatility"] == 83


def test_aceleracao_sem_acento_vira_haste() -> None:
    # Antes deste teste nenhum item tinha 'haste': a poda subestimava itens de Aceleração.
    assert catalog.stats_item(159137).get("haste", 0) > 0
