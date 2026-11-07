"""FastAPI surface for the optional local web interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import db, worker


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    worker.iniciar()
    try:
        yield
    finally:
        worker.encerrar()


app = FastAPI(
    title="WoW Calculator Sim",
    description="Simulador local de equipamento baseado no SimulationCraft. Sem login, uso pessoal.",
    version="0.7.0",
    lifespan=_lifespan,
)


class SimRequest(BaseModel):
    addon: str = Field(min_length=20, description="Saída do /simc ou do addon.")
    iterations: int = Field(200, ge=10, le=20000)
    max_variacoes: int = Field(20, ge=1, le=200)


def _publico(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "iterations": job["iterations"],
        "max_variacoes": job["max_variacoes"],
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "erro": job.get("erro"),
        "resultado": job.get("resultado"),
        "relatorio_md": job.get("relatorio_md"),
        "relatorio_html": job.get("relatorio_html"),
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "workers": worker.WORKERS,
        "threads_por_job": worker.THREADS_POR_JOB,
    }


@app.post("/sim", status_code=202)
def criar_sim(pedido: SimRequest) -> dict:
    job_id = db.criar_job(
        pedido.addon,
        iterations=pedido.iterations,
        max_variacoes=pedido.max_variacoes,
    )
    worker.enfileirar(job_id)
    return {"id": job_id, "status": "pending"}


@app.get("/sim/{job_id}")
def consultar_sim(job_id: str) -> dict:
    job = db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return _publico(job)


@app.get("/sim/{job_id}/relatorio", response_class=FileResponse)
def baixar_relatorio(job_id: str) -> FileResponse:
    job = db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] != "done" or not job.get("relatorio_md"):
        raise HTTPException(status_code=409, detail="Relatório ainda não está pronto.")
    caminho = Path(job["relatorio_md"])
    if not caminho.is_file():
        raise HTTPException(status_code=410, detail="Arquivo do relatório ausente.")
    return FileResponse(caminho, media_type="text/markdown", filename="relatorio.md")
