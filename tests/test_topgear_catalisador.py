"""Testes do Catalisador: gêmeos catalisados, pacotes de tier e teto de cargas.

Tudo offline: nenhum teste aqui chama o binário do simc. O que se verifica é a
geração de candidatos e a linha `.simc` resultante, não dano.
"""

from __future__ import annotations

import pytest

from wowsim.data import tier
from wowsim.models import ItemEquipado, Personagem
from wowsim.topgear.catalisador import (
    adicionar_gemeos,
    contexto_com_catalisador,
    gemeo_catalisado,
    pacotes_de_tier,
    pecas_de_tier,
)
from wowsim.topgear.constraints import avisos, validar
from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec, TopGearRequest
from wowsim.topgear.runner import linhas_override
from wowsim.topgear.search import conjunto_do_personagem, otimizar_catalisador
from wowsim.topgear.runner import LeituraSim

pytestmark = pytest.mark.unit

CLASSE = "warlock"
# Conjunto 2066 do warlock, derivado do item_data.inc do SimC.
TIER_HEAD = 271546
TIER_SHOULDER = 271544
TIER_CHEST = 271549
TIER_HANDS = 271547
TIER_LEGS = 271545


def cand(slot: str, item_id: int | None = 500, **kwargs) -> Candidato:
    dados = {
        "slot": slot,
        "item_id": item_id,
        "bonus_ids": [12854],
        "ilvl": 334,
        "fonte": "mplus",
    }
    dados.update(kwargs)
    return Candidato(**dados)


def test_dados_de_tier_existem_para_as_treze_classes() -> None:
    todos = tier.todos()
    assert len(todos) == 13
    conjunto = tier.conjunto_da_classe("Warlock")
    assert conjunto is not None
    assert conjunto.set_id == 2066
    assert conjunto.item_do_slot("head") == TIER_HEAD
    assert conjunto.item_do_slot("legs") == TIER_LEGS


def test_normaliza_nome_da_classe() -> None:
    assert tier.normalizar_classe("Death Knight") == "death_knight"
    assert tier.normalizar_classe("death-knight") == "death_knight"
    assert tier.conjunto_da_classe("Death Knight") is not None
    assert tier.conjunto_da_classe("classe inexistente") is None


def test_gemeo_preserva_trilha_e_aponta_para_a_origem() -> None:
    origem = cand("head", 250001)
    gemeo = gemeo_catalisado(origem, CLASSE)

    assert gemeo is not None
    assert gemeo.item_id == TIER_HEAD
    assert gemeo.redirected_base_stats == 250001
    assert gemeo.catalisado is True
    # Trilha e nível vêm do item de origem: o Catalisador nunca sobe de track.
    assert gemeo.bonus_ids == [12854]
    assert gemeo.ilvl == 334
    assert gemeo.fonte.startswith("catalisador:")


def test_gemeo_usa_os_stats_do_item_de_origem() -> None:
    origem = cand("chest", 250002, stats={"intellect": 1234})
    gemeo = gemeo_catalisado(origem, CLASSE)

    assert gemeo is not None
    # A poda heurística precisa pontuar pelos stats preservados, não pelos do tier.
    assert gemeo.stats == {"intellect": 1234}


@pytest.mark.parametrize("slot", ["wrist", "neck", "trinket1", "main_hand", "back"])
def test_gemeo_recusa_slot_sem_tier(slot: str) -> None:
    assert gemeo_catalisado(cand(slot, 250003), CLASSE) is None


def test_gemeo_recusa_peca_que_ja_e_de_tier() -> None:
    assert gemeo_catalisado(cand("head", TIER_HEAD), CLASSE) is None


def test_gemeo_recusa_peca_ja_catalisada() -> None:
    ja = cand("head", TIER_HEAD, redirected_base_stats=250004)
    assert gemeo_catalisado(ja, CLASSE) is None


def test_gemeo_recusa_item_craftado_e_sem_id() -> None:
    assert gemeo_catalisado(cand("legs", 250005, craftado=True), CLASSE) is None
    assert gemeo_catalisado(cand("legs", None), CLASSE) is None


def test_gemeo_recusa_classe_sem_dados() -> None:
    assert gemeo_catalisado(cand("head", 250006), "classe inexistente") is None
    assert gemeo_catalisado(cand("head", 250006), None) is None


