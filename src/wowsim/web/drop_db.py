"""SQLite store for Droptimizer jobs (upgrade / best_in_bags / worst_in_bags)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .db import DB_PATH

STATUSES = ("pending", "running", "done", "error", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS drop_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    request_json TEXT NOT NULL,
    progresso_json TEXT,
    resultado_json TEXT,
    erro TEXT,
    cancelado INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_drop_status ON drop_jobs(status, created_at);
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


def criar_job(request_json: str, *, caminho: str | Path | None = None) -> str:
    job_id = uuid.uuid4().hex
    with _conexao(caminho) as con:
        con.execute(
            "INSERT INTO drop_jobs (id, status, request_json, created_at) "
            "VALUES (?, 'pending', ?, ?)",
            (job_id, request_json, _agora()),
        )
    return job_id


def atualizar_job(job_id: str, *, caminho: str | Path | None = None, **campos: object) -> None:
    permitidos = {
        "status",
        "progresso_json",
        "resultado_json",
        "erro",
        "cancelado",
        "started_at",
        "finished_at",
    }
    invalidos = set(campos) - permitidos
    if invalidos:
        raise ValueError(f"Campos não permitidos: {sorted(invalidos)}")
    if "status" in campos and campos["status"] not in STATUSES:
        raise ValueError(f"Status inválido: {campos['status']}")
    if not campos:
        return
    colunas = ", ".join(f"{nome} = ?" for nome in campos)
    with _conexao(caminho) as con:
        con.execute(
            f"UPDATE drop_jobs SET {colunas} WHERE id = ?",
            (*campos.values(), job_id),
        )


def _decodificar(dados: dict) -> dict:
    for chave in ("request_json", "progresso_json", "resultado_json"):
        valor = dados.get(chave)
        alvo = chave.replace("_json", "")
        if not valor:
            dados[alvo] = None
            continue
        try:
            dados[alvo] = json.loads(valor)
        except json.JSONDecodeError:
            dados[alvo] = None
    return dados


def obter_job(job_id: str, *, caminho: str | Path | None = None) -> dict | None:
    with _conexao(caminho) as con:
        linha = con.execute("SELECT * FROM drop_jobs WHERE id = ?", (job_id,)).fetchone()
    if linha is None:
        return None
    return _decodificar(dict(linha))


def listar_jobs(*, limite: int = 50, caminho: str | Path | None = None) -> list[dict]:
    with _conexao(caminho) as con:
        linhas = con.execute(
            "SELECT * FROM drop_jobs ORDER BY created_at DESC LIMIT ?", (limite,)
        ).fetchall()
    return [_decodificar(dict(linha)) for linha in linhas]


def jobs_pendentes(*, caminho: str | Path | None = None) -> list[str]:
    with _conexao(caminho) as con:
        linhas = con.execute(
            "SELECT id FROM drop_jobs "
            "WHERE status IN ('pending', 'running') AND cancelado = 0 "
            "ORDER BY created_at"
        ).fetchall()
    return [linha["id"] for linha in linhas]


def marcar_cancelamento(job_id: str, *, caminho: str | Path | None = None) -> bool:
    with _conexao(caminho) as con:
        cursor = con.execute(
            "UPDATE drop_jobs SET cancelado = 1 WHERE id = ?", (job_id,)
        )
        return cursor.rowcount > 0


def esta_cancelado(job_id: str, *, caminho: str | Path | None = None) -> bool:
    with _conexao(caminho) as con:
        linha = con.execute(
            "SELECT cancelado FROM drop_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return bool(linha and linha["cancelado"])
