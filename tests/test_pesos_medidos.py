"""Measured weights: normalisation, cache roundtrip and fallback."""

from __future__ import annotations

import pytest

from wowsim.data import pesos_medidos
from wowsim.models import ItemEquipado, Personagem


def _personagem() -> Personagem:
    return Personagem(
        texto_original="",
        classe="Bruxo",
        spec="Demonology",
        talents_atual="ATUAL",
        equipado={
            "head": ItemEquipado(slot="head", item_id=1, linha_original="head=,id=1"),
        },
    )


def test_normaliza_scale_factors_para_relativo() -> None:
    bruto = {
        "sim": {
            "players": [
                {
                    "collected_data": {
                        "scale_factors": {
                            "Haste": 2.0,
                            "Crit": 1.0,
                            "Mastery": 1.5,
                            "Versatility": 0.5,
                            "Stamina": 0.01,
                        }
                    }
                }
            ]
        }
    }
    pesos = pesos_medidos.normalizar_scale_factors(bruto)
    assert pesos["haste"] == pytest.approx(1.0)
    assert pesos["mastery"] == pytest.approx(0.75)
    assert pesos["crit"] == pytest.approx(0.5)
    assert "stamina" not in pesos


def test_normaliza_vazio_quando_ausente() -> None:
    assert pesos_medidos.normalizar_scale_factors({}) == {}
    assert pesos_medidos.normalizar_scale_factors({"sim": {"players": []}}) == {}


def test_cache_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pesos_medidos, "DIR", tmp_path / "pesos")
    personagem = _personagem()
    assert pesos_medidos.carregar_pesos_medidos(personagem) is None

    salvo = pesos_medidos.salvar_pesos_medidos(
        personagem, {"haste": 1.0, "crit": 0.8}, fonte="teste:pesos"
    )
    assert salvo.conhecido is True

    lido = pesos_medidos.carregar_pesos_medidos(personagem)
    assert lido is not None
    assert lido.fonte == "teste:pesos"
    assert lido.valores["haste"] == 1.0


def test_chave_muda_com_equipamento() -> None:
    a = _personagem()
    b = a.model_copy(
        update={
            "equipado": {
                "head": ItemEquipado(slot="head", item_id=999, linha_original="head=,id=999")
            }
        }
    )
    assert pesos_medidos.chave_pesos(a) != pesos_medidos.chave_pesos(b)
