"""O equipado do AMR vem do bloco .qN da spec ATIVA (campo 10 do cabeçalho)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.parser.addon import parse_texto
from wowsim.parser.amr import parse_amr, para_personagem
from wowsim.parser.combinar import combinar_textos

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
DRUIDA = RAIZ / "fixtures" / "ngmmexe-amr-cofre.txt"   # Equilíbrio: spec 1, tem .q1 .q2 .q3
BRUXO = RAIZ / "fixtures" / "pyrogalth-amr-181.txt"    # Demonologia: spec 2


def test_druida_equilibrio_usa_q1() -> None:
    amr = parse_amr(DRUIDA.read_text(encoding="utf-8"))
    assert amr.spec_ativa == 1
    assert amr.conjunto_atual is not None and amr.conjunto_atual.chave == "q1"


def test_bruxo_demonologia_continua_q2() -> None:
    amr = parse_amr(BRUXO.read_text(encoding="utf-8"))
    assert amr.spec_ativa == 2
    assert amr.conjunto_atual.chave == "q2"


def test_equipado_do_druida_e_o_da_spec_ativa() -> None:
    amr = parse_amr(DRUIDA.read_text(encoding="utf-8"))
    p = para_personagem(amr)
    q1 = amr.conjuntos["q1"].itens
    assert {s: i.item_id for s, i in p.equipado.items()} == {
        s: i.item_id for s, i in q1.items() if s in p.equipado
    }


def test_campo_ausente_cai_no_q2() -> None:
    amr = parse_amr(BRUXO.read_text(encoding="utf-8"))
    amr2 = amr.model_copy(update={"campo_extra": None})
    assert amr2.spec_ativa is None and amr2.conjunto_atual.chave == "q2"
