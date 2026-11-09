"""T11: escala do Pawn por build (P-044) — leitura do JSON, chave e strings."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from wowsim.data import pesos_medidos as pm
from wowsim.exportar.pawn import (
    escalas_das_builds,
    nome_escala,
    nome_pawn,
    quase_iguais,
    validar_como_pawn,
)
from wowsim.models import Personagem

pytestmark = pytest.mark.unit


def _json(fatores: dict, deltas: dict, dps: float = 200_000.0, erro: float = 100.0) -> dict:
    return {
        "sim": {
            "players": [
                {
                    "scale_factors": fatores,
                    "scale_deltas": deltas,
                    "collected_data": {"dps": {"mean": dps, "mean_std_dev": erro}},
                }
            ]
        }
    }


FATORES = {"Int": 20.0, "Crit": 9.0, "Haste": 10.0, "Mastery": 8.0, "Vers": 7.0, "Wdps": 1.0}
DELTAS = {"Int": 500, "Crit": 400, "Haste": 400, "Mastery": 400, "Vers": 400}


def test_ler_escala_guarda_fatores_crus_com_intelecto_e_erro() -> None:
    dps, erro, fatores, erros = pm.ler_escala(_json(FATORES, DELTAS))
    assert dps == 200_000.0 and erro == 100.0
    assert fatores == {"Int": 20.0, "Crit": 9.0, "Haste": 10.0, "Mastery": 8.0, "Vers": 7.0}
    assert erros["Haste"] == pytest.approx(math.sqrt(2) * 100.0 / 400)


def test_ler_escala_sem_scale_factors_levanta() -> None:
    with pytest.raises(ValueError):
        pm.ler_escala(_json({}, {}))


def test_chave_muda_com_os_talentos() -> None:
    p = Personagem(classe="warlock", spec="demonology", texto_original="")
    assert pm.chave_escala(p, "A", "DungeonSlice", 5000) != pm.chave_escala(p, "B", "DungeonSlice", 5000)


def test_medir_escala_exige_5000_iteracoes() -> None:
    with pytest.raises(ValueError):
        pm.medir_escala(Personagem(classe="warlock", texto_original=""), talentos="A", fight_style="Patchwerk", iterations=200)


def test_medir_escala_passa_talentos_e_scale_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pm, "DIR", tmp_path)
    monkeypatch.setattr(pm, "serializar_texto", lambda p, incluir_checksum=False: 'warlock="X"\n')
    visto = {}
    saida = tmp_path / "r.json"
    saida.write_text(json.dumps(_json(FATORES, DELTAS)), encoding="utf-8")

    def falso_run(perfil, **kw):
        visto.update(kw)
        return SimpleNamespace(json_path=saida)

    monkeypatch.setattr(pm.sr, "run_simc", falso_run)
    m = pm.medir_escala(Personagem(classe="warlock", texto_original=""), talentos="COD", fight_style="DungeonSlice")
    assert "talents=COD" in visto["extra_args"]
    assert "calculate_scale_factors=1" in visto["extra_args"]
    assert "scale_only=Int,Crit,Haste,Mastery,Vers" in visto["extra_args"]
    assert visto["iterations"] == 5000
    assert m.fatores["Int"] == 20.0 and m.talentos == "COD"
    gravado = json.loads(next(tmp_path.glob("escala_*.json")).read_text(encoding="utf-8"))
    assert gravado["talentos"] == "COD" and gravado["iteracoes"] == 5000 and gravado["base_dps"] == 200_000.0


def test_nomes_do_pawn() -> None:
    assert nome_pawn("death_knight") == "DeathKnight"
    assert nome_pawn("demonology") == "Demonology"
    assert nome_escala('Py "x" (m+)') == "Py x m+"


def _medida(fatores, erro=100.0, dps=200_000.0):
    _, _, f, e = pm.ler_escala(_json(fatores, DELTAS, dps=dps, erro=erro))
    return SimpleNamespace(dps=dps, fatores=f, erros=e)


def test_escalas_por_build_e_mistura_passam_no_parser_do_pawn() -> None:
    medicoes = {
        "m+ icy": _medida(FATORES),
        "single icy": _medida({**FATORES, "Mastery": 14.0}),
    }
    saida = escalas_das_builds(
        medicoes, {"m+ icy": 0.7, "single icy": 0.3},
        personagem="Pyrogalth", classe="warlock", spec="demonology",
    )
    nome, valores = validar_como_pawn(saida["builds"]["m+ icy"]["string"])
    assert nome == "Pyrogalth - m+ icy"
    assert valores["Class"] == "Warlock" and valores["Spec"] == "Demonology"
    assert valores["Intellect"] == "10.0"  # Int é o maior: vira escala_max
    nome_m, valores_m = validar_como_pawn(saida["mistura"])
    assert nome_m == "Pyrogalth - Mistura" and "Spec" not in valores_m
    # Mistura entre as duas builds na maestria
    assert float(valores["MasteryRating"]) < float(valores_m["MasteryRating"])
    assert saida["iguais"] == []


def test_builds_quase_iguais_dizem_use_uma_so() -> None:
    medicoes = {"a": _medida(FATORES, erro=2000.0), "b": _medida({**FATORES, "Crit": 9.2}, erro=2000.0)}
    saida = escalas_das_builds(medicoes, {}, personagem="P", classe="warlock", spec="demonology")
    assert saida["iguais"] == [["a", "b"]]


def test_quase_iguais_sem_erro_nao_afirma() -> None:
    assert quase_iguais({"X": 1.0}, {}, {"X": 1.0}, {}) is False
