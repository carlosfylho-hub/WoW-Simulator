"""FastAPI surface for the optional local web interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from ..droptimizer.pools import deduplicar, possuidos_da_mochila
from ..parser.addon import ErroParseAddon, parse_texto
from ..parser.combinar import combinar_textos
from ..simc_runner import SimcFalhou
from . import (
    advisor,
    catalog_api,
    db,
    drop_api,
    masmorras_api,
    perfil_store,
    sim_api,
    topgear_api,
    worker,
)
from .static import montar_frontend


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    # P3: simc logging is OFF for the CLI and ON for the web layer by default.
    from ..simc_runner import configurar_log_simc

    configurar_log_simc(True)
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


class ImportacaoRequest(BaseModel):
    texto: str = Field(min_length=20, description="Saída do /simc a persistir.")


class PreferenciaRequest(BaseModel):
    valor: str = Field(max_length=200_000, description="Valor serializado da preferência.")


class PreferenciasRequest(BaseModel):
    preferencias: dict[str, str] = Field(default_factory=dict)

    @field_validator("preferencias")
    @classmethod
    def _validar_lote(cls, valor: dict[str, str]) -> dict[str, str]:
        if len(valor) > 500:
            raise ValueError("Lote de preferências excede 500 chaves.")
        for chave, item in valor.items():
            if not chave or len(chave) > 200:
                raise ValueError("Chave de preferência inválida (1..200).")
            if len(item) > 200_000:
                raise ValueError(f"Valor da chave '{chave}' grande demais.")
        return valor


class AmrRequest(BaseModel):
    texto: str = Field(min_length=20, description="Export AskMrRobot v181.")
    classe_hint: str | None = Field(default=None, max_length=40)
    spec_hint: str | None = Field(default=None, max_length=40)
    incluir_inv: bool = False


class CombinarRequest(BaseModel):
    """Une um export SimC e/ou AMR em um perfil enriquecido."""

    simc: str | None = Field(
        default=None, min_length=20, max_length=20_000, description="Saída do /simc."
    )
    amr: str | None = Field(
        default=None, min_length=20, max_length=20_000, description="Export AskMrRobot."
    )
    primario: Literal["simc", "amr"] = "simc"
    classe_hint: str | None = Field(default=None, max_length=40)
    spec_hint: str | None = Field(default=None, max_length=40)
    incluir_inv: bool = True

    @model_validator(mode="after")
    def _validar_primario_amr(self) -> "CombinarRequest":
        if self.primario == "amr" and not (
            (self.amr or "").strip() or (self.simc or "").strip().startswith("$")
        ):
            raise ValueError(
                "primario='amr' exige um export AMR em 'amr' "
                "(ou 'simc' começando com '$')."
            )
        return self


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
        "threads_max": max(1, worker.NUCLEOS - 1),
        "vagas_simulacao": worker.VAGAS_SIMULACAO,
    }


@app.get("/api/health")
def api_health() -> dict:
    """Mirror of Simulator-WoW's server.ts healthcheck."""
    return {"status": "ok", "patch": "12.1.5", "season": 2}


@app.get("/api/catalog/items")
def api_catalog_items() -> dict:
    """Authoritative catalog (PT/EN names, ilvl, slot, source, bonus) as JSON."""
    itens = catalog_api.itens_catalogo()
    return {"total": len(itens), "itens": itens}


@app.get("/api/catalog/icones")
def api_catalog_icones() -> dict:
    """Every known item id -> texture slug, including raid/tier items."""
    mapa = catalog_api.mapa_icones()
    return {"total": len(mapa), "icones": mapa}


@app.get("/api/perfil/importacao")
def obter_importacao() -> dict:
    """Last persisted /simc import (survives app restarts and port changes)."""
    registro = perfil_store.obter()
    return {
        "texto": registro["texto"] if registro else None,
        "atualizado_em": registro["atualizado_em"] if registro else None,
    }


