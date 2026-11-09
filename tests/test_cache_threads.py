"""A-06: o número de threads não entra na chave de cache do simc."""

from __future__ import annotations

import pytest

from wowsim import simc_runner as sr

pytestmark = pytest.mark.unit


def _parametros(threads: int) -> dict:
    return sr._parametros_canonicos(
        iterations=200,
        fight_style="Patchwerk",
        threads=threads,
        target_error=None,
        desired_targets=None,
        extra_args=(),
        max_time=None,
    )


def test_threads_nao_muda_a_chave(tmp_path) -> None:
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    simc = tmp_path / "simc.exe"
    simc.write_bytes(b"binario")

    a = sr.chave_cache(perfil, _parametros(1), simc)
    b = sr.chave_cache(perfil, _parametros(8), simc)
    assert a == b


def test_parametros_nao_carregam_threads() -> None:
    assert "threads" not in _parametros(4)
