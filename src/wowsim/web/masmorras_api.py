"""FastAPI routes for the M+ dungeon ranking."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from ..data.classes import atributo_da_classe, tipo_armadura_da_classe
from ..gen.profilesets import estimar_segundos
from ..masmorras.avaliar import montar_opcoes
from ..masmorras.catalogo import elegivel, itens_por_masmorra
from ..masmorras.modelos import RankingRequest, RankingResult
from ..parser.addon import ErroParseAddon, parse_texto
from ..topgear.search import conjunto_do_personagem
from . import masmorras_db
from .worker import enfileirar_masmorras

router = APIRouter(prefix="/api/masmorras", tags=["masmorras"])


def _publico(job: dict) -> dict:
    request = job.get("request") or {}
    request_publico = {
        chave: valor
        for chave, valor in request.items()
        if chave not in ("addon", "amr")
    }
    return {
        "id": job["id"],
        "status": job["status"],
        "request": request_publico,
        "progresso": job.get("progresso"),
        "resultado": job.get("resultado"),
        "erro": job.get("erro"),
        "cancelado": bool(job.get("cancelado")),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


@router.get("")
def listar_masmorras() -> dict:
    jobs = []
    for job in masmorras_db.listar_jobs():
        publico = _publico(job)
        publico.pop("resultado", None)
        jobs.append(publico)
    return {"jobs": jobs}


@router.post("", status_code=202)
def criar_masmorras(pedido: RankingRequest) -> dict:
    if len(pedido.addon.strip()) < 20:
        raise HTTPException(
            status_code=422, detail="Saída do /simc ou export AMR muito curta."
        )
    job_id = masmorras_db.criar_job(pedido.model_dump_json())
    enfileirar_masmorras(job_id)
    return {"id": job_id, "status": "pending"}


@router.get("/estimativa")
def estimar_masmorras(
    addon: str = Query(min_length=20, description="Saída do /simc ou export AMR."),
    ilvl: int = Query(341, description="321/328/334/341."),
    iteracoes_triagem: int = Query(300, ge=10, le=100_000),
    iteracoes_refino: int = Query(3000, ge=10, le=100_000),
) -> dict:
    """Estimativa de custo do ranking antes do Run."""
    try:
        personagem = parse_texto(addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tipo = tipo_armadura_da_classe(personagem.classe)
    atributo = atributo_da_classe(personagem.classe)
    elegiveis = [
        item
        for item in itens_por_masmorra()
        if elegivel(item, tipo_armadura=tipo, atributo=atributo)
    ]
    base = conjunto_do_personagem(personagem)
    try:
        conjuntos, _ = montar_opcoes(base, elegiveis, ilvl=ilvl, classe=personagem.classe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    n = len(conjuntos)
    segundos = estimar_segundos(n, iteracoes_triagem) + estimar_segundos(
        n, iteracoes_refino
    )
    contagens = Counter(item.masmorra for item in elegiveis)
    return {
        "profilesets_total_estimado": n,
        "segundos_estimados": round(segundos, 1),
        "elegiveis_total": len(elegiveis),
        "contagens": dict(contagens),
    }


@router.get("/{job_id}")
def consultar_masmorras(job_id: str) -> dict:
    job = masmorras_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return _publico(job)


@router.post("/{job_id}/cancelar")
def cancelar_masmorras(job_id: str) -> dict:
    job = masmorras_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] in ("done", "error", "cancelled"):
        return {
            "id": job_id,
            "status": job["status"],
            "cancelado": job["status"] == "cancelled",
        }
    masmorras_db.marcar_cancelamento(job_id)
    return {"id": job_id, "status": job["status"], "cancelado": True}


@router.get("/{job_id}/resultado")
def resultado_masmorras(job_id: str) -> dict:
    job = masmorras_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] != "done" or job.get("resultado") is None:
        raise HTTPException(status_code=409, detail="Resultado ainda não está pronto.")
    return RankingResult(**job["resultado"]).model_dump(mode="json")
