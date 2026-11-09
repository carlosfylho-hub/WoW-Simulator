"""Modo Craft: peças com missiva, embelezamento medido na mesma leitura (P4)."""

from __future__ import annotations

import pytest

from wowsim.masmorras import craft
from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec
from wowsim.topgear.runner import LeituraSim, _linha_item

pytestmark = pytest.mark.unit


def test_linha_do_simc_tem_ilevel_missiva_e_embelezamento() -> None:
    item = craft.ItemCraft(244572, "Dragonas", "Silvermoon Agent's Mantle", "shoulder", False)
    emb = next(e for e in craft.embelezamentos() if e.token_simc == "arcanoweave_lining")
    linha = _linha_item(craft.candidato(item, "shoulder", ("crit", "haste"), emb))
    assert linha == (
        "shoulder=,id=244572,ilevel=331,crafted_stats=32/36,embellishment=arcanoweave_lining"
    )


def test_itens_de_couro_tem_pecas_com_id_e_sem_pvp() -> None:
    itens = craft.itens_craftaveis("couro")
    ids = {i.item_id for i in itens}
    assert {244572, 244613}.issubset(ids)
    assert all("competitor" not in (i.nome_en or "").lower() for i in itens)
    assert any(i.slot == "finger" for i in itens) and any(i.slot == "neck" for i in itens)


def test_seis_pares_de_secundarios() -> None:
    assert len(craft.PARES) == 6


class _Sim:
    """Haste+mastery vale 1%; Arcanoweave soma 0,5% em cima; base 100."""

    def __call__(self, conjuntos, iterations):
        r = {}
        for nome, c in conjuntos.items():
            dps = 100.0
            for cand in c.itens.values():
                if cand.crafted_stats == [36, 49]:
                    dps += 1.0
                if cand.embelezamento_simc == "arcanoweave_lining":
                    dps += 0.5
            r[nome] = dps
        return LeituraSim(base_dps=100.0, resultados=r)


def test_rodar_craft_escolhe_a_missiva_e_mede_o_embelezamento_isolado() -> None:
    base = Conjunto(itens={"shoulder": Candidato(slot="shoulder", item_id=1, fonte="x")})
    item = craft.ItemCraft(244572, "Dragonas", "Silvermoon Agent's Mantle", "shoulder", False)
    r = craft.rodar_craft(base, [item], ctx=ContextoSpec(), simular=_Sim(), it_triagem=10, it_refino=10)
    assert r.pecas[0]["missiva"] == "Aceleração + Maestria"
    assert r.pecas[0]["ganho_pct"] == pytest.approx(1.0)
    arcano = next(e for e in r.embelezamentos if e["nome_en"] == "Arcanoweave Lining")
    assert arcano["ganho_pct"] == pytest.approx(0.5)        # só o efeito
    assert arcano["ganho_total_pct"] == pytest.approx(1.5)  # peça + efeito
    assert r.embelezamentos[0]["nome_en"] == "Arcanoweave Lining"


def test_teto_de_dois_embelezamentos_impede_o_terceiro() -> None:
    base = Conjunto(
        itens={
            "shoulder": Candidato(slot="shoulder", item_id=1, fonte="x"),
            "wrist": Candidato(slot="wrist", item_id=2, fonte="x", embelezamento=True),
            "waist": Candidato(slot="waist", item_id=3, fonte="x", embelezamento=True),
        }
    )
    item = craft.ItemCraft(244572, "Dragonas", "Silvermoon Agent's Mantle", "shoulder", False)
    r = craft.rodar_craft(base, [item], ctx=ContextoSpec(), simular=_Sim(), it_triagem=10, it_refino=10)
    assert r.embelezamentos == []
    assert any("não medido" in a for a in r.avisos)


