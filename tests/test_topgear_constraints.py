"""Unit tests for the Top Gear constraint validator."""

from __future__ import annotations

import pytest

from wowsim.topgear.constraints import avisos, validar
from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec

pytestmark = pytest.mark.unit


def cand(slot: str, item_id: int | None = None, **kwargs) -> Candidato:
    dados = {"slot": slot, "item_id": item_id, "fonte": "teste"}
    dados.update(kwargs)
    return Candidato(**dados)


def test_conjunto_vazio_e_valido() -> None:
    ok, motivos = validar(Conjunto(), ContextoSpec())
    assert ok is True
    assert motivos == []


def test_embelezamentos_limite() -> None:
    ctx = ContextoSpec(max_embelezamentos=2)
    conjunto = Conjunto(
        itens={
            "head": cand("head", 1, embelezamento=True),
            "chest": cand("chest", 2, embelezamento=True),
        }
    )
    assert validar(conjunto, ctx) == (True, [])

    conjunto.itens["legs"] = cand("legs", 3, embelezamento=True)
    ok, motivos = validar(conjunto, ctx)
    assert ok is False
    assert any("embelezamentos" in motivo for motivo in motivos)


def test_embelezamento_por_catalogo() -> None:
    ctx = ContextoSpec(embelezamentos={10, 11, 12})
    conjunto = Conjunto(
        itens={
            "head": cand("head", 10),
            "chest": cand("chest", 11),
            "legs": cand("legs", 12),
        }
    )
    ok, motivos = validar(conjunto, ctx)
    assert ok is False
    assert any("embelezamentos" in motivo for motivo in motivos)


def test_diamante_prismatico_unico() -> None:
    ctx = ContextoSpec(diamantes={900, 901})
    um = Conjunto(itens={"head": cand("head", 1, gem_ids=[900])})
    assert validar(um, ctx) == (True, [])

    dois = Conjunto(
        itens={
            "head": cand("head", 1, gem_ids=[900]),
            "chest": cand("chest", 2, gem_ids=[901]),
        }
    )
    ok, motivos = validar(dois, ctx)
    assert ok is False
    assert any("diamantes" in motivo for motivo in motivos)


def test_berloques_on_use() -> None:
    ctx = ContextoSpec(max_on_use=1)
    ativo_passivo = Conjunto(
        itens={
            "trinket1": cand("trinket1", 1, tipo_efeito="ativo"),
            "trinket2": cand("trinket2", 2, tipo_efeito="passivo"),
        }
    )
    assert validar(ativo_passivo, ctx) == (True, [])

    ativo_passivo.itens["trinket2"] = cand("trinket2", 2, tipo_efeito="ativo")
    ok, motivos = validar(ativo_passivo, ctx)
    assert ok is False
    assert any("on-use" in motivo for motivo in motivos)


def test_dois_berloques_de_uso_sao_permitidos_por_padrao() -> None:
    # O jogo não proíbe: sem ``max_on_use`` o par passa e vira só aviso.
    ctx = ContextoSpec(trinkets_on_use={500, 501})
    conjunto = Conjunto(
        itens={
            "trinket1": cand("trinket1", 500),
            "trinket2": cand("trinket2", 501),
        }
    )
    assert validar(conjunto, ctx) == (True, [])
    assert any("Dois berloques de uso" in a for a in avisos(conjunto, ctx))


def test_berloque_on_use_por_catalogo_com_limite_explicito() -> None:
    ctx = ContextoSpec(trinkets_on_use={500, 501}, max_on_use=1)
    conjunto = Conjunto(
        itens={
            "trinket1": cand("trinket1", 500),
            "trinket2": cand("trinket2", 501),
        }
    )
    ok, motivos = validar(conjunto, ctx)
    assert ok is False
    assert any("on-use" in motivo for motivo in motivos)


def test_arma_duas_maos_exclui_offhand() -> None:
    ctx = ContextoSpec()
    conjunto = Conjunto(
        itens={
            "main_hand": cand("main_hand", 1, tipo_arma="2h"),
            "off_hand": cand("off_hand", 2),
        }
    )
    ok, motivos = validar(conjunto, ctx)
    assert ok is False
    assert any("duas mãos" in motivo for motivo in motivos)


def test_uma_mao_exige_offhand_valido() -> None:
    ctx = ContextoSpec(offs_validos={20})
    valido = Conjunto(
        itens={
            "main_hand": cand("main_hand", 1, tipo_arma="1h"),
            "off_hand": cand("off_hand", 20),
        }
    )
    assert validar(valido, ctx) == (True, [])

    invalido = valido.com_troca("off_hand", cand("off_hand", 21))
    ok, motivos = validar(invalido, ctx)
    assert ok is False
    assert any("incompatível" in motivo for motivo in motivos)

    sem_offhand = Conjunto(itens={"main_hand": cand("main_hand", 1, tipo_arma="1h")})
    ok, motivos = validar(sem_offhand, ctx)
    assert ok is False
    assert any("exige" in motivo for motivo in motivos)


def test_folio_valido_e_invalido() -> None:
    ctx = ContextoSpec()
    valido = Conjunto(runas_folio=["1A", "2B", "3A", "4D", "5C"])
    assert validar(valido, ctx) == (True, [])

    linha_repetida = Conjunto(runas_folio=["1A", "1B", "3A", "4D", "5C"])
    ok, motivos = validar(linha_repetida, ctx)
    assert ok is False
    assert any("linha" in motivo for motivo in motivos)

    poucas = Conjunto(runas_folio=["1A", "2B", "3A"])
    ok, motivos = validar(poucas, ctx)
    assert ok is False
    assert any("5 runas" in motivo for motivo in motivos)

    invalida = Conjunto(runas_folio=["1A", "2B", "3A", "4D", "X"])
    ok, motivos = validar(invalida, ctx)
    assert ok is False
    assert any("inválida" in motivo for motivo in motivos)


def test_craft_respeita_teto() -> None:
    ctx = ContextoSpec(craft_ilvl_teto=331)
    ok_conjunto = Conjunto(
        itens={"back": cand("back", 1, craftado=True, ilvl=331)}
    )
    assert validar(ok_conjunto, ctx) == (True, [])

    acima = Conjunto(itens={"back": cand("back", 1, craftado=True, ilvl=341)})
    ok, motivos = validar(acima, ctx)
    assert ok is False
    assert any("craftado" in motivo for motivo in motivos)


def test_avisos_de_tier() -> None:
    ctx = ContextoSpec(tier_ids={1, 2, 3, 4})
    uma = Conjunto(itens={"head": cand("head", 1)})
    assert avisos(uma, ctx)

    tres = Conjunto(
        itens={
            "head": cand("head", 1),
            "chest": cand("chest", 2),
            "legs": cand("legs", 3),
        }
    )
    assert avisos(tres, ctx)

    quatro = Conjunto(
        itens={
            "head": cand("head", 1),
            "chest": cand("chest", 2),
            "legs": cand("legs", 3),
            "hands": cand("hands", 4),
        }
    )
    assert avisos(quatro, ctx) == []
