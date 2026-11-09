"""T8: opções do Grande Cofre a partir do .gv (sintético e dado real)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.masmorras.avaliar import avaliar
from wowsim.masmorras.cofre import montar_opcoes_cofre, opcoes_do_cofre
from wowsim.parser.amr import ImportAMR, parse_amr
from wowsim.parser.amr_codec import ItemAmr, codificar_itens
from wowsim.topgear.models import Conjunto
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
COFRE = RAIZ / "fixtures" / "ngmmexe-amr-cofre.txt"


def _importacao(items: list[ItemAmr]) -> ImportAMR:
    # O .gv tem o mesmo formato de diferença acumulada do .inv; codificar_itens
    # produz tokens equivalentes aos que o addon grava.
    return ImportAMR(versao="181", gv=codificar_itens(items), texto_original="")


def test_opcoes_resolvem_slot_ilvl_e_bonus() -> None:
    amr = _importacao(
        [
            ItemAmr(item_id=271483, bonus_ids=[12854]),  # head, 334
            ItemAmr(item_id=239648, bonus_ids=[8790]),   # wrist
        ]
    )
    opcoes = opcoes_do_cofre(amr)
    por_id = {op["item_id"]: op for op in opcoes}

    assert por_id[271483]["slots"] == ["head"]
    assert por_id[271483]["ilvl"] == 334  # bônus 12854 (raidbots)
    assert por_id[271483]["bonus_ids"] == [12854]

    assert por_id[239648]["slots"] == ["wrist"]
    assert por_id[239648]["bonus_ids"] == [8790]


def test_gv_vazio_nao_gera_opcoes() -> None:
    assert opcoes_do_cofre(ImportAMR(versao="181", texto_original="")) == []


def test_gv_real_do_druida_resolve_os_itens_do_cofre() -> None:
    """O cofre real (Ngmmexe) tem 2 itens de 305 na linha 'Mundo'; um token é
    placeholder sem slot e deve ser ignorado."""
    amr = parse_amr(COFRE.read_text(encoding="utf-8"))
    opcoes = {op["item_id"]: op for op in opcoes_do_cofre(amr)}

    assert opcoes[248583]["slots"] == ["trinket1", "trinket2"]  # Tambor dos Vínculos
    assert opcoes[248583]["ilvl"] == 305
    assert opcoes[272239]["slots"] == ["chest"]  # Brigandina do Espreitador
    assert opcoes[272239]["ilvl"] == 305


def test_montar_opcoes_cofre_usa_bonus_reais_e_avalia() -> None:
    amr = parse_amr(COFRE.read_text(encoding="utf-8"))
    conjuntos, opcoes = montar_opcoes_cofre(Conjunto(), amr, classe="druid")

    ids = {op.item.item_id for op in opcoes.values()}
    assert 248583 in ids
    assert 272239 in ids

    # O candidato usa os bônus REAIS do cofre, não NIVEL_PARA_BONUS.
    nome = next(n for n, op in opcoes.items() if op.item.item_id == 248583)
    slot = opcoes[nome].slot
    assert conjuntos[nome].itens[slot].bonus_ids == [6652, 12841, 13183]

    def simulador(candidatos, iterations):
        base = 100_000.0
        resultados = {}
        for nome_cand in candidatos:
            ganho = 2.0 if opcoes[nome_cand].item.item_id == 272239 else 1.0
            resultados[nome_cand] = base * (1 + ganho / 100)
        return LeituraSim(base_dps=base, resultados=resultados)

    avaliacoes = avaliar(simulador(conjuntos, 100), opcoes)
    por_id = {a.item.item_id: a for a in avaliacoes}
    assert por_id[272239].etiqueta == "direto"
    assert por_id[248583].etiqueta == "direto"