def test_adicionar_gemeos_so_mexe_em_slot_de_tier() -> None:
    pools = {
        "head": [cand("head", 250010), cand("head", 250011)],
        "wrist": [cand("wrist", 250012)],
    }
    saida = adicionar_gemeos(pools, CLASSE)

    assert len(saida["head"]) == 4  # dois originais + dois gêmeos
    assert len(saida["wrist"]) == 1
    catalisados = [c for c in saida["head"] if c.catalisado]
    assert {c.redirected_base_stats for c in catalisados} == {250010, 250011}


def test_adicionar_gemeos_nao_duplica_em_chamada_repetida() -> None:
    pools = {"head": [cand("head", 250013)]}
    uma = adicionar_gemeos(pools, CLASSE)
    duas = adicionar_gemeos(uma, CLASSE)
    assert len(duas["head"]) == len(uma["head"]) == 2


def test_linha_simc_leva_redirected_base_stats() -> None:
    gemeo = gemeo_catalisado(cand("head", 250014), CLASSE)
    assert gemeo is not None
    linhas = linhas_override(Conjunto(itens={"head": gemeo}))

    assert linhas == [
        "head=,id=271546,bonus_id=12854,redirected_base_stats=250014"
    ]


def test_conjunto_do_personagem_preserva_peca_ja_catalisada() -> None:
    """Regressão: sem isto a peça catalisada perdia os stats base ao ser reescrita."""
    personagem = Personagem(
        texto_original="",
        equipado={
            "chest": ItemEquipado(
                slot="chest",
                item_id=TIER_CHEST,
                bonus_ids=[12846],
                redirected_base_stats=272231,
                linha_original="chest=,id=271549",
            )
        },
    )
    conjunto = conjunto_do_personagem(personagem)

    assert conjunto.itens["chest"].redirected_base_stats == 272231
    assert conjunto.itens["chest"].catalisado is True
    assert "redirected_base_stats=272231" in linhas_override(conjunto)[0]


def test_pacotes_fecham_duas_e_quatro_pecas() -> None:
    melhor = Conjunto(
        itens={
            slot: cand(slot, 250100 + i)
            for i, slot in enumerate(("head", "shoulder", "chest", "hands", "legs"))
        }
    )
    pacotes = pacotes_de_tier(melhor, CLASSE)

    de_dois = {n: c for n, c in pacotes.items() if n.startswith("cat2pc_")}
    de_quatro = {n: c for n, c in pacotes.items() if n.startswith("cat4pc_")}
    # 5 slots elegíveis: C(5,2)=10 pacotes de 2 peças e C(5,4)=5 de 4 peças.
    assert len(de_dois) == 10
    assert len(de_quatro) == 5

    algum = next(iter(de_quatro.values()))
    assert len(pecas_de_tier(algum, CLASSE)) == 4


def test_pacotes_consideram_as_pecas_de_tier_que_ja_existem() -> None:
    melhor = Conjunto(
        itens={
            "head": cand("head", TIER_HEAD),      # já é tier
            "shoulder": cand("shoulder", TIER_SHOULDER),  # já é tier
            "chest": cand("chest", 250200),
            "hands": cand("hands", 250201),
            "legs": cand("legs", 250202),
        }
    )
    pacotes = pacotes_de_tier(melhor, CLASSE)

    # Com 2 peças prontas, o alvo de 2 já está cumprido: só restam os de 4.
    assert not any(n.startswith("cat2pc_") for n in pacotes)
    assert all(len(pecas_de_tier(c, CLASSE)) == 4 for c in pacotes.values())


def test_pacotes_respeitam_slots_travados() -> None:
    melhor = Conjunto(
        itens={
            slot: cand(slot, 250300 + i)
            for i, slot in enumerate(("head", "shoulder", "chest", "hands", "legs"))
        }
    )
    pacotes = pacotes_de_tier(melhor, CLASSE, travados={"head", "legs"})

    assert pacotes
    for nome in pacotes:
        assert "head" not in nome and "legs" not in nome


def test_pacotes_vazios_para_classe_sem_dados() -> None:
    melhor = Conjunto(itens={"head": cand("head", 250400)})
    assert pacotes_de_tier(melhor, "classe inexistente") == {}


