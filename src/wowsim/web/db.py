"""SQLite job store for the optional web interface.

One connection per operation keeps the worker and the API from sharing a
connection across threads. Results are stored as JSON text.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "wowsim.db"
STATUSES = ("pending", "running", "done", "error")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    addon_text TEXT NOT NULL,
    iterations INTEGER NOT NULL,
    max_variacoes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    resultado_json TEXT,
    erro TEXT,
    relatorio_md TEXT,
    relatorio_html TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
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


def criar_job(
    addon_text: str,
    *,
    iterations: int = 200,
    max_variacoes: int = 20,
    caminho: str | Path | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    with _conexao(caminho) as con:
        con.execute(
            "INSERT INTO jobs (id, status, addon_text, iterations, max_variacoes, created_at) "
            "VALUES (?, 'pending', ?, ?, ?, ?)",
            (job_id, addon_text, int(iterations), int(max_variacoes), _agora()),
        )
    return job_id


def atualizar_job(
    job_id: str,
    *,
    caminho: str | Path | None = None,
    **campos: object,
) -> None:
    permitidos = {
        "status",
        "started_at",
        "finished_at",
        "resultado_json",
        "erro",
        "relatorio_md",
        "relatorio_html",
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
            f"UPDATE jobs SET {colunas} WHERE id = ?",
            (*campos.values(), job_id),
        )


def obter_job(job_id: str, *, caminho: str | Path | None = None) -> dict | None:
    with _conexao(caminho) as con:
        linha = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if linha is None:
        return None
    dados = dict(linha)
    if dados.get("resultado_json"):
        try:
            dados["resultado"] = json.loads(dados["resultado_json"])
        except json.JSONDecodeError:
            dados["resultado"] = None
    return dados


def jobs_pendentes(*, caminho: str | Path | None = None) -> list[str]:
    with _conexao(caminho) as con:
        linhas = con.execute(
            "SELECT id FROM jobs WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
    return [linha["id"] for linha in linhas]
