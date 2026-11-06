"""Catalog tests: counts, provenance and classification."""

from __future__ import annotations

import json

import pytest

from wowsim.data import (
    berloques_conjurador,
    bonus_para_ilvl,
    encantamentos_por_slot,
    gemas,
    itens_mplus,
    nome_item,
    resolver_encantamento,
    runas_folio,
)
from wowsim.gen import omnium
from wowsim.paths import DADOS_DIR

pytestmark = pytest.mark.schema


def _dados(nome: str) -> dict:
    return json.loads((DADOS_DIR / nome).read_text(encoding="utf-8"))


def test_contagens_de_encantamentos_e_gemas() -> None:
    encantamentos = _dados("encantamentos_e_gemas_s2.json")
    assert len(encantamentos["encantamentos"]) == 76
    assert len({registro["nome_pt"] for registro in encantamentos["encantamentos"].values()}) == 38
    assert len(encantamentos["gemas"]) == 72
    assert len(encantamentos["pernas"]) == 12
    assert len({registro["nome_pt"] for registro in encantamentos["pernas"].values()}) == 6


def test_mapa_de_enchant_ids() -> None:
    mapa = _dados("enchant_ids_s2.json")["enchants"]
    assert len(mapa) == 97


def test_runas_e_combinacoes() -> None:
    dados = _dados("rune_ids_s2.json")
    assert len(dados["runas"]) == 13
    assert dados["estrutura"]["combinacoes_possiveis"] == 72
    assert len(runas_folio()) == 13


def test_nome_item_com_fonte_e_simulavel() -> None:
    item = nome_item(271546)
    assert item.nome_pt == "Crânio do Necrólito Maldito"
    assert item.nome_en == "Skull of the Damned Necrolyte"
    assert item.fonte == "stats_oficiais_itens.json"
    assert item.simulavel is True
    assert item.fonte_simulavel == "item_data.inc"


def test_nome_item_desconhecido() -> None:
    item = nome_item(999_999_999)
    assert item.nome_pt is None
    assert item.nome_en is None
    assert item.simulavel is False
    assert item.fonte == "desconhecido"


def test_bonus_para_ilvl_validado() -> None:
    assert bonus_para_ilvl(12846).ilvl == 321
    assert bonus_para_ilvl(12854).ilvl == 334
    assert bonus_para_ilvl(12849).ilvl == 318
    assert bonus_para_ilvl(12817).ilvl == 266
    assert bonus_para_ilvl(12848).ilvl == 328
    assert bonus_para_ilvl(12856).ilvl == 341
    assert bonus_para_ilvl(12846).fonte == "raidbots:bonus-upgrade-sets"

    desconhecido = bonus_para_ilvl(99999)
    assert desconhecido.ilvl is None
    assert desconhecido.fonte == "desconhecido"


def test_encantamentos_por_slot_e_camadas() -> None:
    aneis = encantamentos_por_slot("anel")
    assert any(item.nome_en == "Enchant Ring - Eyes of the Eagle" for item in aneis)

    arma = resolver_encantamento(7981)
    assert arma is not None
    assert arma.nome_en == "Enchant Weapon - Jan'alai's Precision"
    assert arma.camada == "encantamento"
    assert arma.slot == "arma"

    maos = resolver_encantamento(8730)
    assert maos is not None
    assert maos.camada == "arte_de_batalha"
    assert maos.slot == "mãos"

    pernas = resolver_encantamento(7935)
    assert pernas is not None
    assert pernas.camada == "magilinha"
    assert pernas.slot == "pernas"

    assert resolver_encantamento(1) is None


def test_gemas() -> None:
    todas = gemas()
    assert len(todas) == 72
    assert all(gema.fonte == "encantamentos_e_gemas_s2.json" for gema in todas)
    diamantes = [gema for gema in todas if gema.unica]
    assert diamantes
    assert any(gema.item_id == 240983 for gema in diamantes)
    granadas = gemas("garnet")
    assert any(gema.item_id == 240908 for gema in granadas)


def test_berloques_excluem_forca() -> None:
    berloques = berloques_conjurador()
    ids = {item.item_id for item in berloques}
    assert 273796 in ids
    assert 273795 not in ids
    assert all(item.fonte == "mplus_loot_database.json" for item in berloques)
    assert all(item.slot == "trinket" for item in berloques)


def test_itens_mplus_por_slot() -> None:
    cabecas = itens_mplus("head")
    assert cabecas
    assert all(item.slot == "head" for item in cabecas)
    assert all(item.fonte == "mplus_loot_database.json" for item in cabecas)


def test_omnium_selecao_do_fixture() -> None:
    selecao = omnium.selecao_de_ids([136814, 136815, 136817, 136819, 136822])
    assert selecao.codigo == "1A-2B-3A-4A-5A"
    assert selecao.confianca == "alta"
    assert selecao.por_linha == {
        "1": "1A",
        "2": "2B",
        "3": "3A",
        "4": "4A",
        "5": "5A",
    }


def test_omnium_codigo_para_ids() -> None:
    ids = omnium.codigo_para_ids("1A-2B-3A-4A-5A")
    assert ids == [136822, 136819, 136817, 136815, 136814]
    with pytest.raises(ValueError):
        omnium.codigo_para_ids("9Z-2B-3A-4A-5A")


def test_omnium_variacoes_uma_linha_por_vez() -> None:
    selecao = omnium.selecao_de_ids([136814, 136815, 136817, 136819, 136822])
    variacoes = omnium.variacoes_de_linha(selecao)
    assert variacoes
    for _nome, codigo, _entry in variacoes:
        assert codigo.count("-") == 4
        assert codigo != selecao.codigo
        diferentes = sum(1 for a, b in zip(codigo.split("-"), selecao.codigo.split("-")) if a != b)
        assert diferentes == 1


def test_todo_item_de_catalogo_tem_fonte() -> None:
    assert nome_item(273781).fonte
    assert bonus_para_ilvl(12846).fonte
    assert all(gema.fonte for gema in gemas())
    assert all(runa.fonte for runa in runas_folio())
    assert all(item.fonte for item in itens_mplus("head"))
    assert all(item.fonte for item in berloques_conjurador())
