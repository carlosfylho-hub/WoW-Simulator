"""Estimativa de tempo por estilo de luta e calibração com rodadas reais."""

from __future__ import annotations

import pytest

from wowsim import calibracao, simc_runner
from wowsim.gen.profilesets import estimar_segundos

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(simc_runner, "CACHE_DIR", tmp_path)


def test_dungeon_slice_e_mais_lento_que_patchwerk() -> None:
    assert estimar_segundos(88, 300, "DungeonSlice") > 2.5 * estimar_segundos(88, 300, "Patchwerk")


def test_padrao_bate_com_o_log_real_do_usuario() -> None:
    # 2026-11-08: 88 profilesets × 300 it em DungeonSlice levaram 106,8 s (89 perfis).
    assert estimar_segundos(88, 300, "DungeonSlice") == pytest.approx(106.8, rel=0.15)


def test_registrar_ajusta_a_taxa() -> None:
    calibracao.registrar("Patchwerk", 100, 1000, 300.0)  # 0,003 s
    assert calibracao.taxa("Patchwerk") == pytest.approx(0.003)
    calibracao.registrar("Patchwerk", 100, 1000, 100.0)  # 0,001 -> média 0,002
    assert calibracao.taxa("Patchwerk") == pytest.approx(0.002)


def test_rodada_pequena_nao_calibra() -> None:
    calibracao.registrar("Patchwerk", 3, 5, 9.0)
    assert calibracao.taxa("Patchwerk") == calibracao.PADRAO["Patchwerk"]


def test_sem_estilo_continua_como_antes() -> None:
    assert estimar_segundos(10, 1000) == pytest.approx(10 * 1000 * calibracao.TAXA_GENERICA)
