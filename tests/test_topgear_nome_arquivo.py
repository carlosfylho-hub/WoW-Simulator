"""A-05: o nome do .simc salvo não pode conter caractere recusado pelo Windows."""

from __future__ import annotations

import pytest

from wowsim.web.topgear_api import _nome_arquivo

pytestmark = pytest.mark.unit


def test_nome_arquivo_remove_caracteres_perigosos() -> None:
    nome = _nome_arquivo("a/b\\c:d?e*f")
    assert nome.startswith("topgear-")
    assert nome.endswith(".simc")
    assert all(ch.isalnum() or ch in "-_." for ch in nome)


def test_nome_arquivo_vazio_vira_fallback() -> None:
    nome = _nome_arquivo("///")
    assert nome.startswith("topgear-job-")
