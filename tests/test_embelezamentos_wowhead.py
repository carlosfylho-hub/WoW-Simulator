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


# Página mínima no formato do Wowhead: uma aba "usado em" e uma de materiais.
PAGINA_ABAS = """
<html><body>
<div id="tab-reagent-for"><table class="listview"><tbody>
<tr><td><a href="/pt/item=190316">Ombros do Vazio</a></td></tr>
<tr><td><a href="/pt/item=190317">Peito do Vazio</a></td></tr>
</tbody></table></div>
<div id="tab-reagents"><table class="listview"><tbody>
<tr><td><a href="/pt/item=240167">Forro Arcano</a></td><td>3</td></tr>
<tr><td><a href="/pt/item=219515">Centelha</a></td><td>2</td></tr>
</tbody></table></div>
</body></html>
"""


@pytest.mark.parametrize(
    ("aba", "esperado"),
    [
        ("tab-reagent-for", "usado_em"),
        ("tab-reagents", "materiais"),
        ("tab-created-by", "materiais"),
        ("tab-usado-em", "usado_em"),
        ("tab-comments", None),
    ],
)
def test_classificar_aba(aba: str, esperado: str | None) -> None:
    modulo = _carregar_raspador()
    assert modulo._classificar_aba(aba) == esperado


def test_extrair_pagina_separa_abas_e_le_quantidade() -> None:
    modulo = _carregar_raspador()
    extraido = modulo.extrair_pagina(PAGINA_ABAS)
    assert extraido["_fonte"] == "abas"
    assert extraido["materiais"] == ["3× Forro Arcano", "2× Centelha"]
    assert extraido["usado_em"] == ["Ombros do Vazio", "Peito do Vazio"]
    assert extraido["_detalhe"]["materiais"][0]["item_id"] == 240167
    assert extraido["_detalhe"]["materiais"][0]["quantidade"] == 3


def test_extrair_pagina_sem_abas_cai_no_texto_e_nao_mistura_titulos() -> None:
    modulo = _carregar_raspador()
    html_sem_abas = "<div><h3>Reagentes para</h3><p>Ombros do Vazio</p></div>"
    extraido = modulo.extrair_pagina(html_sem_abas)
    assert extraido["_fonte"] == "texto"
    assert extraido["materiais"] == []
    assert extraido["usado_em"] == ["Ombros do Vazio"]


def test_receitas_da_pagina_nao_repete_ids() -> None:
    modulo = _carregar_raspador()
    html = (
        '<a href="/pt/spell=441234/receita">Receita</a>'
        '<a href="/pt/spell=441234/receita">Receita</a>'
        '<a href="/pt/spell=441999/outra">Outra</a>'
    )
    assert modulo._receitas_da_pagina(html) == [441234, 441999]


def test_materiais_da_receita_le_o_tooltip_do_spell(monkeypatch) -> None:
    modulo = _carregar_raspador()
    tooltip = (
        '<div><table><tr><td><a href="/pt/item=240167">Forro Arcano</a></td>'
        "<td>4</td></tr></tbody></table></div>"
    )
    monkeypatch.setattr(modulo, "_tooltip_receita", lambda *_args: {"tooltip": tooltip})
    assert modulo._materiais_da_receita(441234) == ["4× Forro Arcano"]
