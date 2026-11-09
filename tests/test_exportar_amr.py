"""T12 (núcleo): conversão do conjunto medido em string de importação do AMR."""

from __future__ import annotations

import pytest

from wowsim.exportar.amr import itens_de_conjunto, linha_importacao
from wowsim.parser.amr_codec import itens_da_linha
from wowsim.topgear.models import Candidato, Conjunto

pytestmark = pytest.mark.unit

# Cabeçalho sintético: 15 partes, com ".q2" na posição 15 (índice 14).
MODELO = "$" + ";".join([f"h{i}" for i in range(14)] + [".q2", "i0"]) + "$extra"


def test_converte_conjunto_em_itens_do_amr() -> None:
    conjunto = Conjunto(
        itens={
            "head": Candidato(
                slot="head",
                item_id=271546,
                bonus_ids=[6652, 12846],
                enchant_id=8017,
                gem_ids=[240983],
                fonte="teste",
            ),
            "legs": Candidato(
                slot="legs",
                item_id=271545,
                bonus_ids=[41],
                redirected_base_stats=273786,
                fonte="teste",
            ),
        }
    )
    itens = {item.item_id: item for item in itens_de_conjunto(conjunto)}

    assert itens[271546].slot == 1  # head
    assert itens[271546].enchant_id == 8017
    assert itens[271546].gem_ids == [240983, 0, 0]
    assert itens[271546].bonus_ids == [6652, 12846]

    assert itens[271545].slot == 7  # legs
    assert itens[271545].catalyst_source == 273786


def test_linha_de_importacao_tem_dois_cifroes_e_volta() -> None:
    conjunto = Conjunto(
        itens={
            "head": Candidato(
                slot="head", item_id=271546, bonus_ids=[6652], fonte="teste"
            )
        }
    )
    linha = linha_importacao(
        MODELO, itens_de_conjunto(conjunto), setup_id="WSIM-test", rotulo="teste"
    )
    assert linha.count("$") == 2
    volta = {item.item_id for item in itens_da_linha(linha)}
    assert 271546 in volta


def test_setup_id_com_amr_recusado() -> None:
    conjunto = Conjunto(itens={"head": Candidato(slot="head", item_id=1, fonte="x")})
    with pytest.raises(ValueError):
        linha_importacao(MODELO, itens_de_conjunto(conjunto), setup_id="AMR123", rotulo="r")
