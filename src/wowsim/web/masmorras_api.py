"""FastAPI routes for the M+ dungeon ranking."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..data.classes import atributo_da_classe, tipo_armadura_da_classe
from ..gen.profilesets import estimar_segundos
from ..masmorras.avaliar import montar_opcoes
from ..masmorras.builds import cenario_da_build
from ..masmorras.cofre import opcoes_do_cofre
from ..masmorras.catalogo import elegivel, itens_por_masmorra
from ..masmorras.modelos import RankingRequest, RankingResult
from ..parser.addon import ErroParseAddon, parse_texto
from ..parser.amr import parse_amr
from ..topgear.runner import estilo_de_luta
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


class PedidoBuilds(BaseModel):
    addon: str = Field(min_length=20, max_length=20_000)


@router.post("/builds")
def builds_disponiveis(pedido: PedidoBuilds) -> dict:
    """Builds (loadouts) do export do SimC, com o cenário sugerido pelo nome (T9)."""
    try:
        personagem = parse_texto(pedido.addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    builds = []
    if personagem.talents_atual:
        builds.append({"nome": "Atual", "cenario_sugerido": "dungeon_slice"})
    builds.extend(
        {"nome": nome, "cenario_sugerido": cenario_da_build(nome)}
        for nome in personagem.loadouts
    )
    return {"classe": personagem.classe, "spec": personagem.spec, "builds": builds}


# Execuções do simc por escala do Pawn: base + Int, Crit, Haste, Mastery, Vers.
EXECUCOES_POR_ESCALA = 6


@router.get("/estimativa")
def estimar_masmorras(
    addon: str = Query(min_length=20, description="Saída do /simc ou export AMR."),
    ilvl: int = Query(341, description="321/328/334/341."),
    iteracoes_triagem: int = Query(300, ge=10, le=100_000),
    iteracoes_refino: int = Query(3000, ge=10, le=100_000),
    modo: str = Query("masmorras", pattern="^(masmorras|cofre)$"),
    amr: str | None = Query(None, description="Export AMR (modo cofre)."),
    builds: int = Query(0, ge=0, le=6, description="Quantas builds (T9)."),
    medir_pesos: bool = Query(False),
    iteracoes_pesos: int = Query(5_000, ge=5_000, le=100_000),
    scenario: str = Query("dungeon_slice", description="Cenário sem builds."),
    cenarios: str = Query("", description="Cenário de cada build, separados por vírgula."),
    max_refino: int = Query(24, ge=1, le=500),
) -> dict:
    """Estimativa de custo do ranking antes do Run (por build, quando houver)."""
    contagens: Counter = Counter()
    if modo == "cofre":
        texto = (amr or "").strip() or (addon.strip() if addon.strip().startswith("$") else "")
        if not texto:
            raise HTTPException(status_code=400, detail="O Grande Cofre exige o export do AMR.")
        try:
            opcoes = [op for op in opcoes_do_cofre(parse_amr(texto)) if op["slots"]]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Cada opção vira um candidato por slot (anel/berloque: dois) e às vezes um gêmeo.
        n = sum(len(op["slots"]) for op in opcoes)
        elegiveis_total = len(opcoes)
        contagens["Grande Cofre"] = elegiveis_total
    else:
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
        elegiveis_total = len(elegiveis)
        contagens.update(item.masmorra for item in elegiveis)

    # Refino: só os ``max_refino`` melhores itens (cada item ~ n/elegíveis profilesets).
    por_item = n / elegiveis_total if elegiveis_total else 1.0
    n_refino = min(n, round(max_refino * por_item))
    lista = [c for c in cenarios.split(",") if c.strip()][: max(1, builds)] if builds else []
    estilos = [estilo_de_luta(c.strip()) for c in lista] or [estilo_de_luta(scenario)]
    if builds and len(estilos) < builds:
        estilos += [estilos[-1]] * (builds - len(estilos))
    segundos = 0.0
    for estilo in estilos:
        segundos += estimar_segundos(n, iteracoes_triagem, estilo)
        segundos += estimar_segundos(n_refino, iteracoes_refino, estilo)
        if builds:
            segundos += estimar_segundos(2, iteracoes_refino, estilo)  # confirmação
        if medir_pesos:
            segundos += estimar_segundos(EXECUCOES_POR_ESCALA, iteracoes_pesos, estilo)
    return {
        "profilesets_total_estimado": (n + n_refino) * len(estilos),
        "segundos_estimados": round(segundos, 1),
        # Folga de 30% + 1 min para o pré-voo e a variação entre rodadas.
        "orcamento_sugerido": int(segundos * 1.3 + 60),
        "elegiveis_total": elegiveis_total,
        "contagens": dict(contagens),
        "builds": builds,
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
