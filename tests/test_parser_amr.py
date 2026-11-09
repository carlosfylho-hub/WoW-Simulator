"""Fase 1: parser puro do export AskMrRobot v181."""

from __future__ import annotations

import pytest

from wowsim.parser.addon import serializar_texto
from wowsim.parser.amr import (
    SLOTS_AMR,
    ErroAmr,
    classe_da_spec,
    detectar,
    normalizar_classe,
    para_personagem,
    parse_amr,
)
from wowsim.paths import PROJECT_ROOT

pytestmark = pytest.mark.schema

FIXTURE = PROJECT_ROOT / "fixtures" / "pyrogalth-amr-181.txt"


@pytest.fixture(scope="module")
def amr():
    return parse_amr(FIXTURE.read_text(encoding="utf-8"))


def test_deteccao_por_cifrao() -> None:
    assert detectar("$181;US;...")
    assert not detectar("# Pyrogalth - Demonology")
    with pytest.raises(ErroAmr):
        parse_amr("# nao e amr")


def test_cabecalho(amr) -> None:
    assert amr.versao == "181"
    assert amr.regiao == "US"
    assert amr.reino == "Azralon"
    assert amr.nome == "Pyrogalth"
    assert amr.guilda == "Círculo da Carnificina"
    assert amr.raca_id == 24
    assert amr.classe_id == 2
    assert amr.nivel == 90
    assert amr.campo_extra == "2"


def test_moedas(amr) -> None:
    assert amr.moedas == {13: 100, 15: 1, 12: 207, 11: 100, 4: 100}


def test_conjunto_atual_e_q2(amr) -> None:
    assert set(amr.conjuntos) >= {"q2", "q3"}
    assert amr.conjunto_atual is not None
    assert amr.conjunto_atual.chave == "q2"


def test_item_wrist_239648(amr) -> None:
    item = amr.conjuntos["q2"].itens["wrist"]
    assert item.item_id == 239648
    assert item.slot == "wrist"
    assert item.content_tuning == 3615
    assert 8790 in item.bonus_ids
    assert item.crafted_stats == (36, 32)
    # 'l' é a escala de qualidade do AMR, não o crafting_quality do simc.
    assert item.craft_quality_amr == 8
    # 'd' é vínculo (1 = soulbound), não nível de drop.
    assert item.vinculo == 1
    assert item.guid == "A953F0E9A"


def test_item_main_hand_com_encantamento(amr) -> None:
    item = amr.conjuntos["q2"].itens["main_hand"]
    # fixtures/pyrogalth.simc: main_hand=,id=251156 (o id é diferença acumulada).
    assert item.item_id == 251156
    assert item.enchant_id == 7981  # Precisão de Jan'alai, Tier 2 (ADR-001)


def test_back_decodificado_pelo_export(amr) -> None:
    back = amr.conjuntos["q2"].itens["back"]
    # fixtures/pyrogalth.simc: back=,id=239656 (o id é diferença acumulada).
    # Os "bônus negativos" antes lidos eram diferenças; agora são decodificados.
    assert back.item_id == 239656
    assert back.bonus_ids
    assert all(bonus > 0 for bonus in back.bonus_ids)
    assert 8790 in back.bonus_ids


def test_slots_mapeados(amr) -> None:
    itens = amr.conjuntos["q2"].itens
    assert SLOTS_AMR[9] == "wrist"
    assert set(itens) <= set(SLOTS_AMR.values())
    assert "feet" in amr.conjuntos["q3"].itens


def test_watermarks_do_hlv(amr) -> None:
    assert len(amr.watermarks) == 17
    por_indice = {marca.indice: marca for marca in amr.watermarks}
    assert por_indice[14].atual == 259
    assert por_indice[14].maximo == 305
    assert por_indice[0].atual == 321


def test_talentos_crus(amr) -> None:
    assert "s1" in amr.talentos
    assert amr.talentos["s1"].grupo == 35
    assert amr.talentos["s1"].talentos is None
    s2 = amr.talentos["s2"]
    assert s2.grupo == 36
    assert s2.talentos
    assert s2.runas.get(1279599) == 1
    assert s2.runas.get(1287555) == 1


