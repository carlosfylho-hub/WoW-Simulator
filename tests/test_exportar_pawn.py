"""T11 (núcleo): string do Pawn validada pelo regex do próprio Pawn."""

from __future__ import annotations

import pytest

from wowsim.exportar.pawn import (
    misturar,
    pesos_relativos,
    string_pawn,
    validar_como_pawn,
)

pytestmark = pytest.mark.unit

PESOS = {
    "Intellect": 10.0,
    "CritRating": 8.0,
    "HasteRating": 6.0,
    "MasteryRating": 9.0,
    "Versatility": 5.0,
}


def test_string_valida_no_regex_do_pawn() -> None:
    tag = string_pawn("Demo M+", PESOS, classe="WARLOCK", spec="Demonology")
    nome, valores = validar_como_pawn(tag)
    assert nome == "Demo M+"
    assert valores["Class"] == "WARLOCK"
    assert valores["Spec"] == "Demonology"
    assert float(valores["Intellect"]) == pytest.approx(10.0)
    assert float(valores["CritRating"]) == pytest.approx(8.0)


def test_mistura_sem_spec() -> None:
    tag = string_pawn("Mistura", {"CritRating": 5.0, "HasteRating": 2.5})
    nome, valores = validar_como_pawn(tag)
    assert nome == "Mistura"
    assert "Class" not in valores
    assert "Spec" not in valores


def test_nome_com_aspas_ou_parenteses_recusado() -> None:
    with pytest.raises(ValueError):
        string_pawn('a"b', PESOS)
    with pytest.raises(ValueError):
        string_pawn("a(b)", PESOS)


def test_pesos_relativos() -> None:
    pesos = pesos_relativos({"Int": 10.0, "Crit": 5.0, "Stamina": 1.0}, 1000.0)
    assert pesos == pytest.approx({"Intellect": 1.0, "CritRating": 0.5})


def test_misturar_media_ponderada() -> None:
    mistura = misturar(
        [
            ({"CritRating": 1.0, "HasteRating": 0.5}, 0.5),
            ({"CritRating": 0.0, "HasteRating": 1.0}, 0.5),
        ]
    )
    assert mistura["CritRating"] == pytest.approx(0.5)
    assert mistura["HasteRating"] == pytest.approx(0.75)
