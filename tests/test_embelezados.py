"""P-052: reconhecer os embelezamentos que o personagem já usa (A1)."""

from __future__ import annotations

import pytest

from wowsim.masmorras import craft
from wowsim.masmorras.embelezados import embelezados_do_conjunto
from wowsim.topgear.models import Candidato, Conjunto

pytestmark = pytest.mark.unit


def test_embelezamento_guarda_bonus_id() -> None:
    emb = next(
        e for e in craft.embelezamentos_com_bonus() if e.token_simc == "arcanoweave_lining"
    )
    assert emb.bonus_id == 12384


def test_reconhece_bonus_aplicado_como_arcanotrama() -> None:
    # Bônus 12384 = Forro de Arcanotrama aplicado numa capa craftada.
    conjunto = Conjunto(
        itens={
            "back": Candidato(
                slot="back", item_id=239656, fonte="craft", bonus_ids=[12384]
            )
        }
    )
    atuais = embelezados_do_conjunto(conjunto)
    assert len(atuais) == 1
    atual = atuais[0]
    assert atual.slot == "back"
    assert atual.aplicado is not None
    assert atual.aplicado.nome_en == "Arcanoweave Lining"
    assert atual.aplicado.bonus_id == 12384
    assert atual.embutido is False


def test_pecas_embutidas_sao_marcadas() -> None:
    # 244613 (peito) e 244614 (mãos) já carregam o embelezamento no craft.
    conjunto = Conjunto(
        itens={
            "chest": Candidato(slot="chest", item_id=244613, fonte="craft"),
            "hands": Candidato(slot="hands", item_id=244614, fonte="craft"),
        }
    )
    atuais = {a.item_id: a for a in embelezados_do_conjunto(conjunto)}
    assert atuais[244613].embutido is True
    assert atuais[244614].embutido is True


def test_conjunto_sem_embelezamento_nao_retorna_nada() -> None:
    conjunto = Conjunto(
        itens={"shoulder": Candidato(slot="shoulder", item_id=239045, fonte="mplus")}
    )
    assert embelezados_do_conjunto(conjunto) == []
