"""Testes de degradação de orçamento, estimativa de custo e fake simc.

Cobrem os pontos P0/P1/P2 da rodada 2 de auditoria:
- ``SimcOrcamentoEsgotado`` em timeout real (fake simc que dorme);
- ``SimcCancelado`` matando o processo (fake simc);
- Top Gear devolve resultado parcial + aviso em vez de falhar;
- ``estimar_custo`` avisa antes do Run;
- validação de preferências.
"""

from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from wowsim import simc_runner as sr
from wowsim.models import ItemEquipado, Personagem
from wowsim.topgear.models import Candidato, ContextoSpec, TopGearRequest
from wowsim.topgear.runner import LeituraSim, estimar_custo
from wowsim.topgear.search import executar_topgear

pytestmark = pytest.mark.unit

BASE_DPS = 100_000.0


# --------------------------------------------------------------------------- #
# Fake simc: um launcher + script Python que imprime versão, dorme e escreve JSON
# --------------------------------------------------------------------------- #
_SCRIPT = textwrap.dedent(
    """
    import json
    import os
    import sys
    import time

    args = sys.argv[1:]
    if "--version" in args:
        print("SimulationCraft 1201-01 for World of Warcraft 12.1.5.70783")
        sys.exit(0)

    codigo = int(os.environ.get("WOWSIM_FAKE_EXIT", "0"))
    if codigo:
        sys.exit(codigo)

    chatice = int(os.environ.get("WOWSIM_FAKE_CHATTER", "0"))
    if chatice:
        sys.stdout.write("x" * chatice)
        sys.stdout.flush()

    time.sleep(float(os.environ.get("WOWSIM_FAKE_SLEEP", "0")))

    destino = None
    for arg in args:
        if arg.startswith("json2="):
            destino = arg.split("=", 1)[1]
    if destino:
        dados = {
            "sim": {
                "players": [
                    {
                        "collected_data": {
                            "dps": {"median": 100000.0, "median_std_dev": 100.0}
                        }
                    }
                ],
                "profilesets": [],
            }
        }
        with open(destino, "w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo)
    sys.exit(0)
    """
).strip()


