"""End-to-end mechanics test with a synthetic simc double.

This test never produces reportable numbers: the JSON is written by a test
double and exists only to prove that json2 wiring, cache reuse and result
parsing work. Real numbers require the real binary and the real fixture.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from wowsim import simc_runner as sr

pytestmark = pytest.mark.unit

FAKE_SIMC = '''\
import json
import sys
from pathlib import Path

if "--version" in sys.argv:
    print("SimulationCraft 1201-01 for World of Warcraft 12.1.5.70783")
    raise SystemExit(0)

out = None
for arg in sys.argv[1:]:
    if arg.startswith("json2=") and len(arg) > len("json2="):
        out = arg[len("json2="):]

if not out:
    print("json2 ausente", file=sys.stderr)
    raise SystemExit(9)

dados = {
    "sim": {
        "players": [
            {
                "collected_data": {
                    "dps": {"median": 254000.0, "median_std_dev": 1200.0}
                }
            }
        ],
        "profilesets": {
            "results": [
                {"name": "up_head", "median": 256000.0, "median_std_dev": 1300.0},
                {"name": "ench_ring", "median": 253000.0, "median_std_dev": 900.0},
            ]
        },
    }
}
Path(out).write_text(json.dumps(dados), encoding="utf-8")
'''


def _binario_sintetico(tmp_path: Path) -> Path:
    script = tmp_path / "fake_simc.py"
    script.write_text(FAKE_SIMC, encoding="utf-8")

    if os.name == "nt":
        wrapper = tmp_path / "simc_fake.cmd"
        wrapper.write_text(
            '@echo off\r\npython "%~dp0fake_simc.py" %*\r\n', encoding="utf-8"
        )
    else:
        wrapper = tmp_path / "simc_fake.sh"
        wrapper.write_text(
            '#!/bin/sh\nexec python "$(dirname "$0")/fake_simc.py" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper


def test_pipeline_completo_com_binario_sintetico(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sr, "CACHE_DIR", tmp_path / "cache")
    perfil = tmp_path / "perfil.simc"
    perfil.write_text('warlock="Teste"\n', encoding="utf-8")
    simc = _binario_sintetico(tmp_path)

    primeira = sr.run_simc(
        perfil,
        simc_path=simc,
        iterations=10,
        fight_style="DungeonSlice",
        threads=1,
    )
    assert primeira.cache_hit is False
    assert primeira.info.build == "12.1.5.70783"
    assert primeira.json_path.is_file()

    resultado = sr.read_results(primeira.json_path)
    assert resultado.base is not None
    assert resultado.base.dps == 254000.0
    assert [v.nome for v in resultado.variacoes] == ["up_head", "ench_ring"]
    assert resultado.avisos == ()

    segunda = sr.run_simc(
        perfil,
        simc_path=simc,
        iterations=10,
        fight_style="DungeonSlice",
        threads=1,
    )
    assert segunda.cache_hit is True
    assert segunda.chave == primeira.chave
    assert segunda.json_path == primeira.json_path

    terceira = sr.run_simc(
        perfil,
        simc_path=simc,
        iterations=11,
        fight_style="DungeonSlice",
        threads=1,
    )
    assert terceira.cache_hit is False
    assert terceira.chave != primeira.chave
