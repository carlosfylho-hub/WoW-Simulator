"""A8/P-055: merge e helpers do raspador de embelezamentos do Wowhead."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from wowsim.data.embellishments import mesclar_wowhead

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]


def _carregar_raspador():
    caminho = RAIZ / "scripts" / "raspar_embelezamentos.py"
    spec = importlib.util.spec_from_file_location("raspar_embelezamentos", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_mesclar_wowhead_preenche_campos_visuais() -> None:
    saida = [{"reagente_id": 240167, "nome_en": "Arcanoweave Lining"}]
    wowhead = {
        "embelezamentos": [
            {
                "reagente_id": 240167,
                "icone": "inv_abc",
                "icone_url": "https://wow.zamimg.com/images/wow/icons/large/inv_abc.jpg",
                "texto_completo": "Seus feitiços atraem uma moreia.",
                "qualidade": 4,
                "materiais": ["Tecido", "Centelha"],
                "usado_em": ["Ombros", "Peito"],
            }
        ]
    }
    out = mesclar_wowhead(saida, wowhead)
    assert out[0]["icone_url"].endswith("inv_abc.jpg")
    assert out[0]["texto_completo"].startswith("Seus feitiços")
    assert out[0]["qualidade"] == 4
    assert out[0]["materiais"] == ["Tecido", "Centelha"]
    assert out[0]["usado_em"] == ["Ombros", "Peito"]


def test_mesclar_wowhead_nao_sobrescreve_com_vazio() -> None:
    saida = [{"reagente_id": 1, "texto_completo": "já tinha"}]
    mesclar_wowhead(saida, {"embelezamentos": [{"reagente_id": 1, "texto_completo": "", "materiais": []}]})
    assert saida[0]["texto_completo"] == "já tinha"
    assert "materiais" not in saida[0]


def test_texto_do_html_limpa_tags_e_preserva_quebras() -> None:
    modulo = _carregar_raspador()
    assert modulo.texto_do_html("<b>Dano</b><br>5 por 2 s") == "Dano\n5 por 2 s"


def test_entrada_monta_url_do_icone() -> None:
    modulo = _carregar_raspador()
    entrada = modulo._entrada(
        240167,
        {"name": "Forro", "icon": "inv_abc", "quality": 4, "tooltip": "<b>Efeito</b>"},
        {"name": "Lining", "icon": "inv_abc"},
    )
    assert entrada["icone_url"] == (
        "https://wow.zamimg.com/images/wow/icons/large/inv_abc.jpg"
    )
    assert entrada["texto_completo"] == "Efeito"
