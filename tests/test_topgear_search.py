"""Deterministic search tests using a fake simulator (no simc needed)."""

from __future__ import annotations

import pytest

from wowsim.models import ItemEquipado, Personagem
from wowsim.topgear.models import Candidato, ContextoSpec, TopGearRequest
from wowsim.topgear.pools import consumiveis, gemas_catalogo
from wowsim.topgear.runner import LeituraSim, linhas_override
from wowsim.topgear.search import conjunto_do_personagem, executar_topgear

pytestmark = pytest.mark.unit

BASE_DPS = 100_000.0


def personagem_base() -> Personagem:
    return Personagem(
        texto_original="",
        talents_atual="ATUAL",
        equipado={
            "head": ItemEquipado(
                slot="head",
                item_id=1,
                bonus_ids=[100],
                linha_original="head=,id=1,bonus_id=100",
            ),
            "chest": ItemEquipado(
                slot="chest",
                item_id=2,
                linha_original="chest=,id=2",
            ),
        },
    )


def simulador_falso(poder: dict[int, float]):
    """DPS = base + sum(power[item_id]); ignores iterations on purpose."""

    def executar(candidatos, iterations):
        if not candidatos:
            return LeituraSim(base_dps=BASE_DPS, resultados={})
        resultados = {}
        for nome, conjunto in candidatos.items():
            dps = BASE_DPS
            for candidato in conjunto.itens.values():
                dps += poder.get(candidato.item_id, 0.0)
            resultados[nome] = dps
        return LeituraSim(base_dps=BASE_DPS, resultados=resultados)

    return executar


def candidato_head(item_id: int, poder: float = 0.0, **kwargs) -> Candidato:
    dados = {
        "slot": "head",
        "item_id": item_id,
        "bonus_ids": [200],
        "ilvl": 341,
        "fonte": "teste",
    }
    dados.update(kwargs)
    return Candidato(**dados)


def pedido(**kwargs) -> TopGearRequest:
    dados = {
        "addon": "",
        "scenario": "patchwerk",
        "iterations_triagem": 100,
        "iterations_refino": 100,
        "max_profilesets_rodada": 100,
        "orcamento_segundos": 60,
        "pool_por_slot": 10,
    }
    dados.update(kwargs)
    return TopGearRequest(**dados)


def test_busca_encontra_melhor_item() -> None:
    personagem = personagem_base()
    pools = {
        "head": [
            candidato_head(10, poder=500.0),
            candidato_head(11, poder=200.0),
        ]
    }
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso({10: 500.0, 11: 200.0}),
        request=pedido(),
        ctx=ContextoSpec(),
    )

    assert resultado.melhor.item_id("head") == 10
    assert resultado.melhor_dps == pytest.approx(BASE_DPS + 500.0)
    assert resultado.delta_pct == pytest.approx(0.5)
    assert resultado.trocas and resultado.trocas[0].slot == "head"
    assert resultado.trocas[0].para_item_id == 10
    assert resultado.rodadas


def test_poda_mantem_vencedor_e_encolhe_rodada() -> None:
    personagem = personagem_base()
    # Haste cresce junto com o poder medido, então o top-1 do score é o vencedor.
    pools = {
        "head": [
            candidato_head(10, stats={"haste": 300}),
            candidato_head(11, stats={"haste": 100}),
            candidato_head(12, stats={"haste": 50}),
        ]
    }
    poder = {10: 800.0, 11: 300.0, 12: 100.0}
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso(poder),
        request=pedido(podar=True, pool_efetiva_por_slot=1),
        ctx=ContextoSpec(),
    )

    # O vencedor sobreviveu à poda.
    assert resultado.melhor.item_id("head") == 10
    # A rodada de poda registrou o total descartado (3 candidatos - top 1 = 2).
    poda = [r for r in resultado.rodadas if r.estagio == "poda"]
    assert poda and poda[0].candidatos == 2
    assert any("Poda heurística" in aviso for aviso in resultado.avisos)


