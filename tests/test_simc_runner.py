"""Unit tests for the simc runner. No binary and no real fixture required."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from wowsim import simc_runner as sr

pytestmark = pytest.mark.unit


def _binario_falso(tmp_path: Path, corpo_windows: str, corpo_posix: str) -> Path:
    if os.name == "nt":
        caminho = tmp_path / "simc_fake.bat"
        caminho.write_text("@echo off\r\n" + corpo_windows + "\r\n", encoding="utf-8")
    else:
        caminho = tmp_path / "simc_fake.sh"
        caminho.write_text("#!/bin/sh\n" + corpo_posix + "\n", encoding="utf-8")
        caminho.chmod(caminho.stat().st_mode | stat.S_IXUSR)
    return caminho


def test_find_simc_explicito(tmp_path: Path) -> None:
    falso = _binario_falso(tmp_path, "exit /b 0", "exit 0")
    assert sr.find_simc(falso) == falso


def test_find_simc_por_variavel_de_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    falso = _binario_falso(tmp_path, "exit /b 0", "exit 0")
    monkeypatch.setenv("WOWSIM_SIMC", str(falso))
    assert sr.find_simc() == falso


def test_find_simc_sem_binario_mostra_instrucoes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sr, "BIN_DIR", tmp_path / "bin")
    monkeypatch.delenv("WOWSIM_SIMC", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(sr.SimcNaoEncontrado) as exc:
        sr.find_simc()
    texto = str(exc.value)
    assert "build_simc" in texto
    assert "simulationcraft" in texto.lower()
    assert sr.BUILD_ESPERADO in texto


def test_parse_versao() -> None:
    versao, build = sr._parse_versao(
        "SimulationCraft 1201-01 for World of Warcraft 12.1.5.70783\n"
    )
    assert versao == "1201-01"
    assert build == "12.1.5.70783"


def test_ler_versao_com_binario_falso(tmp_path: Path) -> None:
    falso = _binario_falso(
        tmp_path,
        "echo SimulationCraft 1201-01 for World of Warcraft 12.1.5.70783",
        'echo "SimulationCraft 1201-01 for World of Warcraft 12.1.5.70783"',
    )
    info = sr.ler_versao(falso)
    assert info.build == "12.1.5.70783"
    assert info.build_compativel is True
    assert info.aviso_build is None


def test_montar_comando_json2_obrigatorio(tmp_path: Path) -> None:
    comando = sr.montar_comando(
        "simc",
        "perfil.simc",
        tmp_path / "saida.json",
        iterations=10,
        fight_style="Patchwerk",
        threads=3,
        target_error=0.15,
        desired_targets=1,
    )
    assert "json2=" + str(tmp_path / "saida.json") in comando
    assert "iterations=10" in comando
    assert "fight_style=Patchwerk" in comando
    assert "threads=3" in comando
    assert "target_error=0.15" in comando
    assert "desired_targets=1" in comando
    assert all(arg != "json2=" for arg in comando)

    with pytest.raises(ValueError):
        sr.montar_comando("simc", "perfil.simc", "")


def test_chave_cache_deterministica_e_sensivel(tmp_path: Path) -> None:
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    binario = _binario_falso(tmp_path, "exit /b 0", "exit 0")

    parametros = {
        "iterations": 100,
        "fight_style": "DungeonSlice",
        "threads": 2,
        "target_error": None,
        "desired_targets": None,
        "extra_args": [],
    }
    chave1 = sr.chave_cache(perfil, parametros, binario)
    chave2 = sr.chave_cache(perfil, parametros, binario)
    assert chave1 == chave2

    outros = dict(parametros)
    outros["iterations"] = 200
    assert sr.chave_cache(perfil, outros, binario) != chave1


def _escrever_json(tmp_path: Path, dados: dict) -> Path:
    caminho = tmp_path / "resultado.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return caminho


def test_read_results_base_e_profilesets(tmp_path: Path) -> None:
    """Usa o vocabulário real do simc: os dois blocos nomeiam o erro diferente.

    ``collected_data.dps`` traz ``mean_std_dev`` e um profileset traz
    ``mean_error``/``mean_stddev``. A fixture antiga usava ``median_std_dev``,
    chave que a saída real do build 12.1.5.70783 não produz.
    """
    caminho = _escrever_json(
        tmp_path,
        {
            "sim": {
                "players": [
                    {
                        "collected_data": {
                            "dps": {
                                "mean": 200000.0,
                                "median": 201000.0,
                                "std_dev": 13000.0,      # dispersão entre lutas
                                "mean_std_dev": 1500.0,  # erro da média
                            }
                        }
                    }
                ],
                "profilesets": {
                    "results": [
                        {"name": "up_head", "mean": 205000.0, "mean_error": 1200.0},
                        {
                            "name": "ench_ring",
                            "median": 199000.0,
                            "stddev": 9000.0,
                            "mean_stddev": 900.0,
                        },
                    ]
                },
            }
        },
    )
    resultado = sr.read_results(caminho)
    assert resultado.base is not None
    assert resultado.base.dps == 201000.0
    assert resultado.base.erro_abs == 1500.0
    assert resultado.base.erro_pct == pytest.approx(100.0 * 1500.0 / 201000.0)
    assert [v.nome for v in resultado.variacoes] == ["up_head", "ench_ring"]
    assert resultado.variacoes[0].dps == 205000.0
    assert resultado.variacoes[1].dps == 199000.0
    # O erro é o da média, nunca a dispersão entre lutas (``std_dev``/``stddev``).
    assert resultado.variacoes[0].erro_abs == 1200.0
    assert resultado.variacoes[1].erro_abs == 900.0
    assert resultado.avisos == ()


def test_read_results_sem_base_e_sem_profilesets(tmp_path: Path) -> None:
    caminho = _escrever_json(tmp_path, {"sim": {"players": []}})
    resultado = sr.read_results(caminho)
    assert resultado.base is None
    assert resultado.variacoes == ()
    assert "base_ausente_no_json" in resultado.avisos
    assert "profilesets_ausentes" in resultado.avisos


def test_read_results_profilesets_em_lista(tmp_path: Path) -> None:
    """Build 12.1.5.70783 exposes profilesets as a list, not a dict."""
    caminho = _escrever_json(
        tmp_path,
        {
            "sim": {
                "players": [
                    {
                        "collected_data": {
                            "dps": {"median": 199485.0, "mean_std_dev": 153.0}
                        }
                    }
                ],
                "profilesets": [
                    {"name": "up_head", "median": 201000.0, "median_std_dev": 1000.0}
                ],
            }
        },
    )
    resultado = sr.read_results(caminho)
    assert resultado.base is not None
    assert resultado.base.dps == 199485.0
    assert len(resultado.variacoes) == 1
    assert resultado.variacoes[0].nome == "up_head"
    assert resultado.variacoes[0].dps == 201000.0
    assert resultado.avisos == ()


def test_comparar_com_referencia() -> None:
    delta, dentro = sr.comparar_com_referencia(254000.0, 254000.0)
    assert delta == 0.0
    assert dentro is True

    _, dentro = sr.comparar_com_referencia(254000.0 * 1.04, 254000.0)
    assert dentro is False

    with pytest.raises(ValueError):
        sr.comparar_com_referencia(1000.0, 0.0)


def test_run_simc_falha_sem_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    falso = _binario_falso(tmp_path, "exit /b 0", "exit 0")

    with pytest.raises(sr.SimcFalhou) as exc:
        sr.run_simc(perfil, simc_path=falso, usar_cache=False)
    assert "json2" in str(exc.value)


def test_run_simc_falha_com_codigo_nao_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    falso = _binario_falso(tmp_path, "exit /b 7", "exit 7")

    with pytest.raises(sr.SimcFalhou) as exc:
        sr.run_simc(perfil, simc_path=falso, usar_cache=False)
    assert "código" in str(exc.value) or "codigo" in str(exc.value)
