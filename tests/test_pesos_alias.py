"""A-12: o simc publica versatilidade como 'Vers'; a normalização precisa vê-la."""

import pytest

from wowsim.data.pesos_medidos import normalizar_scale_factors

pytestmark = pytest.mark.unit


def test_vers_do_simc_vira_versatility() -> None:
    bruto = {
        "sim": {
            "players": [
                {
                    "scale_factors": {
                        "Int": 64.4,
                        "SP": 60.0,
                        "Crit": 47.3,
                        "Haste": 31.7,
                        "Mastery": 42.8,
                        "Vers": 36.7,
                    }
                }
            ]
        }
    }
    pesos = normalizar_scale_factors(bruto)
    assert set(pesos) == {"crit", "haste", "mastery", "versatility"}
    assert pesos["crit"] == 1.0
    assert pesos["versatility"] == pytest.approx(36.7 / 47.3)
