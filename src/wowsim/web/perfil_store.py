"""Persist the last ``/simc`` import in SQLite.

The desktop window opens on a random local port, so browser ``localStorage`` is
not a reliable store across restarts (origin includes the port). The backend
keeps the last imported text here and exposes it through ``/api/perfil``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .db import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS perfil_importacao (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    texto TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferencias (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
"""


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conexao(caminho: str | Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(caminho or DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db(caminho: str | Path | None = None) -> None:
    with _conexao(caminho) as con:
        con.executescript(SCHEMA)


def salvar(texto: str, *, caminho: str | Path | None = None) -> None:
    """Store (or replace) the single persisted import."""
    if not texto or len(texto.strip()) < 20:
        raise ValueError("Importação vazia ou curta demais para persistir.")
    with _conexao(caminho) as con:
        con.execute(
            "INSERT INTO perfil_importacao (id, texto, atualizado_em) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET texto = excluded.texto, "
            "atualizado_em = excluded.atualizado_em",
            (texto, _agora()),
        )


def obter(*, caminho: str | Path | None = None) -> dict | None:
    with _conexao(caminho) as con:
        linha = con.execute(
            "SELECT texto, atualizado_em FROM perfil_importacao WHERE id = 1"
        ).fetchone()
    if linha is None:
        return None
    return {"texto": linha["texto"], "atualizado_em": linha["atualizado_em"]}


MAX_CHAVE = 200
MAX_VALOR = 200_000


def salvar_preferencia(
    chave: str, valor: str, *, caminho: str | Path | None = None
) -> None:
    """Persist a generic key/value preference (AMR, form fields, etc.)."""
    if not chave:
        raise ValueError("Chave de preferência vazia.")
    if len(chave) > MAX_CHAVE:
        raise ValueError(f"Chave de preferência excede {MAX_CHAVE} caracteres.")
    if len(valor) > MAX_VALOR:
        raise ValueError(f"Valor de preferência excede {MAX_VALOR} caracteres.")
    with _conexao(caminho) as con:
        con.execute(
            "INSERT INTO preferencias (chave, valor, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
            "atualizado_em = excluded.atualizado_em",
            (chave, valor, _agora()),
        )


def obter_preferencia(chave: str, *, caminho: str | Path | None = None) -> str | None:
    with _conexao(caminho) as con:
        linha = con.execute(
            "SELECT valor FROM preferencias WHERE chave = ?", (chave,)
        ).fetchone()
    return linha["valor"] if linha is not None else None


def obter_preferencias(*, caminho: str | Path | None = None) -> dict[str, str]:
    with _conexao(caminho) as con:
        linhas = con.execute("SELECT chave, valor FROM preferencias").fetchall()
    return {linha["chave"]: linha["valor"] for linha in linhas}
