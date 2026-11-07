"""FastAPI surface for the optional local web interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..simc_runner import SimcFalhou
from . import advisor, db, sim_api, worker
from .static import montar_frontend


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


class AdvisorRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Pergunta do jogador.")
    specId: str | None = None
    scenario: str | None = None
    currentGearSummary: str | None = None


class PerfilRequest(BaseModel):
    profile: str = Field(min_length=20, description="Texto .simc a simular.")
    scenario: str = "patchwerk"
    iterations: int = Field(200, ge=10, le=20000)


class CompararRequest(BaseModel):
    base: str = Field(min_length=20)
    candidate: str = Field(min_length=20)
    scenario: str = "patchwerk"
    iterations: int = Field(200, ge=10, le=20000)


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


@app.get("/api/health")
def api_health() -> dict:
    """Mirror of Simulator-WoW's server.ts healthcheck."""
    return {"status": "ok", "patch": "12.1.5", "season": 2}


@app.post("/api/advisor")
async def api_advisor(pedido: AdvisorRequest) -> dict:
    """Tactical advisor: Gemini when configured, local audited fallback otherwise."""
    texto = await advisor.consultar(
        pedido.prompt,
        spec_id=pedido.specId,
        scenario=pedido.scenario,
        gear_summary=pedido.currentGearSummary,
    )
    return {"response": texto}


@app.post("/api/sim/profile")
def api_sim_profile(pedido: PerfilRequest) -> dict:
    """Run one .simc profile and return measured DPS."""
    try:
        return sim_api.rodar_perfil(pedido.profile, pedido.scenario, pedido.iterations)
    except SimcFalhou as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/sim/compare")
def api_sim_compare(pedido: CompararRequest) -> dict:
    """Run base vs candidate and return measured DPS plus error-aware verdict."""
    try:
        return sim_api.comparar(pedido.base, pedido.candidate, pedido.scenario, pedido.iterations)
    except SimcFalhou as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


# Serve the built React app (Simulator-WoW/dist) last so API routes win.
montar_frontend(app)