@app.put("/api/perfil/importacao")
def salvar_importacao(pedido: ImportacaoRequest) -> dict:
    perfil_store.salvar(pedido.texto)
    return {"ok": True}


@app.get("/api/preferencias")
def obter_preferencias() -> dict:
    """Todas as preferências persistidas (sobrevivem ao port aleatório)."""
    return {"preferencias": perfil_store.obter_preferencias()}


@app.get("/api/preferencias/{chave}")
def obter_preferencia(chave: str) -> dict:
    return {"chave": chave, "valor": perfil_store.obter_preferencia(chave)}


@app.put("/api/preferencias")
def salvar_preferencias(pedido: PreferenciasRequest) -> dict:
    """Grava várias preferências num único PUT (evita N requisições no boot)."""
    for chave, valor in pedido.preferencias.items():
        perfil_store.salvar_preferencia(chave, valor)
    return {"ok": True, "total": len(pedido.preferencias)}


@app.put("/api/preferencias/{chave}")
def salvar_preferencia(chave: str, pedido: PreferenciaRequest) -> dict:
    perfil_store.salvar_preferencia(chave, pedido.valor)
    return {"ok": True}


@app.post("/api/import/amr")
def importar_amr(pedido: AmrRequest) -> dict:
    """Decodifica um export AMR e devolve um perfil SimC canônico + avisos."""
    try:
        personagem = parse_texto(
            pedido.texto,
            classe_hint=pedido.classe_hint,
            spec_hint=pedido.spec_hint,
            incluir_inv=pedido.incluir_inv,
        )
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "nome": personagem.nome,
        "classe": personagem.classe,
        "spec": personagem.spec,
        "nivel": personagem.nivel,
        "itens": len(personagem.equipado),
        "slots": sorted(personagem.equipado),
        "simc": personagem.texto_original,
        "avisos": [
            alerta.model_dump(mode="json") for alerta in personagem.alertas
        ],
    }


@app.post("/api/import/combinar")
def importar_combinado(pedido: CombinarRequest) -> dict:
    """Une SimC + AMR: equipado/talentos de um lado, raça/.inv/.hlv do outro."""
    if not pedido.simc and not pedido.amr:
        raise HTTPException(
            status_code=422, detail="Informe ao menos um export (SimC ou AMR)."
        )
    try:
        combo = combinar_textos(
            pedido.simc,
            pedido.amr,
            primario=pedido.primario,
            classe_hint=pedido.classe_hint,
            spec_hint=pedido.spec_hint,
            incluir_inv=pedido.incluir_inv,
        )
    except (ErroParseAddon, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    personagem = combo.personagem
    # P1-03: possuídos distintos e não-equipados (o merge pode repetir o equipado).
    equipados = {
        (slot, item.item_id, tuple(sorted(item.bonus_ids)))
        for slot, item in personagem.equipado.items()
        if item.item_id is not None
    }
    possuidos = len(
        [
            item
            for item in deduplicar(possuidos_da_mochila(personagem))
            if (item.slot, item.item_id, tuple(sorted(item.bonus_ids)))
            not in equipados
        ]
    )
    return {
        "nome": personagem.nome,
        "classe": personagem.classe,
        "spec": personagem.spec,
        "nivel": personagem.nivel,
        "raca": personagem.raca,
        "primario": combo.primario,
        "fontes": combo.fontes,
        "itens": len(personagem.equipado),
        "slots": sorted(personagem.equipado),
        "possuidos": possuidos,
        "talentos": bool(personagem.talents_atual),
        "omnium": len(personagem.omnium_ids_brutos),
        "simc": combo.simc,
        "avisos": [alerta.model_dump(mode="json") for alerta in combo.avisos],
    }


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


app.include_router(topgear_api.router)
app.include_router(drop_api.router)
app.include_router(masmorras_api.router)


# Serve the built React app (Simulator-WoW/dist) last so API routes win.
montar_frontend(app)
