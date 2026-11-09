"""Fase 4: núcleo do Droptimizer com simulador falso (sem simc)."""

from __future__ import annotations

import pytest

from wowsim.droptimizer import (
    DropRequest,
    ItemPossuido,
    agrupar_por_slot,
    deduplicar,
    executar_droptimizer,
    ids_do_inv,
    itens_do_inv,
    possuidos_da_mochila,
)
from wowsim.data import catalog
from wowsim.models import ItemEquipado, Personagem
from wowsim.parser.addon import parse_texto
from wowsim.parser.amr import ImportAMR, parse_amr
from wowsim.paths import PROJECT_ROOT
from wowsim.topgear.models import Candidato, ContextoSpec
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit

BASE_DPS = 100_000.0


def personagem_base() -> Personagem:
    return Personagem(
        texto_original="",
        talents_atual="ATUAL",
        equipado={
            "head": ItemEquipado(
                slot="head", item_id=1, linha_original="head=,id=1"
            ),
            "chest": ItemEquipado(
                slot="chest", item_id=2, linha_original="chest=,id=2"
            ),
        },
    )


def candidato(slot: str, item_id: int, ilvl: int = 341) -> Candidato:
    return Candidato(
        slot=slot, item_id=item_id, bonus_ids=[200], ilvl=ilvl, fonte="teste"
    )


def simulador_com_poder(poder: dict[int, float], *, erro: float = 0.05, vistos=None):
    def executar(candidatos, iterations):
        if vistos is not None and candidatos:
            vistos.append(len(candidatos))
        resultados = {}
        for nome, conjunto in candidatos.items():
            dps = BASE_DPS + sum(
                poder.get(item.item_id, 0.0) for item in conjunto.itens.values()
            )
            resultados[nome] = dps
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados=resultados,
            base_erro=erro,
            erros={nome: erro for nome in resultados},
        )

    return executar


def test_ranking_upgrade_ordena_e_classifica() -> None:
    candidatos = {
        "head": [candidato("head", 10), candidato("head", 11)]
    }
    resultado = executar_droptimizer(
        personagem_base(),
        candidatos,
        simulador=simulador_com_poder({10: 500.0, 11: 100.0}),
        request=DropRequest(addon="", iterations=100, modo="upgrade"),
        ctx=ContextoSpec(),
    )
    assert resultado.base_dps == BASE_DPS
    assert [item.item_id for item in resultado.itens] == [10, 11]
    assert resultado.itens[0].delta_pct == pytest.approx(0.5)
    assert resultado.itens[0].veredito == "ganho"
    assert resultado.itens[1].delta_pct == pytest.approx(0.1)
    assert resultado.itens[1].veredito == "empate"


def candidato_stats(slot: str, item_id: int, haste: int, ilvl: int = 341) -> Candidato:
    return Candidato(
        slot=slot,
        item_id=item_id,
        bonus_ids=[200],
        ilvl=ilvl,
        fonte="teste",
        stats={"haste": haste},
    )


def test_poda_reduz_ranking_e_mantem_vencedor() -> None:
    candidatos = {
        "head": [
            candidato_stats("head", 10, 300),
            candidato_stats("head", 11, 100),
            candidato_stats("head", 12, 50),
        ]
    }
    resultado = executar_droptimizer(
        personagem_base(),
        candidatos,
        simulador=simulador_com_poder({10: 500.0, 11: 200.0, 12: 50.0}),
        request=DropRequest(
            addon="", iterations=100, modo="upgrade", podar=True, pool_efetiva_por_slot=1
        ),
        ctx=ContextoSpec(),
    )
    # Só o top-1 do score foi medido e é o vencedor real.
    assert [item.item_id for item in resultado.itens] == [10]
    assert any("Poda heurística" in aviso for aviso in resultado.avisos)


def test_poda_desligada_mantem_todos_no_ranking() -> None:
    candidatos = {
        "head": [
            candidato_stats("head", 10, 300),
            candidato_stats("head", 11, 100),
            candidato_stats("head", 12, 50),
        ]
    }
    resultado = executar_droptimizer(
        personagem_base(),
        candidatos,
        simulador=simulador_com_poder({10: 500.0, 11: 200.0, 12: 50.0}),
        request=DropRequest(
            addon="", iterations=100, modo="upgrade", podar=False, pool_efetiva_por_slot=1
        ),
        ctx=ContextoSpec(),
    )
    assert len(resultado.itens) == 3
    assert not any("Poda heurística" in aviso for aviso in resultado.avisos)


def test_worst_in_bags_ordena_ascendente() -> None:
    resultado = executar_droptimizer(
        personagem_base(),
        {"head": [candidato("head", 10), candidato("head", 11)]},
        simulador=simulador_com_poder({10: 500.0, 11: -300.0}),
        request=DropRequest(addon="", iterations=100, modo="worst_in_bags"),
        ctx=ContextoSpec(),
    )
    assert resultado.itens[0].item_id == 11
    assert resultado.itens[0].delta_pct < 0
    assert resultado.itens[0].veredito == "perda"