def test_poda_desligada_nao_descarta() -> None:
    personagem = personagem_base()
    pools = {
        "head": [
            candidato_head(10, stats={"haste": 300}),
            candidato_head(11, stats={"haste": 100}),
            candidato_head(12, stats={"haste": 50}),
        ]
    }
    poder = {10: 800.0, 11: 300.0, 12: 100.0}
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso(poder),
        request=pedido(podar=False, pool_efetiva_por_slot=1),
        ctx=ContextoSpec(),
    )

    assert resultado.melhor.item_id("head") == 10
    assert not any(r.estagio == "poda" for r in resultado.rodadas)
    assert not any("Poda heurística" in aviso for aviso in resultado.avisos)


def test_verificacao_recupera_candidato_podado() -> None:
    personagem = personagem_base()
    # item 11 tem score baixo (é podado), mas DPS muito maior.
    pools = {
        "head": [
            candidato_head(10, stats={"haste": 300}),
            candidato_head(11, stats={"haste": 10}),
        ]
    }
    poder = {10: 100.0, 11: 900.0}
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso(poder),
        request=pedido(podar=True, pool_efetiva_por_slot=1, verificar_podados=True),
        ctx=ContextoSpec(),
    )

    assert resultado.melhor.item_id("head") == 11
    assert any("recuperado" in aviso for aviso in resultado.avisos)
    assert any(r.estagio == "verificacao" for r in resultado.rodadas)


def test_verificacao_confirma_k_suficiente() -> None:
    personagem = personagem_base()
    pools = {
        "head": [
            candidato_head(10, stats={"haste": 300}),
            candidato_head(11, stats={"haste": 10}),
        ]
    }
    poder = {10: 900.0, 11: 50.0}
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso(poder),
        request=pedido(podar=True, pool_efetiva_por_slot=1, verificar_podados=True),
        ctx=ContextoSpec(),
    )

    assert resultado.melhor.item_id("head") == 10
    assert any("suficiente" in aviso for aviso in resultado.avisos)


def _sem_duracao(resultado) -> dict:
    """Dump do resultado sem a cronometragem de cada rodada."""
    dados = resultado.model_dump()
    dados["rodadas"] = [
        {campo: valor for campo, valor in rodada.items() if campo != "duracao_s"}
        for rodada in dados["rodadas"]
    ]
    return dados


def test_busca_e_deterministica() -> None:
    personagem = personagem_base()
    pools = {
        "head": [candidato_head(10, poder=500.0), candidato_head(11, poder=200.0)]
    }
    simulador = simulador_falso({10: 500.0, 11: 200.0})

    primeiro = executar_topgear(
        personagem, pools, simulador=simulador, request=pedido(), ctx=ContextoSpec()
    )
    segundo = executar_topgear(
        personagem, pools, simulador=simulador, request=pedido(), ctx=ContextoSpec()
    )
    # ``duracao_s`` é tempo de parede: nunca se repete entre execuções e não faz
    # parte do determinismo da busca. Comparar o dump cru deixava o teste instável.
    assert _sem_duracao(primeiro) == _sem_duracao(segundo)


