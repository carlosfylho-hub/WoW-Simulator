"""T16 (A-10): leitura do bloco @e de uma string de Best in Bags do AMR."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.parser.amr_codec import encantos_da_linha

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
BIB = RAIZ / "fixtures" / "pyrogalth-bib-amr.txt"

# Casos reais do P-016: Arte de Batalha Hash'ey e Magilinha.
LINHA = (
    "$cab$@WSIM-x#_@rotulo"
    "@e\\8730\\283998\\1315084\\Ancient Hash'ey Battle Art: Eye of the Lynx\\"
    "@e\\7935\\240133\\1228974\\Magilinha\\"
)


def test_extrai_encantos_do_bloco_e() -> None:
    encantos = encantos_da_linha(LINHA)
    assert encantos[8730] == {
        "item_id": 283998,
        "spell_id": 1315084,
        "nome": "Ancient Hash'ey Battle Art: Eye of the Lynx",
        "materiais": "",
    }
    assert encantos[7935]["item_id"] == 240133
    assert encantos[7935]["spell_id"] == 1228974
    assert encantos[7935]["nome"] == "Magilinha"


def test_sem_bloco_retorna_vazio() -> None:
    assert encantos_da_linha("$abc$") == {}


def _encantos_do_fixture() -> dict[int, dict]:
    saida: dict[int, dict] = {}
    for linha in BIB.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            saida.update(encantos_da_linha(linha.strip()))
    return saida


def test_fixture_real_confirma_p016() -> None:
    encantos = _encantos_do_fixture()
    assert len(encantos) == 10
    assert encantos[8730]["item_id"] == 283998
    assert encantos[8730]["spell_id"] == 1315084
    assert encantos[7935]["item_id"] == 240133
    assert encantos[7935]["spell_id"] == 1228974
    assert encantos[8689]["item_id"] == 273072
    # Nenhum campo de materiais pode vazar para a linha seguinte.
    for valor in encantos.values():
        assert "$" not in valor["materiais"]
        assert "\n" not in valor["materiais"]
