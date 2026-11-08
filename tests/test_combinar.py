"""Merge de exports SimC + AskMrRobot (complementares, sem inventar DPS)."""

from __future__ import annotations

import pytest

from wowsim.droptimizer import itens_do_inv
from wowsim.parser.amr import para_personagem, parse_amr
from wowsim.parser.combinar import combinar_textos
from wowsim.paths import PROJECT_ROOT

pytestmark = pytest.mark.unit

FIXTURES = PROJECT_ROOT / "fixtures"
SIMC = (FIXTURES / "pyrogalth.simc").read_text(encoding="utf-8")
AMR = (FIXTURES / "pyrogalth-amr-181.txt").read_text(encoding="utf-8")


def _itens_inv_com_slot() -> set[int]:
    """Ids do .inv AMR que resolvem para um slot real (mesma via do merge)."""
    return {item.item_id for item in itens_do_inv(parse_amr(AMR))}


def test_combina_simc_amr_talentos_e_inv() -> None:
    combo = combinar_textos(SIMC, AMR, primario="simc")
    assert combo.primario == "simc"
    assert "simc" in combo.fontes and "amr" in combo.fontes

    # Talentos/omnium só vêm do SimC.
    assert combo.personagem.talents_atual
    # Raça só vem do AMR (via map do addon).
    assert combo.personagem.raca == "dracthyr"
    assert combo.personagem.classe == "warlock"

    # .inv AMR foi mesclado às bolsas como itens possuídos.
    itens_mochila = {
        item.item_id
        for itens in combo.personagem.mochila.values()
        for item in itens
        if item.item_id is not None
    }
    esperados = _itens_inv_com_slot()
    assert esperados
    assert esperados & itens_mochila


def test_primario_amr_usa_equipado_amr_mas_talentos_do_simc() -> None:
    amr_personagem = para_personagem(
        parse_amr(AMR), classe_hint="warlock", spec_hint="demonology"
    )
    combo = combinar_textos(SIMC, AMR, primario="amr")

    # Equipado vem do AMR (primário).
    for slot, item in amr_personagem.equipado.items():
        if slot in combo.personagem.equipado:
            assert combo.personagem.equipado[slot].item_id == item.item_id
    # Mesmo com AMR primário, talentos continuam do SimC.
    assert combo.personagem.talents_atual


def test_somente_amr_sem_simc() -> None:
    combo = combinar_textos(None, AMR, classe_hint="warlock", spec_hint="demonology")
    assert combo.fontes == ["amr"]
    assert combo.personagem.classe == "warlock"
    assert combo.personagem.raca == "dracthyr"
    assert combo.personagem.talents_atual is None
    assert any(combo.personagem.mochila.values())


def test_conflito_de_equipado_e_avisado() -> None:
    combo = combinar_textos(SIMC, AMR, primario="simc")
    codigos = {aviso.codigo for aviso in combo.avisos}
    assert "combinar_equipado_conflito" in codigos
    assert "combinar_fontes" in codigos


def test_sem_texto_levanta() -> None:
    with pytest.raises(ValueError):
        combinar_textos(None, None)


def test_fontes_sem_duplicata() -> None:
    """P1-01: cada fonte aparece uma única vez."""
    combo = combinar_textos(SIMC, AMR)
    assert len(combo.fontes) == len(set(combo.fontes))


def test_dois_amr_distintos_levantam() -> None:
    """P1-01: principal AMR + AMR diferente em 'amr' é ambíguo."""
    with pytest.raises(ValueError):
        combinar_textos(AMR, AMR + "\n# segundo export diferente")


def test_simc_combinado_regenerado() -> None:
    """P1-05: o .simc de saída reflete o modelo mesclado (tem talentos)."""
    combo = combinar_textos(SIMC, AMR)
    assert combo.simc
    assert "talents" in combo.simc
    assert "combinar_simc_limitacoes" in {aviso.codigo for aviso in combo.avisos}
