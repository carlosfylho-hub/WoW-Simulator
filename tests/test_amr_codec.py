"""Codec do AMR: diferença acumulada, confrontado com o export do SimC (fonte independente)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from wowsim.parser.amr import parse_amr, _linha_item
from wowsim.parser.amr_codec import codificar_itens, decodificar_itens

pytestmark = pytest.mark.golden

RAIZ = Path(__file__).resolve().parents[1]
AMR = (RAIZ / "fixtures" / "pyrogalth-amr-181.txt").read_text(encoding="utf-8")
SIMC = (RAIZ / "fixtures" / "pyrogalth.simc").read_text(encoding="utf-8")


def _verdade() -> dict[str, dict]:
    saida = {}
    for m in re.finditer(r"^(\w+)=,id=(\d+)(.*)$", SIMC, re.M):
        extra = m.group(3)
        def lista(campo):
            achado = re.search(campo + r"=([\d/]+)", extra)
            return sorted(int(x) for x in achado.group(1).split("/")) if achado else []
        enchant = re.search(r"enchant_id=(\d+)", extra)
        redirect = re.search(r"redirected_base_stats=(\d+)", extra)
        saida[m.group(1)] = {
            "id": int(m.group(2)),
            "gemas": lista("gem_id"),
            "enchant": int(enchant.group(1)) if enchant else None,
            "redirect": int(redirect.group(1)) if redirect else None,
        }
    return saida


def _secao(nome: str) -> list[str]:
    m = re.search(r"\." + nome + r";(.*?)(?:;\.[a-z]+\d*;|\$|$)", AMR, re.S)
    return [t for t in m.group(1).split(";") if t.strip()] if m else []


def test_todos_os_slots_batem_com_o_export_do_simc() -> None:
    verdade = _verdade()
    conjunto = parse_amr(AMR).conjunto_atual
    erros = [
        (slot, item.item_id, verdade[slot]["id"])
        for slot, item in conjunto.itens.items()
        if slot in verdade and item.item_id != verdade[slot]["id"]
    ]
    assert erros == []
    assert len([s for s in conjunto.itens if s in verdade]) == 15


def test_encantos_gemas_e_origem_do_catalisador() -> None:
    verdade = _verdade()
    conjunto = parse_amr(AMR).conjunto_atual
    for slot, item in conjunto.itens.items():
        v = verdade.get(slot)
        if not v:
            continue
        assert (item.enchant_id or None) == v["enchant"], slot
        assert sorted(item.gem_ids) == v["gemas"], slot
        if v["redirect"]:
            assert item.catalyst_source == v["redirect"], slot


def test_linha_do_simc_nao_tem_campos_corrompidos() -> None:
    conjunto = parse_amr(AMR).conjunto_atual
    for item in conjunto.itens.values():
        linha = _linha_item(item)
        assert "drop_level=" not in linha
        assert "gem_id2=" not in linha
        assert "crafting_quality=" not in linha


def test_mochila_preserva_itens_repetidos() -> None:
    itens = decodificar_itens(_secao("inv"))
    assert len(itens) == 418
    assert sum(a.item_id == b.item_id for a, b in zip(itens, itens[1:])) == 68


@pytest.mark.parametrize("secao", ["q2", "q3", "inv"])
def test_ida_e_volta_identica(secao: str) -> None:
    original = _secao(secao)
    assert codificar_itens(decodificar_itens(original)) == original
