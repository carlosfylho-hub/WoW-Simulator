"""FastAPI routes for the Droptimizer (upgrade / best/worst in bags)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..droptimizer.models import DropRequest
from ..gen.profilesets import estimar_segundos
from ..parser.addon import ErroParseAddon, parse_texto
from ..topgear.pools import construir_pools, resumo
from ..topgear.runner import erro_alvo_efetivo
from . import drop_db
from .topgear_worker import atributo_da_classe, tipo_armadura_da_classe
from .worker import enfileirar_drop

router = APIRouter(prefix="/api/droptimizer", tags=["droptimizer"])


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
def listar_drop() -> dict:
    jobs = []
    for job in drop_db.listar_jobs():
        publico = _publico(job)
        publico.pop("resultado", None)
        jobs.append(publico)
    return {"jobs": jobs}


@router.post("", status_code=202)
def criar_drop(pedido: DropRequest) -> dict:
    if len(pedido.addon.strip()) < 20:
        raise HTTPException(
            status_code=422, detail="Saída do /simc ou export AMR muito curta."
        )
    job_id = drop_db.criar_job(pedido.model_dump_json())
    enfileirar_drop(job_id)
    return {"id": job_id, "status": "pending"}


@router.get("/estimativa")
def estimar_drop(
    addon: str = Query(min_length=20, description="Saída do /simc."),
    pool: int = Query(12, ge=1, le=100),
    iterations: int = Query(200, ge=10, le=100_000),
    orcamento_segundos: int = Query(600, ge=1, le=86_400),
    target_error: float | None = Query(None),
    max_profilesets_rodada: int = Query(300, ge=1, le=5_000),
    tipo_armadura: str | None = Query(None),
    atributo: str | None = Query(None),
) -> dict:
    """Estimativa de custo do ranking antes do Run."""
    try:
        personagem = parse_texto(addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tipo = tipo_armadura or tipo_armadura_da_classe(personagem.classe)
    atrib = atributo or atributo_da_classe(personagem.classe)
    pools = construir_pools(tipo_armadura=tipo, atributo=atrib, pool_por_slot=pool)
    n_candidatos = sum(len(lista) for lista in pools.values())
    limite = min(n_candidatos, max_profilesets_rodada) if n_candidatos else 0
    erro = erro_alvo_efetivo(target_error, limite)
    segundos = estimar_segundos(n_candidatos, iterations) if n_candidatos else 0.0
    excede = segundos > orcamento_segundos
    avisos: list[str] = []
    if target_error is not None and erro is None:
        avisos.append(
            "Erro-alvo ignorado: muitos candidatos no mesmo lote. "
            "Reduza as pools para o simc parar pelo erro."
        )
    if excede:
        avisos.append(
            f"Estimativa de ~{segundos:.0f}s excede o orçamento de "
            f"{orcamento_segundos}s. Aumente o orçamento ou reduza pools/iterações."
        )
    return {
        "profilesets_total_estimado": n_candidatos,
        "segundos_estimados": round(segundos, 1),
        "excede_orcamento": excede,
        "target_error_aplicado": erro,
        "target_error_ignorado": target_error is not None and erro is None,
        "contagens": resumo(pools),
        "avisos": avisos,
    }


@router.get("/{job_id}")
def consultar_drop(job_id: str) -> dict:
    job = drop_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return _publico(job)


@router.post("/{job_id}/cancelar")
def cancelar_drop(job_id: str) -> dict:
    job = drop_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] in ("done", "error", "cancelled"):
        return {
            "id": job_id,
            "status": job["status"],
            "cancelado": job["status"] == "cancelled",
        }
    drop_db.marcar_cancelamento(job_id)
    return {"id": job_id, "status": job["status"], "cancelado": True}


@router.get("/{job_id}/resultado")
def resultado_drop(job_id: str) -> dict:
    job = drop_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] != "done" or job.get("resultado") is None:
        raise HTTPException(status_code=409, detail="Resultado ainda não está pronto.")
    return job["resultado"]
