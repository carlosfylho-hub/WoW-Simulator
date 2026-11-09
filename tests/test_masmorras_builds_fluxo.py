"""T9: montagem correta (P-041/P-042) e fluxo por build com confirmação (P-043)."""

from __future__ import annotations

import pytest

from wowsim.masmorras.avaliar import Avaliacao, Opcao, avaliar
from wowsim.masmorras.builds import (
    avaliacoes_medias,
    matriz_builds,
    melhores_por_slot,
    montar_valido,
    rodar_build,
)
from wowsim.masmorras.catalogo import ItemDeMasmorra
from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit


def _item(item_id: int, slot: str = "head", masmorra: str = "D") -> ItemDeMasmorra:
    return ItemDeMasmorra(item_id, f"Item {item_id}", slot, masmorra, "armadura_tecido_mplus", None)


def _cand(slot: str, item_id: int, **extra) -> Candidato:
    return Candidato(slot=slot, item_id=item_id, fonte="teste", **extra)


def _base() -> Conjunto:
    return Conjunto(
        itens={
            "head": _cand("head", 1),
            "finger1": _cand("finger1", 2),
            "finger2": _cand("finger2", 3),
            "trinket1": _cand("trinket1", 4),
            "trinket2": _cand("trinket2", 5),
        }
    )


def _ctx(**extra) -> ContextoSpec:
    return ContextoSpec(classe="warlock", spec="demonology", **extra)


# ---------------------------------------------------------------- P-041


def test_item_para_catalisar_entra_catalisado() -> None:
    base = _base()
    item = _item(10)
    cru = _cand("head", 10)
    cat = _cand("head", 271546, redirected_base_stats=10)
    opcoes = {
        "c_10_head": Opcao("c_10_head", item, "head", False),
        "k_10_head": Opcao("k_10_head", item, "head", True),
    }
    conjuntos = {"c_10_head": base.com_troca("head", cru), "k_10_head": base.com_troca("head", cat)}
    leitura = LeituraSim(base_dps=100.0, resultados={"c_10_head": 100.05, "k_10_head": 102.0})
    avaliacoes = avaliar(leitura, opcoes)
    assert avaliacoes[0].etiqueta == "catalisar"

    escolhas = melhores_por_slot(avaliacoes, opcoes, conjuntos)
    assert escolhas["head"].item_id == 271546
    assert escolhas["head"].redirected_base_stats == 10


def test_item_direto_entra_cru_mesmo_com_catalisado_um_pouco_maior() -> None:
    base = _base()
    item = _item(10)
    opcoes = {
        "c_10_head": Opcao("c_10_head", item, "head", False),
        "k_10_head": Opcao("k_10_head", item, "head", True),
    }
    conjuntos = {
        "c_10_head": base.com_troca("head", _cand("head", 10)),
        "k_10_head": base.com_troca("head", _cand("head", 271546, redirected_base_stats=10)),
    }
    # catalisado 0,05% acima: dentro do ruído, não vale gastar a carga.
    leitura = LeituraSim(base_dps=100.0, resultados={"c_10_head": 102.0, "k_10_head": 102.05})
    avaliacoes = avaliar(leitura, opcoes)
    assert avaliacoes[0].etiqueta == "direto"
    assert melhores_por_slot(avaliacoes, opcoes, conjuntos)["head"].item_id == 10


# ---------------------------------------------------------------- P-042


def _anel(item_id: int, slot: str, ganho: float) -> tuple[Avaliacao, str, Opcao, Conjunto]:
    item = _item(item_id, "finger")
    nome = f"c_{item_id}_{slot}"
    av = Avaliacao(item, ganho, 0.15, None, None, slot, nome_cru=nome)
    return av, nome, Opcao(nome, item, slot, False), _base().com_troca(slot, _cand(slot, item_id))


def test_dois_aneis_bons_ocupam_os_dois_slots() -> None:
    a1, n1, o1, c1 = _anel(20, "finger1", 3.0)
    a2, n2, o2, c2 = _anel(21, "finger1", 2.0)  # também mediu melhor no finger1
    escolhas = melhores_por_slot([a1, a2], {n1: o1, n2: o2}, {n1: c1, n2: c2})
    assert escolhas["finger1"].item_id == 20
    assert escolhas["finger2"].item_id == 21
    assert escolhas["finger2"].slot == "finger2"


def test_mesmo_item_nao_vai_para_os_dois_slots() -> None:
    a1, n1, o1, c1 = _anel(20, "finger1", 3.0)
    a2, n2, o2, c2 = _anel(20, "finger2", 2.0)
    escolhas = melhores_por_slot([a1, a2], {n1: o1, n2: o2}, {n1: c1, n2: c2})
    assert [c.item_id for c in escolhas.values()] == [20]


