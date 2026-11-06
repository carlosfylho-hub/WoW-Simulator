"""Integration test: generate a batch and run the real simc binary."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim import simc_runner as sr
from wowsim.gen import profilesets
from wowsim.parser.addon import parse_arquivo

pytestmark = pytest.mark.integration_simc

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


def test_todas_as_variacoes_aparecem_no_resultado(tmp_path: Path) -> None:
    personagem = parse_arquivo(FIXTURE)
    variacoes = profilesets.gerar(
        personagem,
        categorias={"upgrade", "talento", "folio"},
        de_bonus=12846,
        para_bonus=12854,
        max_variacoes=8,
    )
    assert len(variacoes) > 1

    destino = profilesets.escrever_arquivo(
        personagem, variacoes, tmp_path / "lote.simc"
    )
    execucao = sr.run_simc(
        destino,
        iterations=200,
        fight_style="DungeonSlice",
        threads=sr.threads_padrao(),
        usar_cache=False,
    )
    resultado = sr.read_results(execucao.json_path)

    assert resultado.base is not None
    nomes_esperados = {variacao.nome for variacao in variacoes[1:]}
    nomes_recebidos = {variacao.nome for variacao in resultado.variacoes}
    assert nomes_recebidos == nomes_esperados
    assert all(variacao.dps > 0 for variacao in resultado.variacoes)
