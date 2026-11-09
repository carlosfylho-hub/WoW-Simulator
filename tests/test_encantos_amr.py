"""T16 (A-10): leitura do bloco @e de uma string de Best in Bags do AMR."""

from __future__ import annotations

import pytest

from wowsim.parser.amr_codec import encantos_da_linha

pytestmark = pytest.mark.unit

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