def _fake_simc(tmp_path: Path) -> Path:
    script = tmp_path / "fake_simc.py"
    script.write_text(_SCRIPT, encoding="utf-8")
    if os.name == "nt":
        launcher = tmp_path / "simc_fake.bat"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8"
        )
    else:
        launcher = tmp_path / "simc_fake.sh"
        launcher.write_text(
            f'#!/bin/sh\n"{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


def test_timeout_levanta_orcamento_esgotado(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    falso = _fake_simc(tmp_path)
    monkeypatch.setenv("WOWSIM_FAKE_SLEEP", "5")

    with pytest.raises(sr.SimcOrcamentoEsgotado):
        sr.run_simc(perfil, simc_path=falso, timeout=0.5, usar_cache=False)


def test_cancelar_mata_processo(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    falso = _fake_simc(tmp_path)
    monkeypatch.setenv("WOWSIM_FAKE_SLEEP", "5")

    with pytest.raises(sr.SimcCancelado):
        sr.run_simc(
            perfil,
            simc_path=falso,
            timeout=30.0,
            cancelar=lambda: True,
            usar_cache=False,
        )


def test_orcamento_esgotado_e_subclasse_de_simcfalhou():
    assert issubclass(sr.SimcOrcamentoEsgotado, sr.SimcFalhou)


def test_montar_comando_inclui_max_time(tmp_path):
    comando = sr.montar_comando(
        "simc", "perfil.simc", tmp_path / "s.json", max_time=30
    )
    assert "max_time=30" in comando


def test_popen_nao_trava_com_saida_grande(tmp_path, monkeypatch):
    """Regressão: o caminho com cancelar não pode travar no buffer do PIPE."""
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    falso = _fake_simc(tmp_path)
    monkeypatch.setenv("WOWSIM_FAKE_CHATTER", "200000")

    execucao = sr.run_simc(
        perfil,
        simc_path=falso,
        timeout=20,
        cancelar=lambda: False,
        usar_cache=False,
    )
    resultado = sr.read_results(execucao.json_path)
    assert resultado.base is not None
    assert resultado.base.dps > 0


# --------------------------------------------------------------------------- #
# Degradação graciosa no Top Gear
# --------------------------------------------------------------------------- #
def _personagem() -> Personagem:
    return Personagem(
        texto_original="",
        talents_atual="ATUAL",
        equipado={
            "head": ItemEquipado(
                slot="head",
                item_id=1,
                bonus_ids=[100],
                linha_original="head=,id=1,bonus_id=100",
            ),
        },
    )


def _candidato(item_id: int) -> Candidato:
    return Candidato(
        slot="head", item_id=item_id, bonus_ids=[200], ilvl=341, fonte="teste"
    )


def test_preflight_ok_com_fake_simc(tmp_path, monkeypatch):
    from wowsim.topgear.runner import preflight

    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    falso = _fake_simc(tmp_path)

    pre = preflight(_personagem(), simc_path=falso, iterations=3, timeout=10)
    assert pre.ok is True
    assert pre.dps is not None and pre.dps > 0


def test_preflight_falha_rapido_quando_simc_quebra(tmp_path, monkeypatch):
    from wowsim.topgear.runner import preflight

    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    falso = _fake_simc(tmp_path)
    monkeypatch.setenv("WOWSIM_FAKE_EXIT", "7")

    pre = preflight(_personagem(), simc_path=falso, iterations=3, timeout=10)
    assert pre.ok is False
    assert pre.erro
    assert "7" in pre.erro or "codigo" in pre.erro or "código" in pre.erro


def test_topgear_devolve_parcial_quando_orcamento_estoira():
    chamadas = {"n": 0}

    def simulador(candidatos, iterations):
        chamadas["n"] += 1
        if chamadas["n"] == 1:  # chamada da base
            return LeituraSim(base_dps=BASE_DPS, resultados={})
        raise sr.SimcOrcamentoEsgotado("estourou")

    resultado = executar_topgear(
        _personagem(),
        {"head": [_candidato(10), _candidato(11)]},
        simulador=simulador,
        request=TopGearRequest(
            addon="",
            iterations_triagem=100,
            iterations_refino=100,
            max_profilesets_rodada=100,
            orcamento_segundos=60,
        ),
        ctx=ContextoSpec(),
    )

    assert resultado.base_dps == pytest.approx(BASE_DPS)
    assert resultado.melhor_dps == pytest.approx(BASE_DPS)
    assert any("Orçamento" in aviso for aviso in resultado.avisos)


# --------------------------------------------------------------------------- #
# Estimativa de custo
# --------------------------------------------------------------------------- #
def test_erro_alvo_nao_aplica_na_base():
    from wowsim.topgear.runner import erro_alvo_efetivo

    # n=0 é a medição da base: não passa target_error (evita rodar até max_time).
    assert erro_alvo_efetivo(0.2, 0) is None


def test_estimar_custo_conta_profilesets_e_tempo():
    pools = {"head": [_candidato(10), _candidato(11)], "chest": [_candidato(20)]}
    estimativa = estimar_custo(
        pools,
        iterations=200,
        orcamento_segundos=600,
        target_error=None,
        max_profilesets_rodada=300,
    )
    assert estimativa["profilesets_total_estimado"] == 3 + 2 * 4
    assert estimativa["segundos_estimados"] > 0
    assert estimativa["excede_orcamento"] is False


def test_estimar_custo_avisa_orcamento_curto():
    pools = {"head": [_candidato(i) for i in range(50)]}
    estimativa = estimar_custo(
        pools,
        iterations=10_000,
        orcamento_segundos=1,
        target_error=None,
        max_profilesets_rodada=300,
    )
    assert estimativa["excede_orcamento"] is True
    assert estimativa["avisos"]


def test_estimar_custo_target_error_ignorado_em_lote_grande():
    from wowsim.topgear.runner import LIMITE_PROFILESETS_TARGET_ERROR

    pools = {
        "head": [
            _candidato(i) for i in range(LIMITE_PROFILESETS_TARGET_ERROR + 10)
        ]
    }
    estimativa = estimar_custo(
        pools,
        iterations=200,
        orcamento_segundos=600,
        target_error=0.2,
        max_profilesets_rodada=1000,
    )
    assert estimativa["target_error_ignorado"] is True
    assert estimativa["target_error_aplicado"] is None


# --------------------------------------------------------------------------- #
# Validação de preferências
# --------------------------------------------------------------------------- #
def test_preferencia_chave_longa_rejeitada(tmp_path):
    from wowsim.web import perfil_store

    db = tmp_path / "wowsim.db"
    perfil_store.init_db(db)
    with pytest.raises(ValueError):
        perfil_store.salvar_preferencia("k" * 201, "v", caminho=db)