def test_item_equipado_e_excluidos_saem_do_ranking() -> None:
    candidatos = {
        "head": [candidato("head", 1), candidato("head", 10)],
    }
    resultado = executar_droptimizer(
        personagem_base(),
        candidatos,
        simulador=simulador_com_poder({1: 999.0, 10: 500.0}),
        request=DropRequest(addon="", iterations=100, excluir=[10]),
        ctx=ContextoSpec(),
    )
    # item 1 é o equipado; item 10 foi excluído -> nada para comparar.
    assert resultado.itens == []
    assert resultado.avisos


def test_candidato_ilegal_e_descartado() -> None:
    personagem = personagem_base()
    personagem.equipado["main_hand"] = ItemEquipado(
        slot="main_hand", item_id=50, linha_original="main_hand=,id=50"
    )
    personagem.equipado["off_hand"] = ItemEquipado(
        slot="off_hand", item_id=51, linha_original="off_hand=,id=51"
    )
    dois_maos = Candidato(
        slot="main_hand",
        item_id=60,
        bonus_ids=[12856],
        ilvl=341,
        fonte="teste",
        tipo_arma="2h",
    )
    resultado = executar_droptimizer(
        personagem,
        {"main_hand": [dois_maos]},
        simulador=simulador_com_poder({60: 500.0}),
        request=DropRequest(addon="", iterations=100),
        ctx=ContextoSpec(exige_offhand_com_1h=True),
    )
    assert resultado.itens == []


def test_chunking_respeita_max_profilesets() -> None:
    vistos: list[int] = []
    resultado = executar_droptimizer(
        personagem_base(),
        {
            "head": [candidato("head", i) for i in range(10, 15)],
        },
        simulador=simulador_com_poder(
            {i: 100.0 * (i - 9) for i in range(10, 15)}, vistos=vistos
        ),
        request=DropRequest(addon="", iterations=100, max_profilesets_rodada=2),
        ctx=ContextoSpec(),
    )
    assert vistos and max(vistos) <= 2
    assert resultado.itens[0].item_id == 14


def test_agrupar_e_deduplicar_possuidos() -> None:
    itens = [
        ItemPossuido(slot="head", item_id=10, ilvl=334),
        ItemPossuido(slot="head", item_id=10, ilvl=334),  # duplicado
        ItemPossuido(slot="head", item_id=11, ilvl=341),
        ItemPossuido(slot="chest", item_id=20, ilvl=321),
    ]
    unicos = deduplicar(itens)
    assert len(unicos) == 3

    pools = agrupar_por_slot(unicos)
    assert [c.item_id for c in pools["head"]] == [11, 10]  # maior ilvl primeiro
    assert pools["chest"][0].fonte.startswith("possuido:")


def test_possuidos_da_mochila_simc() -> None:
    personagem = personagem_base()
    personagem.mochila = {
        "head": [
            ItemEquipado(
                slot="head",
                item_id=30,
                linha_original="head=,id=30",
                ilvl_comentario=334,
            )
        ]
    }
    itens = possuidos_da_mochila(personagem)
    assert len(itens) == 1
    assert itens[0].slot == "head"
    assert itens[0].item_id == 30
    assert itens[0].fonte == "bags_simc"
    assert itens[0].ilvl == 334


def test_ids_do_inv_do_amr() -> None:
    amr = parse_amr(
        (PROJECT_ROOT / "fixtures" / "pyrogalth-amr-181.txt").read_text(
            encoding="utf-8"
        )
    )
    ids = ids_do_inv(amr)
    assert ids
    assert all(item_id > 0 for item_id in ids)
    assert 6948 in ids  # Pedra de Regresso, presente no .inv do fixture


def test_inventory_type_do_item_data() -> None:
    assert catalog.inventory_type(239648) == 9  # wrist
    assert catalog.slots_do_item(271483) == ["head"]
    assert catalog.inventory_type(999_999_999) is None


def test_itens_do_inv_resolve_slot() -> None:
    amr = ImportAMR(
        versao="181",
        # O id do segundo token é a DIFERENÇA para o anterior: 271483 - 239648.
        inv=["239648d1!A953F0E9A", "31835n334b12854!A8BC82AA9"],
        texto_original="",
    )
    itens = itens_do_inv(amr)
    pares = {(item.item_id, item.slot) for item in itens}
    assert (239648, "wrist") in pares
    assert (271483, "head") in pares
    assert all(item.fonte == "inv_amr" for item in itens)
    cabeca = next(item for item in itens if item.item_id == 271483)
    assert cabeca.ilvl == 334  # bônus 12854 = 334


