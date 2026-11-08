"""Persisted /simc import store."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.web import perfil_store

pytestmark = pytest.mark.unit

TEXTO = "warlock=Teste\nlevel=90\n" + "x" * 40


def test_salva_e_le_importacao(tmp_path: Path) -> None:
    caminho = tmp_path / "perfil.db"
    perfil_store.init_db(caminho)

    assert perfil_store.obter(caminho=caminho) is None

    perfil_store.salvar(TEXTO, caminho=caminho)
    registro = perfil_store.obter(caminho=caminho)
    assert registro is not None
    assert registro["texto"] == TEXTO
    assert registro["atualizado_em"]


def test_sobrescreve_a_ultima_importacao(tmp_path: Path) -> None:
    caminho = tmp_path / "perfil.db"
    perfil_store.init_db(caminho)
    perfil_store.salvar(TEXTO, caminho=caminho)
    perfil_store.salvar(TEXTO + "\n# novo", caminho=caminho)
    registro = perfil_store.obter(caminho=caminho)
    assert registro is not None
    assert registro["texto"].endswith("# novo")


def test_texto_curto_nao_persiste(tmp_path: Path) -> None:
    caminho = tmp_path / "perfil.db"
    perfil_store.init_db(caminho)
    with pytest.raises(ValueError):
        perfil_store.salvar("curto", caminho=caminho)
