"""Embellishment data: inherent crafts, optional crafts and recommendations."""

from __future__ import annotations

import pytest

from wowsim.data import embellishments
from wowsim.web.catalog_api import itens_catalogo

pytestmark = pytest.mark.schema


def test_craft_embutido() -> None:
    info = embellishments.info(241140)
    assert info.craftado is True
    assert info.embutido is True
    assert info.aceita is False
    assert info.limite == 2


def test_craft_de_acessorio_aceita_embelezamento() -> None:
    info = embellishments.info(240949)  # Elo Sin'dorei Magistral
    assert info.craftado is True
    assert info.embutido is False
    assert info.aceita is True
    assert info.nome_pt == "Elo Sin'dorei Magistral"


def test_recomendacao_vem_do_guia() -> None:
    info = embellishments.info(239648)  # Braceletes do Mártir
    assert info.craftado is True
    assert "Arcanotrama" in (info.recomendado or "") or info.recomendado == "Arcanoweave Lining"

    anel = embellishments.info(240949)  # Elo Sin'dorei Magistral
    assert anel.recomendado == "Amolita Polida"

    lanterna = embellishments.info(245769)  # Lanterna de Aln'hara
    assert lanterna.recomendado == "Pedra Ritual do Caçador"


def test_item_desconhecido_nao_e_craftado() -> None:
    info = embellishments.info(999_999_999)
    assert info.craftado is False
    assert info.embutido is False
    assert info.aceita is False
    assert info.fonte == "desconhecido"


def test_catalogo_expoe_embelezamento_dos_craftados() -> None:
    itens = itens_catalogo()
    por_id = {item["id"]: item for item in itens if item["id"] in (240949, 239648, 241140)}

    anel = por_id[240949]
    assert anel["craftado"] is True
    assert anel["aceita_embelezamento"] is True
    assert anel["embellished"] is False
    assert anel["embelezamento_recomendado"] == "Amolita Polida"
    assert anel["limite_embelezamentos"] == 2

    pulsos = por_id[239648]
    recomendado = pulsos["embelezamento_recomendado"] or ""
    assert "Arcanotrama" in recomendado or recomendado == "Arcanoweave Lining"

    sinete = por_id[241140]
    assert sinete["embellished"] is True
    assert sinete["aceita_embelezamento"] is False
