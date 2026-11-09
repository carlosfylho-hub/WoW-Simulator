"""Background worker for the optional web interface.

Concurrency is cores - 1. Each job gets a share of the cores so two jobs do not
oversubscribe the machine.
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import simc_runner as sr
from ..gen import profilesets
from ..llm.summary import montar_contexto
from ..parser.addon import ErroParseAddon, parse_texto
from ..report import render
from . import db, drop_db, masmorras_db, perfil_store, topgear_db

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAIDA_DIR = PROJECT_ROOT / "saida" / "web"

NUCLEOS = os.cpu_count() or 2
WORKERS = max(1, NUCLEOS - 1)
# Mantido para o worker legado; Drop/Top Gear usam threads_para_job().
THREADS_POR_JOB = max(1, NUCLEOS // WORKERS)

# Limita quantas simulações pesadas (simc) rodam ao mesmo tempo. Em desktop o
# padrão é 1: a fila garante que cada job receba núcleos-1 threads sem saturar.
VAGAS_SIMULACAO = max(1, int(os.environ.get("WOWSIM_SIM_VAGAS", "1")))
_vagas = threading.Semaphore(VAGAS_SIMULACAO)

_ativos = 0
_ativos_lock = threading.Lock()


def registrar_inicio_job() -> None:
    """Reserva uma vaga de simulação e marca o job como ativo."""
    _vagas.acquire()
    global _ativos
    with _ativos_lock:
        _ativos += 1


def registrar_fim_job() -> None:
    global _ativos
    with _ativos_lock:
        _ativos = max(0, _ativos - 1)
    _vagas.release()


def threads_para_job() -> int:
    """Divide os núcleos entre os jobs ativos: um job sozinho usa quase tudo."""
    with _ativos_lock:
        ativos = max(1, _ativos)
    return max(1, (NUCLEOS - 1) // ativos)

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def iniciar() -> None:
    global _executor
    with _lock:
        if _executor is not None:
            return
        db.init_db()
        perfil_store.init_db()
        topgear_db.init_db()
        drop_db.init_db()
        masmorras_db.init_db()
        _executor = ThreadPoolExecutor(
            max_workers=WORKERS, thread_name_prefix="wowsim"
        )
    for job_id in db.jobs_pendentes():
        enfileirar(job_id)
    for job_id in topgear_db.jobs_pendentes():
        enfileirar_topgear(job_id)
    for job_id in drop_db.jobs_pendentes():
        enfileirar_drop(job_id)
    for job_id in masmorras_db.jobs_pendentes():
        enfileirar_masmorras(job_id)


def enfileirar(job_id: str) -> None:
    with _lock:
        if _executor is None:
            raise RuntimeError("O worker não foi iniciado.")
        _executor.submit(processar, job_id)


def enfileirar_topgear(job_id: str) -> None:
    from . import topgear_worker

    with _lock:
        if _executor is None:
            raise RuntimeError("O worker não foi iniciado.")
        _executor.submit(topgear_worker.processar, job_id)


def enfileirar_drop(job_id: str) -> None:
    from . import drop_worker

    with _lock:
        if _executor is None:
            raise RuntimeError("O worker não foi iniciado.")
        _executor.submit(drop_worker.processar, job_id)


def enfileirar_masmorras(job_id: str) -> None:
    from . import masmorras_worker

    with _lock:
        if _executor is None:
            raise RuntimeError("O worker não foi iniciado.")
        _executor.submit(masmorras_worker.processar, job_id)


def encerrar() -> None:
    global _executor
    with _lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=True, cancel_futures=False)


def processar(job_id: str) -> None:
    """Process one job synchronously. Exceptions become status=error."""
    job = db.obter_job(job_id)
    if job is None:
        return
    db.atualizar_job(
        job_id,
        status="running",
        started_at=db._agora(),  # noqa: SLF001 - same package
    )
    registrar_inicio_job()
    print(f"[sim {job_id[:8]}] iniciado", flush=True)

    try:
        personagem = parse_texto(job["addon_text"])
        variacoes = profilesets.gerar(
            personagem,
            de_bonus=12846,
            para_bonus=12854,
            nivel_berloque=341,
            max_variacoes=int(job["max_variacoes"]),
        )
        pasta = SAIDA_DIR / job_id
        arquivo = profilesets.escrever_arquivo(
            personagem, variacoes, pasta / "lote.simc"
        )
        execucao = sr.run_simc(
            arquivo,
            iterations=int(job["iterations"]),
            fight_style="DungeonSlice",
            threads=threads_para_job(),
        )
        resultado = sr.read_results(execucao.json_path)
        if resultado.base is None:
            raise ValueError("O simc não devolveu DPS da base.")

        caminho_md, caminho_html = render(
            personagem,
            resultado,
            variacoes,
            destino=pasta,
            iterations=int(job["iterations"]),
            fight_style="DungeonSlice",
        )
        contexto = montar_contexto(
            resultado,
            variacoes,
            iterations=int(job["iterations"]),
            fight_style="DungeonSlice",
        )
        db.atualizar_job(
            job_id,
            status="done",
            finished_at=db._agora(),  # noqa: SLF001
            resultado_json=json.dumps(contexto, ensure_ascii=False),
            relatorio_md=str(caminho_md),
            relatorio_html=str(caminho_html),
        )
    except (ErroParseAddon, sr.SimcError, ValueError, OSError) as exc:
        db.atualizar_job(
            job_id,
            status="error",
            finished_at=db._agora(),  # noqa: SLF001
            erro=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - nunca deixar job zumbi em "running"
        db.atualizar_job(
            job_id,
            status="error",
            finished_at=db._agora(),  # noqa: SLF001
            erro=repr(exc),
        )
        print(f"[sim {job_id[:8]}] erro: {exc!r}", flush=True)
    finally:
        registrar_fim_job()
