"""FastAPI routes for the Top Gear job (Raidbots style)."""

from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from ..data import pesos as pesos_mod
from ..data import tier
from ..paths import PROJECT_ROOT
from ..heuristic.score import pontuar_candidato
from ..parser.addon import ErroParseAddon, parse_texto, serializar_texto
from ..topgear.catalisador import adicionar_gemeos, estimar_pacotes_max, pecas_de_tier
from ..topgear.models import Conjunto, TopGearRequest
from ..topgear.pools import construir_pools, resumo, secoes_ausentes
from ..topgear.runner import estimar_custo, linhas_override
from ..topgear.search import conjunto_do_personagem
from . import topgear_db
from .topgear_worker import atributo_da_classe, tipo_armadura_da_classe
from .worker import enfileirar_topgear

router = APIRouter(prefix="/api/topgear", tags=["topgear"])


def _publico(job: dict) -> dict:
    request = job.get("request") or {}
    request_publico = {chave: valor for chave, valor in request.items() if chave != "addon"}
    return {
        "id": job["id"],
        "status": job["status"],
        "request": request_publico,
        "progresso": job.get("progresso"),
        "estado": job.get("estado"),
        "resultado": job.get("resultado"),
        "erro": job.get("erro"),
        "cancelado": bool(job.get("cancelado")),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


def _listar_jobs() -> list[dict]:
    jobs = topgear_db.listar_jobs()
    saida = []
    for job in jobs:
        publico = _publico(job)
        # The list omits the heavy result payload; fetch it per job instead.
        publico.pop("resultado", None)
        publico.pop("estado", None)
        saida.append(publico)
    return saida


@router.get("")
def listar_topgear() -> dict:
    return {"jobs": _listar_jobs()}


@router.post("", status_code=202)
def criar_topgear(pedido: TopGearRequest) -> dict:
    if len(pedido.addon.strip()) < 20:
        raise HTTPException(
            status_code=422, detail="Saída do /simc muito curta para um job."
        )
    job_id = topgear_db.criar_job(pedido.model_dump_json())
    enfileirar_topgear(job_id)
    return {"id": job_id, "status": "pending"}


@router.get("/pools")
def previa_pools(
    addon: str = Query(min_length=20, description="Saída do /simc."),
    pool: int = Query(12, ge=1, le=100),
    tipo_armadura: str | None = Query(None),
    atributo: str | None = Query(None),
) -> dict:
    try:
        personagem = parse_texto(addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # P0-08: derive armor/attribute from the class instead of a UI hardcode.
    tipo = tipo_armadura or tipo_armadura_da_classe(personagem.classe)
    atrib = atributo or atributo_da_classe(personagem.classe)

    pools = construir_pools(tipo_armadura=tipo, atributo=atrib, pool_por_slot=pool)
    itens = {
        slot: [
            {
                "item_id": candidato.item_id,
                "nome_pt": candidato.nome_pt,
                "nome_en": candidato.nome_en,
                "ilvl": candidato.ilvl,
                "bonus_id": candidato.bonus_id,
                "slot": candidato.slot,
            }
            for candidato in candidatos
        ]
        for slot, candidatos in pools.items()
    }
    return {
        "classe": personagem.classe,
        "spec": personagem.spec,
        "tipo_armadura": tipo,
        "atributo": atrib,
        "contagens": resumo(pools),
        "itens": itens,
        "avisos": secoes_ausentes(tipo),
    }


@router.get("/estimativa")
def estimar_topgear(
    addon: str = Query(min_length=20, description="Saída do /simc."),
    pool: int = Query(12, ge=1, le=100),
    iterations: int = Query(200, ge=10, le=100_000),
    orcamento_segundos: int = Query(600, ge=1, le=86_400),
    target_error: float | None = Query(None),
    max_profilesets_rodada: int = Query(300, ge=1, le=5_000),
    tipo_armadura: str | None = Query(None),
    atributo: str | None = Query(None),
    catalisador: bool = Query(False),
    max_catalisados: int | None = Query(None, ge=0, le=5),
) -> dict:
    """Estimativa de custo exibida antes do Run (profilesets e segundos)."""
    try:
        personagem = parse_texto(addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tipo = tipo_armadura or tipo_armadura_da_classe(personagem.classe)
    atrib = atributo or atributo_da_classe(personagem.classe)
    pools = construir_pools(tipo_armadura=tipo, atributo=atrib, pool_por_slot=pool)
    extras = 0
    avisos_cat: list[str] = []
    if catalisador:
        if not tier.disponivel():
            avisos_cat.append(
                "Catalisador pedido, mas tier_sets.json está ausente — custo sem gêmeos/pacotes."
            )
        else:
            antes = sum(len(lista) for lista in pools.values())
            pools = adicionar_gemeos(pools, personagem.classe)
            gemeos = sum(len(lista) for lista in pools.values()) - antes
            ja_tier = len(pecas_de_tier(conjunto_do_personagem(personagem), personagem.classe))
            extras = estimar_pacotes_max(
                pools,
                personagem.classe,
                ja_tier=ja_tier,
                max_catalisados=max_catalisados,
            )
            avisos_cat.append(
                f"Catalisador: +{gemeos} gêmeos na pool e ~{extras} pacotes de 2/4 peças."
            )
    estimativa = estimar_custo(
        pools,
        iterations=iterations,
        orcamento_segundos=orcamento_segundos,
        target_error=target_error,
        max_profilesets_rodada=max_profilesets_rodada,
        extras_profilesets=extras,
    )
    estimativa["contagens"] = resumo(pools)
    estimativa["catalisador"] = bool(catalisador)
    estimativa["extras_catalisador"] = extras
    if avisos_cat:
        estimativa["avisos"] = list(estimativa.get("avisos") or []) + avisos_cat
    return estimativa


@router.get("/heuristica")
def estimativa_heuristica(
    addon: str = Query(min_length=20, description="Saída do /simc."),
    pool: int = Query(12, ge=1, le=100),
    top: int = Query(6, ge=1, le=50),
    tipo_armadura: str | None = Query(None),
    atributo: str | None = Query(None),
) -> dict:
    """Ranking heurístico instantâneo por slot (NÃO é DPS).

    Roda sem SimC: pondera atributos secundários para mostrar, em segundos, o
    "porquê" antes de medir. O número medido continua vindo do job real.
    """
    try:
        personagem = parse_texto(addon)
    except ErroParseAddon as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tipo = tipo_armadura or tipo_armadura_da_classe(personagem.classe)
    atrib = atributo or atributo_da_classe(personagem.classe)
    pools = construir_pools(tipo_armadura=tipo, atributo=atrib, pool_por_slot=pool)
    pesos = pesos_mod.pesos_para(personagem.classe, personagem.spec)

    por_slot: dict[str, list[dict]] = {}
    for slot, candidatos in pools.items():
        pontuados = sorted(
            (
                pontuar_candidato(c, pesos.valores, fonte=pesos.fonte)
                for c in candidatos
            ),
            key=lambda p: (p.score, p.candidato.ilvl or 0),
            reverse=True,
        )
        por_slot[slot] = [
            {
                "item_id": p.candidato.item_id,
                "nome_pt": p.candidato.nome_pt,
                "nome_en": p.candidato.nome_en,
                "ilvl": p.candidato.ilvl,
                "score": round(p.score, 2),
                "breakdown": {k: round(v, 2) for k, v in p.breakdown.items()},
            }
            for p in pontuados[:top]
        ]

    return {
        "classe": personagem.classe,
        "spec": personagem.spec,
        "heuristico": True,
        "fonte_pesos": pesos.fonte,
        "por_slot": por_slot,
        "avisos": [
            "Estimativa heurística: ordena por pesos de atributos, NÃO é DPS. "
            "O valor medido vem do SimulationCraft ao rodar o job."
        ],
    }


@router.get("/{job_id}")
def consultar_topgear(job_id: str) -> dict:
    job = topgear_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    return _publico(job)


@router.post("/{job_id}/cancelar")
def cancelar_topgear(job_id: str) -> dict:
    job = topgear_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] in ("done", "error", "cancelled"):
        return {"id": job_id, "status": job["status"], "cancelado": job["status"] == "cancelled"}
    topgear_db.marcar_cancelamento(job_id)
    return {"id": job_id, "status": job["status"], "cancelado": True}


@router.get("/{job_id}/resultado")
def resultado_topgear(job_id: str) -> dict:
    job = topgear_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] != "done" or job.get("resultado") is None:
        raise HTTPException(status_code=409, detail="Resultado ainda não está pronto.")
    return job["resultado"]


@router.get("/{job_id}/perfil")
def perfil_topgear(job_id: str) -> dict:
    """Canonical ``.simc`` for the measured set (gems, enchants, folio included).

    Reusing ``linhas_override`` guarantees the exported profile reproduces the
    exact set that was simulated, instead of pasting the original addon plus
    partial overrides.
    """
    job = topgear_db.obter_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if job["status"] != "done" or job.get("resultado") is None:
        raise HTTPException(status_code=409, detail="Resultado ainda não está pronto.")

    addon = (job.get("request") or {}).get("addon") or ""
    if not addon:
        raise HTTPException(status_code=409, detail="Addon original indisponível.")

    try:
        personagem = parse_texto(addon)
        conjunto = Conjunto.model_validate(job["resultado"]["melhor"])
    except (ErroParseAddon, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    linhas = [serializar_texto(personagem, incluir_checksum=False).rstrip(), ""]
    linhas.extend(linhas_override(conjunto))
    return {"simc": "\n".join(linhas).rstrip() + "\n"}


def _nome_arquivo(job_id: str) -> str:
    """Nome estável e seguro (sem caractere que o Windows recuse)."""
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    limpo = re.sub(r"[^A-Za-z0-9_-]", "", job_id[:8]) or "job"
    return f"topgear-{limpo}-{carimbo}.simc"


@router.post("/{job_id}/perfil/salvar")
def salvar_perfil_topgear(job_id: str) -> dict:
    """Grava o ``.simc`` otimizado em ``saida/`` e devolve o caminho.

    Mesma razão do CSV do Droptimizer: a janela do app desktop (pywebview) não
    tem gerenciador de download, então o link `blob:` do botão não produzia
    arquivo nem erro.
    """
    texto = perfil_topgear(job_id)["simc"]
    pasta = PROJECT_ROOT / "saida"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = (pasta / _nome_arquivo(job_id)).resolve()
    caminho.write_text(texto, encoding="utf-8")
    return {
        "caminho": str(caminho),
        "pasta": str(caminho.parent),
        "arquivo": caminho.name,
        "linhas": texto.count("\n"),
    }