def test_ach_e_inv(amr) -> None:
    assert 62410 in amr.ach
    assert 62414 in amr.ach
    assert amr.inv  # histórico de aquisição preservado cru
    assert amr.texto_original.startswith("$181;")


# ---------------------------------------------------------------------------
# Fase 2: adaptador para Personagem + texto SimC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("warlock", "warlock"),
        ("Bruxo", "warlock"),
        ("Sacerdote", "priest"),
        ("Caçador de Demônios", "demonhunter"),
        ("Cavaleiro da Morte", "deathknight"),
        ("Mago", "mage"),
        ("Xamã", "shaman"),
        ("desconhecida", None),
    ],
)
def test_normalizar_classe(entrada: str, esperado: str | None) -> None:
    assert normalizar_classe(entrada) == esperado


def test_para_personagem_com_hints(amr) -> None:
    personagem = para_personagem(
        amr, classe_hint="bruxo", spec_hint="demonology"
    )
    assert personagem.classe == "warlock"
    assert personagem.spec == "demonology"
    assert personagem.nivel == 90
    assert personagem.nome == "Pyrogalth"
    assert personagem.regiao == "us"
    assert personagem.servidor == "azralon"

    wrist = personagem.equipado["wrist"]
    assert wrist.item_id == 239648
    assert 8790 in wrist.bonus_ids
    assert wrist.crafted_stats == (36, 32)

    main = personagem.equipado["main_hand"]
    # fixtures/pyrogalth.simc: main_hand=,id=251156
    assert main.item_id == 251156
    assert main.enchant_id == 7981

    # Back decodificado: ids e bônus batem com o export do SimC (239656).
    back = personagem.equipado["back"]
    assert back.item_id == 239656
    assert all(bonus > 0 for bonus in back.bonus_ids)


def test_texto_simc_canonico(amr) -> None:
    personagem = para_personagem(amr, classe_hint="warlock", spec_hint="demonology")
    texto = personagem.texto_original
    assert 'warlock="Pyrogalth"' in texto
    assert "level=90" in texto
    assert "spec=demonology" in texto
    assert "wrist=,id=239648" in texto
    assert "main_hand=,id=251156,enchant_id=7981" in texto
    # Round-trip: serializar_texto devolve o mesmo texto gerado.
    assert serializar_texto(personagem) == texto


def test_classe_da_spec_do_mapa() -> None:
    assert classe_da_spec("181", 36) == "warlock"
    assert classe_da_spec("181", 38) == "warrior"  # addon v181: Warrior 38-40
    assert classe_da_spec("89", 13) == "mage"
    assert classe_da_spec("999", 36) is None


def test_para_personagem_infere_classe_do_mapa(amr) -> None:
    personagem = para_personagem(amr)
    assert personagem.classe == "warlock"  # v181: specs 35/36/37 = bruxo
    assert personagem.raca == "dracthyr"  # raca 24 no enum do addon
    codigos = {alerta.codigo for alerta in personagem.alertas}
    assert "amr_classe_do_mapa" in codigos
    assert "amr_talentos_nao_convertidos" in codigos
    assert 'warlock="Pyrogalth"' in personagem.texto_original


def test_para_personagem_versao_sem_mapa_avisa() -> None:
    texto = FIXTURE.read_text(encoding="utf-8").replace("$181;", "$999;", 1)
    personagem = para_personagem(parse_amr(texto))
    assert personagem.classe is None
    codigos = {alerta.codigo for alerta in personagem.alertas}
    assert "amr_classe_ausente" in codigos
    assert 'warlock="' not in personagem.texto_original


def test_para_personagem_watermarks(amr) -> None:
    personagem = para_personagem(amr, classe_hint="warlock")
    assert len(personagem.slot_high_watermarks) == 17
    por_indice = {marca.indice: marca for marca in personagem.slot_high_watermarks}
    assert por_indice[14].ilvl_atual == 259
    assert por_indice[14].mapeado is True