def test_sem_pools_retorna_base() -> None:
    resultado = executar_topgear(
        personagem_base(),
        {},
        simulador=simulador_falso({}),
        request=pedido(),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor_dps == BASE_DPS
    assert resultado.delta_pct == 0.0
    assert resultado.trocas == []
    assert any("Nenhum candidato" in aviso for aviso in resultado.avisos)


def test_slot_travado_nao_muda() -> None:
    pools = {"head": [candidato_head(10, poder=500.0)]}
    resultado = executar_topgear(
        personagem_base(),
        pools,
        simulador=simulador_falso({10: 500.0}),
        request=pedido(slots_travados={"head": 1}),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.item_id("head") == 1
    assert resultado.melhor_dps == BASE_DPS


def test_restricao_descarta_candidato_ilegal() -> None:
    personagem = personagem_base()
    personagem.equipado["main_hand"] = ItemEquipado(
        slot="main_hand", item_id=50, linha_original="main_hand=,id=50"
    )
    personagem.equipado["off_hand"] = ItemEquipado(
        slot="off_hand", item_id=51, linha_original="off_hand=,id=51"
    )
    pools = {
        "main_hand": [
            Candidato(
                slot="main_hand",
                item_id=60,
                bonus_ids=[12856],
                ilvl=341,
                fonte="teste",
                tipo_arma="2h",
            )
        ]
    }
    resultado = executar_topgear(
        personagem,
        pools,
        simulador=simulador_falso({60: 500.0}),
        request=pedido(),
        ctx=ContextoSpec(),
    )
    # 2M com off_hand é ilegal, então nenhum candidato é simulado.
    assert resultado.melhor.item_id("main_hand") == 50
    assert resultado.melhor_dps == BASE_DPS
    assert resultado.trocas == []
    assert any("Nenhum candidato" in aviso for aviso in resultado.avisos)


def simulador_por_funcao(funcao):
    def executar(candidatos, iterations):
        if not candidatos:
            return LeituraSim(base_dps=BASE_DPS, resultados={})
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados={nome: funcao(conjunto) for nome, conjunto in candidatos.items()},
        )

    return executar


def test_otimiza_encantos() -> None:
    personagem = personagem_base()
    personagem.equipado["head"].enchant_id = 100

    def funcao(conjunto):
        enchant = conjunto.itens["head"].enchant_id
        return BASE_DPS + (1000.0 if enchant != 100 else 0.0)

    resultado = executar_topgear(
        personagem,
        {},
        simulador=simulador_por_funcao(funcao),
        request=pedido(incluir=["encanto"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.itens["head"].enchant_id not in (None, 100)
    assert resultado.delta_pct > 0


def test_otimiza_gemas() -> None:
    gemas = gemas_catalogo()
    atual = next(g for g in gemas if "diamante" not in (g.tipo or "").lower())
    familia = (atual.tipo or "").lower().split("(")[0].strip()
    alternativa = next(
        g
        for g in gemas
        if g.item_id != atual.item_id
        and (g.tipo or "").lower().split("(")[0].strip() == familia
    )

    personagem = personagem_base()
    personagem.equipado["head"].gem_ids = [atual.item_id]

    def funcao(conjunto):
        gems = conjunto.itens["head"].gem_ids
        return BASE_DPS + (1000.0 if gems and gems[0] != atual.item_id else 0.0)

    resultado = executar_topgear(
        personagem,
        {},
        simulador=simulador_por_funcao(funcao),
        request=pedido(incluir=["gema"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.itens["head"].gem_ids[0] == alternativa.item_id
    assert resultado.delta_pct > 0


def test_otimiza_talentos() -> None:
    personagem = personagem_base()
    personagem.loadouts = {"raid": "RAID", "mplus": "MPLUS"}

    def funcao(conjunto):
        return BASE_DPS + (1000.0 if conjunto.talentos == "MPLUS" else 0.0)

    resultado = executar_topgear(
        personagem,
        {},
        simulador=simulador_por_funcao(funcao),
        request=pedido(incluir=["talento"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.talentos == "MPLUS"
    assert resultado.delta_pct > 0


def test_otimiza_folio() -> None:
    def funcao(conjunto):
        alvo = conjunto.runas_folio and conjunto.runas_folio[0] == "1B"
        return BASE_DPS + (1000.0 if alvo else 0.0)

    resultado = executar_topgear(
        personagem_base(),
        {},
        simulador=simulador_por_funcao(funcao),
        request=pedido(incluir=["folio"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.runas_folio[0] == "1B"
    assert len(resultado.melhor.runas_folio) == 5
    assert resultado.delta_pct > 0


def test_incluir_desativa_etapas() -> None:
    personagem = personagem_base()
    personagem.loadouts = {"raid": "RAID"}

    def funcao(conjunto):
        return BASE_DPS + (1000.0 if conjunto.talentos == "RAID" else 0.0)

    resultado = executar_topgear(
        personagem,
        {},
        simulador=simulador_por_funcao(funcao),
        request=pedido(incluir=[]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.talentos == "ATUAL"
    assert resultado.delta_pct == 0.0


def simulador_por_funcao_iter(funcao):
    def executar(candidatos, iterations):
        if not candidatos:
            return LeituraSim(base_dps=BASE_DPS, resultados={})
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados={
                nome: funcao(conjunto, iterations)
                for nome, conjunto in candidatos.items()
            },
        )

    return executar


def candidato(slot: str, item_id: int) -> Candidato:
    return Candidato(
        slot=slot, item_id=item_id, bonus_ids=[200], ilvl=341, fonte="teste"
    )


def test_beam_captura_interacao_entre_dois_slots() -> None:
    def funcao(conjunto, iterations):
        ids = {c.item_id for c in conjunto.itens.values()}
        dps = BASE_DPS
        dps += 1000.0 if 20 in ids else 0.0  # melhor sozinho
        dps -= 100.0 if 21 in ids else 0.0
        dps -= 100.0 if 30 in ids else 0.0
        dps += 5000.0 if {21, 30} <= ids else 0.0  # só o par compensa
        return dps

    resultado = executar_topgear(
        personagem_base(),
        {
            "chest": [candidato("chest", 20), candidato("chest", 21)],
            "legs": [candidato("legs", 30)],
        },
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=[]),
        ctx=ContextoSpec(),
    )
    # A gulosa escolhe o item 20; o beam percebe que 21 + 30 vale mais.
    assert resultado.melhor.item_id("chest") == 21
    assert resultado.melhor.item_id("legs") == 30
    assert resultado.delta_pct > 4.0
    assert any(rodada.estagio == "beam" for rodada in resultado.rodadas)


def test_refino_remede_com_iteracoes_maiores() -> None:
    def funcao(conjunto, iterations):
        extra = 50.0 if iterations >= 500 else 0.0
        dps = BASE_DPS + extra
        for item in conjunto.itens.values():
            if item.item_id == 10:
                dps += 1000.0
        return dps

    resultado = executar_topgear(
        personagem_base(),
        {"head": [candidato_head(10)]},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=[], iterations_refino=500),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.item_id("head") == 10
    assert resultado.melhor_dps == pytest.approx(BASE_DPS + 1050.0)
    assert any(rodada.estagio == "refino" for rodada in resultado.rodadas)


def test_pool_de_consumiveis_tem_tokens_do_simc() -> None:
    pools = consumiveis()
    for categoria in ("flask", "potion", "food", "augmentation"):
        assert pools.get(categoria)
        assert all(candidato.valor for candidato in pools[categoria])
    assert any(
        candidato.valor == "flask_of_the_shattered_sun_2"
        for candidato in pools["flask"]
    )


def test_otimiza_consumiveis() -> None:
    def funcao(conjunto, iterations):
        dps = BASE_DPS
        if conjunto.flask:
            dps += 1000.0
        if conjunto.potion:
            dps += 500.0
        if conjunto.food:
            dps += 500.0
        if conjunto.augmentation:
            dps += 500.0
        return dps

    resultado = executar_topgear(
        personagem_base(),
        {},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=["flask", "potion", "food", "augmentation"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.flask
    assert resultado.melhor.potion
    assert resultado.melhor.food
    assert resultado.melhor.augmentation
    assert resultado.delta_pct > 0
    assert any(rodada.estagio == "consumiveis" for rodada in resultado.rodadas)
    assert {troca.slot for troca in resultado.trocas} >= {
        "flask",
        "potion",
        "food",
        "augmentation",
    }


def test_talentos_extras_sao_testados() -> None:
    def funcao(conjunto, iterations):
        return BASE_DPS + (1000.0 if conjunto.talentos == "EXTRA" else 0.0)

    resultado = executar_topgear(
        personagem_base(),
        {},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=["talento"], talentos_extra=["EXTRA"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.talentos == "EXTRA"
    assert resultado.delta_pct > 0


def test_linhas_override_incluem_bonus_e_talentos() -> None:
    personagem = personagem_base()
    base = conjunto_do_personagem(personagem)
    assert base.itens["head"].bonus_ids == [100]
    assert base.talentos == "ATUAL"

    conjunto = base.com_troca(
        "head",
        Candidato(
            slot="head",
            item_id=99,
            bonus_ids=[12856],
            ilvl=341,
            fonte="teste",
        ),
    )
    linhas = linhas_override(conjunto)
    assert "head=,id=99,bonus_id=12856" in linhas
    assert "talents=ATUAL" in linhas

    consumiveis_conjunto = conjunto.model_copy(
        update={
            "flask": "flask_of_the_shattered_sun_2",
            "potion": "lights_potential_2",
            "food": "harandar_celebration",
            "augmentation": "void_touched",
        }
    )
    linhas_consumiveis = linhas_override(consumiveis_conjunto)
    assert "flask=flask_of_the_shattered_sun_2" in linhas_consumiveis
    assert "potion=lights_potential_2" in linhas_consumiveis
    assert "food=harandar_celebration" in linhas_consumiveis
    assert "augmentation=void_touched" in linhas_consumiveis


def simulador_com_erro(valor_ganho: float, erro: float):
    """Fake simulator that reports a measured error for every variant (P0-04)."""

    def executar(candidatos, iterations):
        resultados = {
            nome: BASE_DPS + (valor_ganho if c.item_id("head") == 11 else 0.0)
            for nome, c in candidatos.items()
        }
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados=resultados,
            base_erro=erro,
            erros={nome: erro for nome in resultados},
        )

    return executar


def test_limiar_por_erro_ignora_ganho_dentro_do_ruido() -> None:
    resultado = executar_topgear(
        personagem_base(),
        {"head": [candidato_head(11)]},
        simulador=simulador_com_erro(valor_ganho=300.0, erro=0.5),
        request=pedido(incluir=[]),
        ctx=ContextoSpec(),
    )
    # +0,30% fica abaixo do erro medido de 0,5%: nada é aceito.
    assert resultado.melhor.item_id("head") == 1
    assert resultado.melhor_dps == pytest.approx(BASE_DPS)


def test_limiar_por_erro_aceita_ganho_acima_do_ruido() -> None:
    resultado = executar_topgear(
        personagem_base(),
        {"head": [candidato_head(11)]},
        simulador=simulador_com_erro(valor_ganho=300.0, erro=0.05),
        request=pedido(incluir=[]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.item_id("head") == 11
    assert resultado.melhor_dps == pytest.approx(BASE_DPS + 300.0)


def test_chunking_respeita_max_profilesets_sem_mudar_resultado() -> None:
    poder = {10: 100.0, 11: 500.0, 12: 300.0, 13: 200.0, 14: 400.0}
    pools = {"head": [candidato_head(item_id) for item_id in poder]}

    def executar(tamanhos: list[int]):
        def simulador(candidatos, iterations):
            if candidatos:
                tamanhos.append(len(candidatos))
            return LeituraSim(
                base_dps=BASE_DPS,
                resultados={
                    nome: BASE_DPS + poder[c.item_id("head")]
                    for nome, c in candidatos.items()
                },
            )

        return simulador

    tamanhos_fatiados: list[int] = []
    fatiado = executar_topgear(
        personagem_base(),
        pools,
        simulador=executar(tamanhos_fatiados),
        request=pedido(incluir=[], max_profilesets_rodada=2),
        ctx=ContextoSpec(),
    )
    assert tamanhos_fatiados and max(tamanhos_fatiados) <= 2

    tamanhos_inteiros: list[int] = []
    inteiro = executar_topgear(
        personagem_base(),
        pools,
        simulador=executar(tamanhos_inteiros),
        request=pedido(incluir=[], max_profilesets_rodada=1000),
        ctx=ContextoSpec(),
    )
    # O resultado medido é idêntico; apenas o número de chamadas muda.
    assert fatiado.melhor.item_id("head") == inteiro.melhor.item_id("head") == 11
    assert fatiado.melhor_dps == pytest.approx(inteiro.melhor_dps)


def test_slot_travado_preserva_encanto_e_gema() -> None:
    gemas = gemas_catalogo()
    atual = next(g for g in gemas if "diamante" not in (g.tipo or "").lower())

    personagem = personagem_base()
    personagem.equipado["head"].enchant_id = 100
    personagem.equipado["head"].gem_ids = [atual.item_id]

    def funcao(conjunto, iterations):
        cabeca = conjunto.itens["head"]
        dps = BASE_DPS
        if cabeca.enchant_id not in (None, 100):
            dps += 1000.0
        if cabeca.gem_ids and cabeca.gem_ids[0] != atual.item_id:
            dps += 1000.0
        return dps

    resultado = executar_topgear(
        personagem,
        {},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=["encanto", "gema"], slots_travados={"head": 1}),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.itens["head"].enchant_id == 100
    assert resultado.melhor.itens["head"].gem_ids == [atual.item_id]


def test_incluir_filtra_categorias_de_consumiveis() -> None:
    def funcao(conjunto, iterations):
        dps = BASE_DPS
        for campo in ("flask", "potion", "food", "augmentation"):
            if getattr(conjunto, campo):
                dps += 500.0
        return dps

    resultado = executar_topgear(
        personagem_base(),
        {},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=["flask"]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.flask
    assert resultado.melhor.potion is None
    assert resultado.melhor.food is None
    assert resultado.melhor.augmentation is None


def test_conjuntos_estaveis_independem_da_ordem_e_rotulo() -> None:
    from wowsim.topgear.runner import conjuntos_estaveis

    base = conjunto_do_personagem(personagem_base())
    c10 = base.com_troca("head", candidato_head(10))
    c11 = base.com_troca("head", candidato_head(11))

    a = conjuntos_estaveis({"r1_head_10_0": c10, "r1_head_11_1": c11})
    b = conjuntos_estaveis({"r9_head_11_9": c11, "r9_head_10_9": c10})
    assert set(a) == set(b)
    assert len(a) == 2


def test_refino_nao_abaixa_melhor_dps() -> None:
    def funcao(conjunto, iterations):
        dps = BASE_DPS
        for item in conjunto.itens.values():
            if item.item_id == 10:
                dps += 1000.0
        if iterations >= 500:  # refino mede menor por ruído
            dps -= 200.0
        return dps

    resultado = executar_topgear(
        personagem_base(),
        {"head": [candidato_head(10)]},
        simulador=simulador_por_funcao_iter(funcao),
        request=pedido(incluir=[], iterations_refino=500),
        ctx=ContextoSpec(),
    )
    # A triagem dá BASE+1000; o refino ruidoso daria BASE+800, mas o maior é mantido.
    assert resultado.melhor_dps == pytest.approx(BASE_DPS + 1000.0)


def test_excluir_remove_candidato() -> None:
    pools = {"head": [candidato_head(10), candidato_head(11)]}

    def simulador(candidatos, iterations):
        return LeituraSim(
            base_dps=BASE_DPS,
            resultados={
                nome: BASE_DPS + (900.0 if c.item_id("head") == 10 else 500.0)
                for nome, c in candidatos.items()
            },
        )

    resultado = executar_topgear(
        personagem_base(),
        pools,
        simulador=simulador,
        request=pedido(incluir=[], excluir=[10]),
        ctx=ContextoSpec(),
    )
    assert resultado.melhor.item_id("head") == 11
