"""Unit tests for the profileset generators."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.gen import profilesets
from wowsim.parser.addon import parse_arquivo

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


@pytest.fixture(scope="module")
def personagem():
    return parse_arquivo(FIXTURE)


def test_base_sempre_primeira(personagem) -> None:
    variacoes = profilesets.gerar(
        personagem, categorias={"talento"}, max_variacoes=10
    )
    assert variacoes[0].nome == "base"
    assert variacoes[0].categoria == "base"
    assert variacoes[0].linhas_override == []


def test_upgrade_por_slot(personagem) -> None:
    variacoes = profilesets.upgrade_por_slot(personagem, 12846, 12854)
    assert len(variacoes) == 7
    nomes = {variacao.nome for variacao in variacoes}
    assert nomes == {
        "up_head",
        "up_shoulder",
        "up_chest",
        "up_hands",
        "up_legs",
        "up_feet",
        "up_finger1",
    }
    for variacao in variacoes:
        assert "12854" in variacao.linhas_override[0]
        assert "12846" not in variacao.linhas_override[0]
        assert variacao.categoria == "upgrade"

    mitico = profilesets.upgrade_por_slot(personagem, 12854, 12856)
    assert {variacao.nome for variacao in mitico} == {"up_waist", "up_finger2"}

    inexistente = profilesets.upgrade_por_slot(personagem, 99999, 12856)
    assert inexistente == []


def test_encantamentos_de_aneis_em_uma_variacao(personagem) -> None:
    variacoes = profilesets.encantamentos(personagem)
    aneis = [variacao for variacao in variacoes if variacao.nome.startswith("ench_rings_")]
    assert aneis
    for variacao in aneis:
        assert len(variacao.linhas_override) == 2
        assert any("finger1=" in linha for linha in variacao.linhas_override)
        assert any("finger2=" in linha for linha in variacao.linhas_override)
        enchant_ids = [
            linha.split("enchant_id=")[1].split(",")[0]
            for linha in variacao.linhas_override
        ]
        assert len(set(enchant_ids)) == 1


def test_encantamentos_nao_usam_camada_errada(personagem) -> None:
    ids = {
        int(variacao.nome.rsplit("_", 1)[-1])
        for variacao in profilesets.encantamentos(personagem)
    }
    assert 7935 not in ids
    assert 8730 not in ids


def test_gemas_mantem_familia(personagem) -> None:
    variacoes = profilesets.gemas(personagem)
    assert variacoes
    for variacao in variacoes:
        assert "gem_id=" in variacao.linhas_override[0]
        assert variacao.categoria == "gema"


def test_talentos_uma_por_loadout(personagem) -> None:
    variacoes = profilesets.talentos(personagem)
    assert len(variacoes) == 6
    assert all(variacao.linhas_override[0].startswith("talents=CoQAMr") for variacao in variacoes)
    assert len({variacao.linhas_override[0] for variacao in variacoes}) == 6


def test_folio_uma_linha_por_vez(personagem) -> None:
    variacoes = profilesets.folio(personagem)
    assert len(variacoes) == 8
    atual = ["1A", "2B", "3A", "4A", "5A"]
    for variacao in variacoes:
        linha = variacao.linhas_override[0]
        assert linha.startswith("omnium_talents=")
        assert "136814" in linha or "136815" in linha or "136817" in linha
        assert variacao.nome.startswith("folio_")


def test_berloques_respeitam_nivel_e_slots(personagem) -> None:
    variacoes = profilesets.berloques(personagem, nivel=341)
    assert variacoes
    for variacao in variacoes:
        linha = variacao.linhas_override[0]
        assert variacao.nome.startswith(("trinket1_", "trinket2_"))
        if variacao.bonus_ids_envolvidos:
            assert variacao.bonus_ids_envolvidos == [12856]
            assert "12856" in linha
        else:
            assert "bonus_id=" not in linha
    assert any(variacao.aviso for variacao in variacoes)

    with pytest.raises(ValueError):
        profilesets.berloques(personagem, nivel=300)


def test_arquivo_tem_profilesets_unicos(personagem, tmp_path: Path) -> None:
    variacoes = profilesets.gerar(
        personagem,
        categorias={"talento", "folio"},
        max_variacoes=20,
    )
    destino = profilesets.escrever_arquivo(personagem, variacoes, tmp_path / "lote.simc")
    texto = destino.read_text(encoding="utf-8")
    nomes = [linha.split('"')[1] for linha in texto.splitlines() if linha.startswith("profileset.")]
    assert len(nomes) == len(set(nomes)) == len(variacoes) - 1
    assert 'profileset."tal_raid_maxroll"+=' in texto
    assert "# Checksum" not in texto


def test_max_variacoes_limita_corpo(personagem) -> None:
    variacoes = profilesets.gerar(
        personagem,
        categorias={"talento", "folio"},
        max_variacoes=5,
    )
    assert len(variacoes) == 6
    assert variacoes[0].nome == "base"


def test_upgrade_exige_de_e_para(personagem) -> None:
    with pytest.raises(ValueError):
        profilesets.gerar(personagem, categorias={"upgrade"})