def test_teto_de_cargas_barra_o_conjunto() -> None:
    ctx = ContextoSpec(max_catalisados=1)
    head = gemeo_catalisado(cand("head", 250500), CLASSE)
    legs = gemeo_catalisado(cand("legs", 250501), CLASSE)
    assert head is not None and legs is not None

    assert validar(Conjunto(itens={"head": head}), ctx) == (True, [])

    ok, motivos = validar(Conjunto(itens={"head": head, "legs": legs}), ctx)
    assert ok is False
    assert any("Catalisador" in motivo for motivo in motivos)


def test_peca_ja_equipada_catalisada_nao_gasta_carga() -> None:
    head = gemeo_catalisado(cand("head", 250600), CLASSE)
    assert head is not None
    ctx = ContextoSpec(
        max_catalisados=0,
        catalisados_equipados={(TIER_HEAD, 250600)},
    )
    assert validar(Conjunto(itens={"head": head}), ctx) == (True, [])


def test_sem_teto_nao_limita() -> None:
    ctx = ContextoSpec(max_catalisados=None)
    itens = {}
    for i, slot in enumerate(("head", "shoulder", "chest", "hands", "legs")):
        gemeo = gemeo_catalisado(cand(slot, 250700 + i), CLASSE)
        assert gemeo is not None
        itens[slot] = gemeo
    assert validar(Conjunto(itens=itens), ctx) == (True, [])


def test_contexto_le_as_pecas_catalisadas_do_personagem() -> None:
    personagem = Personagem(
        texto_original="",
        equipado={
            "legs": ItemEquipado(
                slot="legs",
                item_id=TIER_LEGS,
                redirected_base_stats=273786,
                linha_original="legs=,id=271545",
            )
        },
    )
    ctx = contexto_com_catalisador(ContextoSpec(), personagem, CLASSE, 2)

    assert ctx.max_catalisados == 2
    assert (TIER_LEGS, 273786) in ctx.catalisados_equipados
    assert TIER_HEAD in ctx.tier_ids


def test_aviso_relata_as_conversoes_usadas() -> None:
    head = gemeo_catalisado(cand("head", 250800), CLASSE)
    assert head is not None
    ctx = ContextoSpec(tier_ids=tier.ids_tier(CLASSE))
    mensagens = avisos(Conjunto(itens={"head": head}), ctx)

    assert any("Catalisador" in m and "head" in m for m in mensagens)


def test_etapa_escolhe_o_pacote_de_maior_dps() -> None:
    melhor = Conjunto(
        itens={
            slot: cand(slot, 250900 + i)
            for i, slot in enumerate(("head", "shoulder", "chest", "hands", "legs"))
        }
    )
    base_dps = 100_000.0

    def simulador(candidatos, iterations):
        # 4 peças de tier valem mais que 2: o ganho vem do bônus de conjunto.
        resultados = {}
        for nome, conjunto in candidatos.items():
            pecas = len(pecas_de_tier(conjunto, CLASSE))
            resultados[nome] = base_dps * (1 + 0.01 * pecas)
        return LeituraSim(base_dps=base_dps, resultados=resultados)

    novo, novo_dps, rodadas = otimizar_catalisador(
        melhor,
        base_dps,
        ContextoSpec(),
        simulador=simulador,
        iterations=100,
        classe=CLASSE,
        limiar_pct=0.15,
        numero=1,
    )

    assert len(pecas_de_tier(novo, CLASSE)) == 4
    assert novo_dps > base_dps
    assert rodadas and rodadas[0].estagio == "catalisador"


def test_etapa_rejeita_ganho_abaixo_do_limiar() -> None:
    melhor = Conjunto(itens={"head": cand("head", 251000)})
    base_dps = 100_000.0

    def simulador(candidatos, iterations):
        return LeituraSim(
            base_dps=base_dps,
            resultados={nome: base_dps * 1.0001 for nome in candidatos},
        )

    novo, novo_dps, _rodadas = otimizar_catalisador(
        melhor,
        base_dps,
        ContextoSpec(),
        simulador=simulador,
        iterations=100,
        classe=CLASSE,
        limiar_pct=0.15,
        numero=1,
    )

    assert novo == melhor
    assert novo_dps == base_dps


def test_pedido_desligado_por_padrao() -> None:
    pedido = TopGearRequest(addon="")
    assert pedido.catalisador is False
    assert pedido.max_catalisados is None