def test_ponta_a_ponta_amr_best_in_bags() -> None:
    """Export AMR real -> personagem -> possuídos -> ranking medido (simc fake)."""
    texto = (PROJECT_ROOT / "fixtures" / "pyrogalth-amr-181.txt").read_text(
        encoding="utf-8"
    )
    # parse_texto detecta o formato AMR (prefixo '$') e devolve um Personagem.
    personagem = parse_texto(texto, classe_hint="warlock", spec_hint="demonology")
    amr = parse_amr(texto)

    possuidos = deduplicar(
        list(possuidos_da_mochila(personagem)) + list(itens_do_inv(amr))
    )
    assert possuidos, "o export AMR deveria trazer itens possuídos (.inv)"
    candidatos = agrupar_por_slot(possuidos)
    assert candidatos

    def executar(conjuntos, iterations):
        def poder(item_id: int) -> float:
            return float((item_id % 97) + 1)

        resultados = {
            nome: BASE_DPS + sum(poder(item.item_id or 0) for item in conjunto.itens.values())
            for nome, conjunto in conjuntos.items()
        }
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados=resultados,
            base_erro=0.05,
            erros={nome: 0.05 for nome in resultados},
        )

    resultado = executar_droptimizer(
        personagem,
        candidatos,
        simulador=executar,
        request=DropRequest(addon="", iterations=10, modo="best_in_bags"),
        ctx=ContextoSpec(),
    )

    assert resultado.modo == "best_in_bags"
    assert resultado.base_dps == BASE_DPS
    assert resultado.itens, resultado.avisos
    deltas = [item.delta_pct for item in resultado.itens]
    assert deltas == sorted(deltas, reverse=True)
    assert all(item.veredito in ("ganho", "perda", "empate") for item in resultado.itens)


def test_upgrade_nao_exclui_item_possuido_com_trilha_superior() -> None:
    """P0-01: o mesmo item_id com ilvl superior é um upgrade legítimo."""
    from wowsim.web import drop_worker

    personagem = personagem_base()
    personagem.equipado["head"] = ItemEquipado(
        slot="head",
        item_id=1,
        ilvl_comentario=340,
        linha_original="head=,id=1",
    )
    possuidos = [ItemPossuido(slot="head", item_id=1, ilvl=350)]

    def pools_falsos(**_kwargs):
        return {
            "head": [
                candidato("head", 1, ilvl=360),  # supera o possuído -> mantém
                candidato("head", 1, ilvl=345),  # não supera -> descarta
                candidato("head", 99, ilvl=300),  # item novo -> mantém
            ]
        }

    original = drop_worker.construir_pools
    drop_worker.construir_pools = pools_falsos  # type: ignore[assignment]
    try:
        saida = drop_worker._candidatos(
            DropRequest(addon="", iterations=100, modo="upgrade"),
            personagem,
            possuidos,
        )
    finally:
        drop_worker.construir_pools = original  # type: ignore[assignment]

    ilvls = sorted(c.ilvl for c in saida["head"])
    assert ilvls == [300, 360], f"esperado manter 360 e 300, descartar 345: {ilvls}"


def test_best_in_bags_monta_conjunto_final() -> None:
    """P0-02: best_in_bags devolve o conjunto montado, não só o ranking."""
    resultado = executar_droptimizer(
        personagem_base(),
        {
            "head": [candidato("head", 10)],
            "chest": [candidato("chest", 20)],
        },
        simulador=simulador_com_poder({10: 3000.0, 20: 2000.0}),
        request=DropRequest(addon="", iterations=100, modo="best_in_bags"),
        ctx=ContextoSpec(),
    )
    assert resultado.conjunto is not None
    ids = {c.item_id for c in resultado.conjunto.itens.values()}
    assert ids == {10, 20}
    assert resultado.conjunto_dps == pytest.approx(BASE_DPS + 5000.0)
    assert resultado.delta_conjunto_pct == pytest.approx(5.0)


def test_possuidos_nao_incluem_equipados() -> None:
    """P1-03: possuídos coincidentes com o equipado são removidos."""
    from wowsim.web import drop_worker

    personagem = personagem_base()
    personagem.equipado["head"] = ItemEquipado(
        slot="head",
        item_id=1,
        ilvl_comentario=340,
        linha_original="head=,id=1",
    )
    personagem.mochila = {
        "head": [
            ItemEquipado(
                slot="head",
                item_id=1,
                ilvl_comentario=340,
                linha_original="head=,id=1",
            ),
            ItemEquipado(
                slot="head",
                item_id=30,
                ilvl_comentario=350,
                linha_original="head=,id=30",
            ),
        ]
    }
    possuidos = drop_worker._possuidos(personagem)
    assert [item.item_id for item in possuidos] == [30]


def test_inv_ignorados_conta_tokens_sem_slot() -> None:
    """P2-03: tokens do .inv sem InventoryType são contabilizados."""
    from types import SimpleNamespace

    from wowsim.droptimizer.pools import inv_ignorados

    # 1 wrist (239648) e 1 sem slot (999999999); o 2º id é a diferença acumulada.
    falsa = SimpleNamespace(inv=["239648d1", "999760351d1"])
    assert inv_ignorados(falsa) == [999999999]
