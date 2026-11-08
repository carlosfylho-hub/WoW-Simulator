"""Data gate tests: current snapshot passes, corrupted ones are blocked."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wowsim.data.gate import verificar
from wowsim.paths import DADOS_DIR

pytestmark = pytest.mark.schema


def test_snapshot_atual_passa_no_gate() -> None:
    assert verificar(DADOS_DIR) == []


def test_arquivo_ausente_bloqueia(tmp_path: Path) -> None:
    copia = tmp_path / "dados"
    shutil.copytree(DADOS_DIR, copia)
    (copia / "rune_ids_s2.json").unlink()

    motivos = verificar(copia)
    assert any("rune_ids_s2.json" in motivo for motivo in motivos)


def test_contagem_de_gemas_bloqueia(tmp_path: Path) -> None:
    copia = tmp_path / "dados"
    shutil.copytree(DADOS_DIR, copia)
    caminho = copia / "encantamentos_e_gemas_s2.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["gemas"] = {}
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    motivos = verificar(copia)
    assert any("gemas" in motivo for motivo in motivos)


def test_bonus_de_ilvl_bloqueia(tmp_path: Path) -> None:
    copia = tmp_path / "dados"
    shutil.copytree(DADOS_DIR, copia)
    caminho = copia / "derivados" / "bonus_ilvl.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["bonus"]["12856"]["ilvl"] = 999
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    motivos = verificar(copia)
    assert any("12856" in motivo for motivo in motivos)
