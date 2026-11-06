"""Report tests: error-aware verdict, provenance and limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.models import Personagem, Variacao
from wowsim.report import render
from wowsim.simc_runner import ResultadoDps, SimcResultado

pytestmark = pytest.mark.unit


def _personagem() -> Personagem:
    return Personagem.model_construct(
        nome="Pyrogalth",
        classe="warlock",
        spec="demonology",
        nivel=90,
        regiao="us",
        servidor="azralon",
        build_cliente="12.1.5.70783",
        checksum="70553fc1",
        texto_original="",
        bloco_equipamento_original="",
        alertas=[],
    )


def _cenario() -> tuple[SimcResultado, list[Variacao]]:
    base = ResultadoDps(nome="base", dps=200_000.0, erro_abs=2_000.0, eh_base=True)
    variacoes = [
        Variacao(
            nome="up_head",
            categoria="upgrade",
            linhas_override=["head=,id=271546,bonus_id=12854"],
            item_ids=[271546],
            fonte="bonus_ids_s2.json",
        ),
        Variacao(
            nome="up_legs",
            categoria="upgrade",
            linhas_override=["legs=,id=271545,bonus_id=12854"],
            item_ids=[271545],
            fonte="bonus_ids_s2.json",
        ),
        Variacao(
            nome="trinket1_273796",
            categoria="berloque",
            linhas_override=["trinket1=,id=273796,bonus_id=12856"],
            item_ids=[273796],
            fonte="mplus_loot_database.json",
        ),
    ]
    resultados = (
        ResultadoDps(nome="up_head", dps=201_000.0, erro_abs=300.0),
        ResultadoDps(nome="up_legs", dps=200_100.0, erro_abs=300.0),
        ResultadoDps(nome="trinket1_273796", dps=198_000.0, erro_abs=300.0),
    )
    return SimcResultado(json_path=Path("resultado.json"), base=base, variacoes=resultados), variacoes


def test_empate_usa_o_maior_erro(tmp_path: Path) -> None:
    resultado, variacoes = _cenario()
    md, html = render(
        _personagem(),
        resultado,
        variacoes,
        destino=tmp_path,
        iterations=1000,
        fight_style="DungeonSlice",
    )
    texto = md.read_text(encoding="utf-8")
    assert "**empate**" in texto
    assert "**perda**" in texto
    assert "**ganho**" not in texto
    assert "+0.50%" in texto

    pagina = html.read_text(encoding="utf-8")
    assert "<html" in pagina
    assert "empate" in pagina


def test_relatorio_tem_origem_e_limites(tmp_path: Path) -> None:
    resultado, variacoes = _cenario()
    md, _ = render(
        _personagem(),
        resultado,
        variacoes,
        destino=tmp_path,
        iterations=1000,
        fight_style="DungeonSlice",
    )
    texto = md.read_text(encoding="utf-8")
    assert "Onde dropa" in texto
    assert "Códice Corrosivo" in texto
    assert "Todos os números vêm do SimulationCraft" in texto
    assert "bonus_ids_s2.json" in texto
    assert "mplus_loot_database.json" in texto
    assert "Crânio do Necrólito Maldito" in texto


def test_sem_base_falha(tmp_path: Path) -> None:
    resultado = SimcResultado(json_path=Path("x.json"), base=None, variacoes=())
    with pytest.raises(ValueError):
        render(
            _personagem(),
            resultado,
            [],
            destino=tmp_path,
            iterations=100,
            fight_style="DungeonSlice",
        )
