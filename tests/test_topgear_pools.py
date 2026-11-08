"""Pool builder tests against the real Season 2 snapshot."""

from __future__ import annotations

import pytest

from wowsim.data import catalog, consumables, embellishments
from wowsim.parser.addon import parse_texto
from wowsim.paths import PROJECT_ROOT
from wowsim.topgear.pools import (
    NIVEL_PARA_BONUS,
    combinacoes_folio,
    construir_contexto,
    construir_pools,
    diamantes,
    encantos_por_slot,
    gemas_catalogo,
    resumo,
    secoes_ausentes,
    talentos_disponiveis,
)

pytestmark = pytest.mark.schema

FIXTURE = PROJECT_ROOT / "fixtures" / "pyrogalth.simc"


def test_pools_cobrem_slots_de_armadura_e_acessorios() -> None:
    pools = construir_pools()
    for slot in ("head", "shoulder", "chest", "wrist", "hands", "waist", "legs", "feet"):
        assert pools.get(slot), f"pool vazia para {slot}"
    for slot in ("neck", "finger1", "finger2", "trinket1", "trinket2", "main_hand"):
        assert pools.get(slot), f"pool vazia para {slot}"


def test_pools_sem_duplicados_e_com_bonus_coerente() -> None:
    pools = construir_pools()
    for slot, candidatos in pools.items():
        chaves = [(c.item_id, c.ilvl, c.bonus_id) for c in candidatos]
        assert len(chaves) == len(set(chaves)), f"duplicados em {slot}"
        for candidato in candidatos:
            assert candidato.ilvl in NIVEL_PARA_BONUS
            assert candidato.bonus_id == NIVEL_PARA_BONUS[candidato.ilvl]
            assert candidato.fonte


def test_pool_por_slot_limita_sem_quebrar_ordem() -> None:
    completo = construir_pools()
    limitado = construir_pools(pool_por_slot=2)
    for slot, candidatos in limitado.items():
        assert len(candidatos) <= 2
        assert candidatos == completo[slot][:2]


def test_resumo_conta_por_slot() -> None:
    pools = construir_pools()
    contagem = resumo(pools)
    assert set(contagem) == set(pools)
    assert all(valor > 0 for valor in contagem.values())


def test_encantos_por_slot_tem_camadas() -> None:
    encantos = encantos_por_slot()
    assert encantos.get("head")
    camadas = {candidato.tipo for lista in encantos.values() for candidato in lista}
    assert "encantamento" in camadas
    assert any(candidato.enchant_id for lista in encantos.values() for candidato in lista)


def test_gemas_e_diamantes() -> None:
    gemas = gemas_catalogo()
    assert len(gemas) == 72
    assert all(gema.slot == "gema" for gema in gemas)

    prisma = diamantes()
    assert prisma
    tipos = {gema.item_id: gema.tipo for gema in gemas}
    for item_id in prisma:
        assert "diamante" in (tipos[item_id] or "").lower()


def test_combinacoes_de_folio() -> None:
    combinacoes = combinacoes_folio()
    assert len(combinacoes) == 72
    for combo in combinacoes:
        assert len(combo) == 5
        linhas = [runa[0] for runa in combo]
        assert sorted(linhas) == ["1", "2", "3", "4", "5"]


def test_contexto_indexa_catalogo() -> None:
    ctx = construir_contexto(classe="warlock", spec="demonology")
    assert ctx.diamantes
    assert ctx.embelezamentos
    assert ctx.trinkets_on_use
    assert ctx.offs_validos
    assert ctx.craft_ilvl_teto == 331


def test_talentos_do_fixture() -> None:
    personagem = parse_texto(FIXTURE.read_text(encoding="utf-8"))
    talentos = talentos_disponiveis(personagem)
    assert talentos
    assert all(candidato.slot == "talentos" for candidato in talentos)
    assert all(candidato.valor for candidato in talentos)
    assert len({candidato.valor for candidato in talentos}) == len(talentos)


def test_atributo_primario_do_catalogo() -> None:
    assert catalog.atributo_primario(251156) == "Intelecto"
    assert catalog.atributo_primario(999_999_999) is None


def test_embelezamento_vem_do_catalogo_de_craft_nao_de_peconha() -> None:
    """P0-01: a venom-forged drop is not an embellishment."""
    com_peconha = [
        loot
        for nivel in catalog.ILVLS_ALVO
        for loot in catalog.itens_monitor(nivel)
        if loot.peconha
    ]
    assert com_peconha, "o snapshot deveria ter itens com peçonha"

    ctx = construir_contexto()
    for loot in com_peconha:
        if not embellishments.info(loot.item_id).embutido:
            assert loot.item_id not in ctx.embelezamentos

    for candidatos in construir_pools().values():
        for candidato in candidatos:
            if candidato.item_id is not None:
                assert candidato.embelezamento == embellishments.info(
                    candidato.item_id
                ).embutido


def test_secoes_de_armadura_cobrem_tecido_couro_malha_placa() -> None:
    # Tecido/couro vêm do snapshot M+; malha/placa vêm da raspagem Wowhead.
    assert secoes_ausentes("tecido") == []
    assert secoes_ausentes("couro") == []
    assert secoes_ausentes("malha") == []
    assert secoes_ausentes("placa") == []
    # Um tipo sem mapeamento continua avisando.
    assert secoes_ausentes("inexistente")


@pytest.mark.parametrize(
    ("armadura", "atributo"),
    [
        ("malha", "Agilidade"),
        ("malha", "Intelecto"),
        ("placa", "Força"),
        ("placa", "Intelecto"),
    ],
)
def test_pools_de_malha_e_placa_tem_todos_os_slots(
    armadura: str, atributo: str
) -> None:
    pools = construir_pools(tipo_armadura=armadura, atributo=atributo)
    for slot in (
        "head",
        "shoulder",
        "chest",
        "wrist",
        "hands",
        "waist",
        "legs",
        "feet",
    ):
        assert pools.get(slot), f"pool vazia {armadura}/{atributo}/{slot}"


def test_consumiveis_vem_de_json_com_proveniencia() -> None:
    assert "consumiveis_s2.json" in consumables.FONTE
    assert consumables.categorias() == ("flask", "potion", "food", "augmentation")
    assert consumables.nome("flask", "flask_of_the_shattered_sun_2")
