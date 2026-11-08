"""A-01: o timeout de execucao nunca pode virar a duracao da luta (max_time)."""
from __future__ import annotations

from pathlib import Path

import pytest

from wowsim import simc_runner as sr

pytestmark = pytest.mark.unit


class _Parar(Exception):
    """Interrompe run_simc logo depois de montar o comando (sem rodar o simc)."""


def _preparar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, dict, list]:
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(sr, "find_simc", lambda explicit=None: tmp_path / "simc.exe")
    monkeypatch.setattr(sr, "ler_versao", lambda simc, timeout=30.0: sr.SimcInfo(caminho=Path(simc)))
    capturado: dict = {}
    chaves: list = []
    original = sr.chave_cache

    def chave_espiada(*args, **kwargs):
        chaves.append(original(*args, **kwargs))
        return chaves[-1]

    def comando_falso(*args, **kwargs):
        capturado.update(kwargs)
        raise _Parar

    monkeypatch.setattr(sr, "chave_cache", chave_espiada)
    monkeypatch.setattr(sr, "montar_comando", comando_falso)
    return perfil, capturado, chaves


def test_timeout_nao_vira_duracao_da_luta(tmp_path, monkeypatch) -> None:
    perfil, capturado, _ = _preparar(monkeypatch, tmp_path)
    with pytest.raises(_Parar):
        sr.run_simc(perfil, timeout=600, usar_cache=False)
    assert capturado["max_time"] is None


def test_max_time_explicito_continua_valendo(tmp_path, monkeypatch) -> None:
    perfil, capturado, _ = _preparar(monkeypatch, tmp_path)
    with pytest.raises(_Parar):
        sr.run_simc(perfil, timeout=600, max_time=300, usar_cache=False)
    assert capturado["max_time"] == 300


def test_chave_de_cache_nao_depende_do_orcamento(tmp_path, monkeypatch) -> None:
    perfil, _, chaves = _preparar(monkeypatch, tmp_path)
    for timeout in (600, 37):
        with pytest.raises(_Parar):
            sr.run_simc(perfil, timeout=timeout, usar_cache=False)
    assert chaves[0] == chaves[1]