def test_montar_valido_tira_a_troca_mais_fraca_ate_validar() -> None:
    base = _base()
    # Dois berloques de uso: a regra R4 permite um só.
    escolhas = {
        "trinket1": (3.0, _cand("trinket1", 30)),
        "trinket2": (1.0, _cand("trinket2", 31)),
        "head": (2.0, _cand("head", 10)),
    }
    ctx = _ctx(trinkets_on_use={30, 31})
    conjunto, trocas, descartadas = montar_valido(base, escolhas, ctx)
    assert conjunto.item_id("trinket1") == 30
    assert conjunto.item_id("trinket2") == 5  # volta ao equipado
    assert conjunto.item_id("head") == 10
    assert [slot for slot, _, _ in trocas] == ["trinket1", "head"]
    assert [slot for slot, _ in descartadas] == ["trinket2"]


# ---------------------------------------------------------------- P-043


class _SimFalso:
    """Simulador falso: DPS = 100 + soma dos bônus por item_id; ``ref`` vem dos talentos."""

    def __init__(self, ganho: dict[int, float], fator_talento: float) -> None:
        self.ganho = ganho
        self.fator = fator_talento
        self.chamadas: list[set[str]] = []

    def __call__(self, conjuntos, iterations):
        self.chamadas.append(set(conjuntos))
        resultados = {}
        for nome, conjunto in conjuntos.items():
            assert conjunto.talentos == "COD"  # P4: tudo com os talentos da build
            dps = 100.0 + sum(self.ganho.get(c.item_id, 0.0) for c in conjunto.itens.values())
            resultados[nome] = dps * self.fator
        # A base do arquivo usa OUTROS talentos: DPS diferente, nunca usado no delta.
        return LeituraSim(base_dps=50.0, resultados=resultados)


def test_rodar_build_mede_contra_ref_e_confirma_o_conjunto() -> None:
    base = _base()
    item_bom, item_ruim = _item(10), _item(11)
    conjuntos = {
        "c_10_head": base.com_troca("head", _cand("head", 10)),
        "c_11_head": base.com_troca("head", _cand("head", 11)),
    }
    opcoes = {
        "c_10_head": Opcao("c_10_head", item_bom, "head", False),
        "c_11_head": Opcao("c_11_head", item_ruim, "head", False),
    }
    sim = _SimFalso({10: 2.0, 11: -1.0}, fator_talento=2.0)

    r = rodar_build(
        base, conjuntos, opcoes, nome="m+ icy", codigo="COD", cenario="dungeon_slice",
        ctx=_ctx(), simular=sim, it_triagem=100, it_refino=1000,
    )

    assert r.ref_dps == pytest.approx(200.0)
    delta = {a.item.item_id: a.delta_cru for a in r.avaliacoes}
    assert delta[10] == pytest.approx(2.0)   # contra ref (200), não contra a base (50)
    assert r.conjunto.item_id("head") == 10
    assert r.conjunto.talentos == "COD"
    assert r.delta_conjunto == pytest.approx(2.0)
    assert r.limiar_conjunto == pytest.approx(0.15)
    # triagem, refino e confirmação; a confirmação só tem ref e montado.
    assert len(sim.chamadas) == 3
    assert sim.chamadas[-1] == {"ref", "montado"}


def test_build_sem_upgrade_nao_roda_confirmacao() -> None:
    base = _base()
    conjuntos = {"c_11_head": base.com_troca("head", _cand("head", 11))}
    opcoes = {"c_11_head": Opcao("c_11_head", _item(11), "head", False)}
    sim = _SimFalso({11: -1.0}, fator_talento=1.0)
    r = rodar_build(
        base, conjuntos, opcoes, nome="x", codigo="COD", cenario="patchwerk",
        ctx=_ctx(), simular=sim, it_triagem=100, it_refino=1000,
    )
    assert r.trocas == []
    assert r.delta_conjunto == 0.0
    assert len(sim.chamadas) == 1  # nada vivo: nem refino nem confirmação


def _av(item_id: int, delta: float, limiar: float = 0.15) -> Avaliacao:
    return Avaliacao(_item(item_id), delta, limiar, None, None, "head")


def test_matriz_media_e_divergencia() -> None:
    por_build = {"m+": [_av(10, 2.0), _av(11, 1.0)], "single": [_av(10, -1.0), _av(11, 1.0)]}
    linhas = {l["item_id"]: l for l in matriz_builds(por_build, {"m+": 0.75, "single": 0.25})}
    assert linhas[10]["media_pct"] == pytest.approx(1.25)
    assert linhas[10]["divergente"] is True
    assert linhas[11]["divergente"] is False
    assert linhas[10]["deltas"] == {"m+": 2.0, "single": -1.0}


def test_avaliacoes_medias_usam_os_pesos() -> None:
    por_build = {"a": [_av(10, 2.0, 0.2)], "b": [_av(10, 0.0, 0.1)]}
    media = avaliacoes_medias(por_build, {"a": 0.5, "b": 0.5})
    assert len(media) == 1
    assert media[0].delta_cru == pytest.approx(1.0)
    assert media[0].limiar_cru == pytest.approx(0.15)


def test_pesos_vazios_viram_iguais() -> None:
    por_build = {"a": [_av(10, 2.0)], "b": [_av(10, 0.0)]}
    assert matriz_builds(por_build, {})[0]["media_pct"] == pytest.approx(1.0)
