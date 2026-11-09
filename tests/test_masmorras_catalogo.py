"""T5: catálogo de M+ por masmorra e elegibilidade por classe."""

from __future__ import annotations

from collections import Counter

import pytest

from wowsim.data.classes import atributo_da_classe, tipo_armadura_da_classe
from wowsim.masmorras.catalogo import elegivel, itens_por_masmorra

pytestmark = pytest.mark.unit

# Contagens validadas contra dados/mplus_loot_database.json para Warlock
# (tecido, Intelecto): 51 elegíveis, de 4 a 8 por masmorra.
CONTAGENS_WARLOCK = {
    "Altar das Presas": 8,
    "Templo de Sethraliss": 8,
    "Murder Row": 7,
    "Descanso do Rei": 7,
    "Arena da Chaga do Caos": 6,
    "Covil de Nalorakk": 6,
    "O Vale Ofuscante": 5,
    "Piscinas da Vida Rubi": 4,
}


def _elegiveis_warlock():
    tipo = tipo_armadura_da_classe("warlock")
    atrib = atributo_da_classe("warlock")
    return [i for i in itens_por_masmorra() if elegivel(i, tipo_armadura=tipo, atributo=atrib)]


def test_contagem_por_masmorra_warlock() -> None:
    assert tipo_armadura_da_classe("warlock") == "tecido"
    assert atributo_da_classe("warlock") == "Intelecto"
    contagem = Counter(i.masmorra for i in _elegiveis_warlock())
    assert dict(contagem) == CONTAGENS_WARLOCK
    assert sum(contagem.values()) == 51


def test_nenhum_couro_elegivel_para_tecido() -> None:
    for item in itens_por_masmorra():
        if item.secao == "armadura_couro_mplus":
            assert not elegivel(item, tipo_armadura="tecido", atributo="Intelecto")


def test_todo_berloque_tem_masmorra_resolvida() -> None:
    berloques = [i for i in itens_por_masmorra() if i.slot == "trinket"]
    assert berloques
    assert all(i.masmorra for i in berloques)
