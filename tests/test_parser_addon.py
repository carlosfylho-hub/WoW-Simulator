"""Tests for the addon parser using the real Pyrogalth fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.parser.addon import (
    FormatoAmrRejeitado,
    FormatoDesconhecido,
    parse_texto,
    serializar_bloco_equipamento,
    serializar_texto,
)

pytestmark = pytest.mark.golden

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


@pytest.fixture(scope="module")
def texto() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def personagem(texto: str):
    return parse_texto(texto)


def test_identidade(personagem) -> None:
    assert personagem.nome == "Pyrogalth"
    assert personagem.classe == "warlock"
    assert personagem.spec == "demonology"
    assert personagem.nivel == 90
    assert personagem.raca == "dracthyr"
    assert personagem.regiao == "us"
    assert personagem.servidor == "azralon"
    assert personagem.profissoes == {"alchemy": 100, "enchanting": 100}
    assert personagem.versao_addon == "12.1.5-04"
    assert personagem.build_cliente == "12.1.5.70783"
    assert personagem.checksum == "70553fc1"


def test_slots_e_ausencia_de_offhand(personagem) -> None:
    assert len(personagem.equipado) == 16
    assert "tabard" in personagem.equipado
    assert "off_hand" not in personagem.equipado
    assert set(personagem.equipado) == {
        "head",
        "neck",
        "shoulder",
        "back",
        "chest",
        "tabard",
        "wrist",
        "hands",
        "waist",
        "legs",
        "feet",
        "finger1",
        "finger2",
        "trinket1",
        "trinket2",
        "main_hand",
    }


def test_head_com_tier_gema_e_encantamento(personagem) -> None:
    head = personagem.equipado["head"]
    assert head.item_id == 271546
    assert head.enchant_id == 8017
    assert head.gem_ids == [240983]
    assert head.bonus_ids == [13692, 6652, 13695, 13698, 12846]
    assert head.ilvl_comentario == 321
    assert head.nome_pt == "Crânio do Necrólito Maldito"
    assert head.origem_linha == "equipado"


def test_pernas_com_sorver_e_redirect(personagem) -> None:
    legs = personagem.equipado["legs"]
    assert legs.item_id == 271545
    assert 41 in legs.bonus_ids
    assert 13440 in legs.bonus_ids
    assert legs.redirected_base_stats == 273786
    assert legs.enchant_id == 7935


def test_peitoral_catalisado(personagem) -> None:
    chest = personagem.equipado["chest"]
    assert chest.redirected_base_stats == 272231
    assert chest.enchant_id == 7987
    assert 13690 in chest.bonus_ids


def test_item_craftado(personagem) -> None:
    back = personagem.equipado["back"]
    assert back.item_id == 239656
    assert back.crafted_stats == (32, 40)
    assert back.crafting_quality == 5
    assert back.content_tuning == 3615

    wrist = personagem.equipado["wrist"]
    assert wrist.item_id == 239648
    assert wrist.crafted_stats == (36, 32)


def test_loadouts_salvos(personagem) -> None:
    assert len(personagem.loadouts) == 6
    assert set(personagem.loadouts) == {
        "raid maxroll",
        "Diabolist Delves",
        "m+ icy",
        "delves icy",
        "Diabolist Single",
        "single icy",
    }
    assert personagem.talents_atual is not None
    assert personagem.talents_atual.startswith("CoQAMr")
    for codigo in personagem.loadouts.values():
        assert not codigo.startswith("#")
        assert codigo.startswith("CoQAMr")


def test_omnium(personagem) -> None:
    assert personagem.omnium_ids_brutos == [136814, 136815, 136817, 136819, 136822]
    assert all(rank == 1 for rank in personagem.omnium_ranks.values())
    assert not any(alerta.codigo == "omnium_incompleto" for alerta in personagem.alertas)


def test_high_watermarks(personagem) -> None:
    marcas = personagem.slot_high_watermarks
    assert len(marcas) == 17
    assert all(marca.ilvl_atual <= marca.ilvl_maximo for marca in marcas)
    autorizadas = [marca for marca in marcas if marca.mapeado]
    assert len(autorizadas) == 1
    assert autorizadas[0].indice == 14
    assert (autorizadas[0].ilvl_atual, autorizadas[0].ilvl_maximo) == (259, 305)


def test_moedas_e_extras(personagem) -> None:
    assert len(personagem.catalyst_currencies) == 5
    assert personagem.catalyst_currencies[2813] == 8
    assert personagem.upgrade_currencies["c:1792"] == 4668
    assert personagem.upgrade_currencies["i:280562"] == 6
    assert personagem.bonus_roll_currencies == {3418: 0, 3511: 0}
    assert personagem.bonus_roll_items is not None
    assert 19577 in personagem.upgrade_achievements


def test_mochila(personagem) -> None:
    assert sum(len(itens) for itens in personagem.mochila.values()) == 5
    assert personagem.mochila["neck"][0].item_id == 158075
    assert personagem.mochila["neck"][0].ilvl_comentario == 207
    assert {item.item_id for item in personagem.mochila["back"]} == {272226, 272230}
    assert personagem.mochila["finger1"][0].item_id == 144392
    assert personagem.mochila["trinket1"][0].item_id == 241291
    assert all(item.origem_linha == "mochila" for itens in personagem.mochila.values() for item in itens)


def test_round_trip_byte_a_byte(texto: str, personagem) -> None:
    assert serializar_texto(personagem, incluir_checksum=True) == texto

    sem_checksum = texto.replace("# Checksum: 70553fc1\n", "")
    assert serializar_texto(personagem, incluir_checksum=False) == sem_checksum

    inicio = texto.index("# Crânio do Necrólito Maldito (321)")
    marcador_fim = "main_hand=,id=251156,enchant_id=7981,bonus_id=6652/12856"
    fim = texto.index(marcador_fim) + len(marcador_fim)
    assert serializar_bloco_equipamento(personagem) == texto[inicio:fim]


def test_reescrita_de_slot(texto: str, personagem) -> None:
    head = personagem.equipado["head"]
    head.linha_original = head.linha_original.replace("12846", "12854")
    saida = serializar_texto(personagem, incluir_checksum=False)
    assert "head=,id=271546,enchant_id=8017,gem_id=240983,bonus_id=13692/6652/13695/13698/12854" in saida
    assert saida.count("12846") == texto.count("12846") - 1


def test_rejeita_amr() -> None:
    with pytest.raises(FormatoAmrRejeitado):
        parse_texto("$181;US;Azralon;Pyrogalth;...")


def test_rejeita_formato_desconhecido() -> None:
    with pytest.raises(FormatoDesconhecido):
        parse_texto("isso não é um export")


def test_export_sem_equipamento() -> None:
    texto = (
        "# Novo - Demonology - 2026-11-06 - US/Azralon\n"
        "# SimC AddOn 12.1.5-04\n"
        'warlock="Novo"\n'
        "level=90\n"
        "talents=ABC\n"
    )
    personagem = parse_texto(texto)
    assert personagem.equipado == {}
    assert any(alerta.codigo == "equipamento_ausente" for alerta in personagem.alertas)
    assert any(alerta.codigo == "checksum_ausente" for alerta in personagem.alertas)


def test_bonus_id_invalido_nao_quebra() -> None:
    texto = (
        "# X - Demonology - 2026-11-06 - US/Azralon\n"
        "# SimC AddOn 12.1.5-04\n"
        'warlock="X"\n'
        "talents=ABC\n"
        "head=,id=1,bonus_id=abc/123\n"
        "# Checksum: 70553fc1\n"
    )
    personagem = parse_texto(texto)
    assert personagem.equipado["head"].bonus_ids == [123]
    assert any(
        alerta.codigo == "campo_nao_numerico" for alerta in personagem.alertas
    )