def test_fase1_nao_mede_peca_embutida_quando_ja_ha_dois_embutidos() -> None:
    # Peito e mãos já vêm com embelezamento embutido; mais um nos pés = 3 efeitos.
    base = Conjunto(
        itens={
            "chest": Candidato(slot="chest", item_id=244613, fonte="craft"),
            "hands": Candidato(slot="hands", item_id=244614, fonte="craft"),
        }
    )
    ctx = ContextoSpec(embelezamentos={244613, 244614})
    item = craft.ItemCraft(244601, "Ataduras", "Rootbound Wraps", "feet", True)
    r = craft.rodar_craft(base, [item], ctx=ctx, simular=_Sim(), it_triagem=10, it_refino=10)
    assert all(p["item_id"] != 244601 for p in r.pecas)
    assert any(b["item_id"] == 244601 for b in r.bloqueados)
    assert any("embutido" in b["motivo"] for b in r.bloqueados)


def test_fase1_mede_peca_embutida_quando_ha_so_um_embutido() -> None:
    base = Conjunto(
        itens={"chest": Candidato(slot="chest", item_id=244613, fonte="craft")}
    )
    ctx = ContextoSpec(embelezamentos={244613})
    item = craft.ItemCraft(244601, "Ataduras", "Rootbound Wraps", "feet", True)
    r = craft.rodar_craft(base, [item], ctx=ctx, simular=_Sim(), it_triagem=10, it_refino=10)
    assert any(p["item_id"] == 244601 for p in r.pecas)
    assert r.bloqueados == []


class _SimEmb:
    """Base 100; Presa Adornada (adorned_fang) vale 0,4%; missiva Ace+Mae +1%."""

    def __call__(self, conjuntos, iterations):
        r = {}
        for nome, c in conjuntos.items():
            dps = 100.0
            for cand in c.itens.values():
                if cand.crafted_stats == [36, 49]:
                    dps += 1.0
                if cand.embelezamento_simc == "adorned_fang":
                    dps += 0.4
            r[nome] = dps
        return LeituraSim(base_dps=100.0, resultados=r)


def test_fase2_troca_o_reagente_quando_o_teto_esta_cheio() -> None:
    # Dois embelezamentos aplicados (bônus): Arcanotrama nas costas e Elo Devorador
    # na cintura. No teto, a fase 2 deve TROCAR o reagente, não somar um terceiro.
    base = Conjunto(
        itens={
            "back": Candidato(
                slot="back", item_id=239656, fonte="craft", bonus_ids=[12384]
            ),
            "waist": Candidato(
                slot="waist", item_id=239649, fonte="craft", bonus_ids=[12685]
            ),
        }
    )
    item = craft.ItemCraft(244572, "Dragonas", "Mantle", "shoulder", False)
    r = craft.rodar_craft(
        base, [item], ctx=ContextoSpec(), simular=_SimEmb(), it_triagem=10, it_refino=10
    )
    trocas = [e for e in r.embelezamentos if e["tipo"] == "troca"]
    presa = next(e for e in trocas if e["nome_en"] == "Adorned Fang")
    assert presa["ganho_pct"] == pytest.approx(0.4)
    assert presa["troca_de"] in ("Forro de Arcanotrama", "Elo Devorador")
    assert presa["slot_medido"] in ("back", "waist")


def test_fase2_troca_a_peca_embutida_quando_so_ha_embutidos() -> None:
    # Peito e mãos embutidos (teto cheio). A peça craftada de peito com Presa
    # Adornada substitui a peça embutida inteira.
    base = Conjunto(
        itens={
            "chest": Candidato(slot="chest", item_id=244613, fonte="craft"),
            "hands": Candidato(slot="hands", item_id=244614, fonte="craft"),
        }
    )
    ctx = ContextoSpec(embelezamentos={244613, 244614})
    item = craft.ItemCraft(244571, "Vestes", "Robes", "chest", False)
    r = craft.rodar_craft(
        base, [item], ctx=ctx, simular=_SimEmb(), it_triagem=10, it_refino=10
    )
    pecas_emb = [e for e in r.embelezamentos if e["tipo"] == "peca"]
    presa = next(e for e in pecas_emb if e["nome_en"] == "Adorned Fang")
    assert presa["slot_medido"] == "chest"
    assert presa["troca_de"] == "244613"
