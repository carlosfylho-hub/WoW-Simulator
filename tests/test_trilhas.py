"""Escada de trilhas, atalhos de ilvl e custo de upgrade em brasões."""

from __future__ import annotations

import pytest

from wowsim.data import trilhas

pytestmark = pytest.mark.unit


def test_escada_bate_com_os_dados_verificados() -> None:
    heroi = [d.ilvl for d in trilhas.escada() if d.trilha == "heroi"]
    mito = [d.ilvl for d in trilhas.escada() if d.trilha == "mito"]
    assert heroi == [305, 308, 311, 315, 318, 321]
    assert mito == [318, 321, 324, 328, 331, 334]


def test_forja_so_no_seis_de_seis() -> None:
    assert trilhas.degrau("mito", 6, True).ilvl == 341
    assert trilhas.degrau("heroi", 6, True).ilvl == 328
    with pytest.raises(ValueError):
        trilhas.degrau("mito", 4, True)


def test_atalhos_antigos_continuam() -> None:
    assert trilhas.degrau_do_ilvl(341).bonus_id == 12856
    assert trilhas.degrau_do_ilvl(321).rotulo == "Herói 6/6"
    with pytest.raises(ValueError):
        trilhas.degrau_do_ilvl(318)  # Herói 5/6 ou Mito 1/6: ambíguo


def test_custo_de_upgrade_vinte_por_etapa() -> None:
    c = trilhas.custo_upgrade(trilhas.degrau("mito", 1))
    assert {k: c[k] for k in ("moeda", "brasoes", "etapas", "ate")} == {
        "moeda": "Brasão Mítico", "brasoes": 100, "etapas": 5, "ate": "Mito 6/6 (334)"
    }
    assert trilhas.custo_upgrade(trilhas.degrau("heroi", 4))["brasoes"] == 40
    assert trilhas.custo_upgrade(trilhas.degrau("mito", 6, True))["brasoes"] == 0


def test_degrau_pelos_bonus_do_item() -> None:
    assert trilhas.degrau_dos_bonus([6652, 12851]).rotulo == "Mito 3/6"
    assert trilhas.degrau_dos_bonus([12856, 6652]).forja is True
    assert trilhas.degrau_dos_bonus([1, 2]) is None
