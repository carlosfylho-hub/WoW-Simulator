"""Background processor for Top Gear jobs.

Wraps the simulator so cancellation is checked between SimulationCraft batches,
persists progress events and stores the measured result. A restart re-enqueues
pending/running jobs (basic resume; the search restarts from the base set).
"""

from __future__ import annotations

import json
import time

from .. import simc_runner as sr
from ..parser.addon import ErroParseAddon
from ..parser.combinar import combinar_textos
from ..topgear.models import TopGearRequest
from ..topgear.pools import construir_contexto, construir_pools, secoes_ausentes
from ..topgear.runner import criar_simulador, estilo_de_luta, preflight
from ..topgear.search import executar_topgear
from . import topgear_db
from .worker import registrar_fim_job, registrar_inicio_job, threads_para_job


class _Cancelado(Exception):
    pass


_TECIDO = {"warlock", "priest", "mage"}
_COURO = {"druid", "rogue", "monk", "demonhunter"}
_MALHA = {"hunter", "shaman", "evoker"}
_PLACA = {"warrior", "paladin", "deathknight"}
_FORCA = {"warrior", "paladin", "deathknight"}
_AGILIDADE = {"rogue", "hunter", "monk", "demonhunter"}


def tipo_armadura_da_classe(classe: str | None) -> str:
    """Map class to its real armor type: tecido, couro, malha or placa.

    Previously mail/plate classes silently fell back to cloth, producing pools
    with illegal armor for Hunters/Shamans/Evokers and Warriors/Paladins/DKs.
    """
    nome = (classe or "").lower()
    if nome in _PLACA:
        return "placa"
    if nome in _MALHA:
        return "malha"
    if nome in _COURO:
        return "couro"
    if nome in _TECIDO:
        return "tecido"
    return "tecido"


def atributo_da_classe(classe: str | None) -> str:
    nome = (classe or "").lower()
    if nome in _FORCA:
        return "Força"
    if nome in _AGILIDADE:
        return "Agilidade"
    return "Intelecto"


def _registrar_progresso(job_id: str, evento: dict) -> None:
    print(
        f"[topgear {job_id[:8]}] progresso: {json.dumps(evento, ensure_ascii=False)}",
        flush=True,
    )
    topgear_db.atualizar_job(
        job_id,
        progresso_json=json.dumps(evento, ensure_ascii=False),
        estado_json=json.dumps(evento, ensure_ascii=False),
    )
    if topgear_db.esta_cancelado(job_id):
        raise _Cancelado()


def processar(job_id: str) -> None:
    job = topgear_db.obter_job(job_id)
    if job is None:
        return
    if job.get("cancelado"):
        topgear_db.atualizar_job(
            job_id, status="cancelled", finished_at=topgear_db._agora()
        )
        return

    topgear_db.atualizar_job(
        job_id, status="running", started_at=topgear_db._agora()
    )
    registrar_inicio_job()
    print(f"[topgear {job_id[:8]}] iniciado", flush=True)

    try:
        pedido = TopGearRequest(**job["request"])
        personagem = combinar_textos(
            pedido.addon,
            pedido.amr,
            primario=pedido.primario,
            classe_hint=pedido.classe_hint,
            spec_hint=pedido.spec_hint,
        ).personagem
        tipo_armadura = tipo_armadura_da_classe(personagem.classe)
        atributo = atributo_da_classe(personagem.classe)

        pools = construir_pools(
            tipo_armadura=tipo_armadura,
            atributo=atributo,
            pool_por_slot=pedido.pool_por_slot,
        )
        contexto = construir_contexto(
            classe=personagem.classe,
            spec=personagem.spec,
            tipo_armadura=tipo_armadura,
        )

        # Pré-voo: descobre em segundos se o simc trava/erra neste perfil.
        pre = preflight(
            personagem,
            fight_style=estilo_de_luta(pedido.scenario),
            threads=pedido.thread or threads_para_job(),
            iterations=5,
            timeout=min(30.0, float(pedido.orcamento_segundos)),
        )
        _registrar_progresso(
            job_id,
            {
                "estagio": "pre-voo",
                # Sem DPS: 5 iterações servem para saber se o simc roda o perfil,
                # não para medir dano.
                "duracao_s": round(pre.duracao_s, 2),
            },
        )
        if not pre.ok:
            raise sr.SimcFalhou(f"Pré-voo falhou: {pre.erro}")

        inicio_busca = time.monotonic()

        def cancelado() -> bool:
            return topgear_db.esta_cancelado(job_id)

        def restante() -> float | None:
            return pedido.orcamento_segundos - (time.monotonic() - inicio_busca)

        simulador_base = criar_simulador(
            personagem,
            fight_style=estilo_de_luta(pedido.scenario),
            threads=pedido.thread or threads_para_job(),
            target_error=pedido.target_error,
            cancelar=cancelado,
            orcamento_restante=restante,
        )

        def simulador_conferindo(conjuntos, iterations):
            if cancelado():
                raise _Cancelado()
            try:
                return simulador_base(conjuntos, iterations)
            except sr.SimcCancelado as exc:
                raise _Cancelado() from exc

        resultado = executar_topgear(
            personagem,
            pools,
            simulador=simulador_conferindo,
            request=pedido,
            ctx=contexto,
            progresso=lambda evento: _registrar_progresso(job_id, evento),
        )
        resultado.avisos.extend(secoes_ausentes(tipo_armadura))

        if topgear_db.esta_cancelado(job_id):
            raise _Cancelado()

        topgear_db.atualizar_job(
            job_id,
            status="done",
            finished_at=topgear_db._agora(),
            resultado_json=json.dumps(
                resultado.model_dump(mode="json"), ensure_ascii=False
            ),
        )
        print(
            f"[topgear {job_id[:8]}] concluido: {len(resultado.rodadas)} rodadas, "
            f"{len(resultado.trocas)} trocas",
            flush=True,
        )
    except _Cancelado:
        topgear_db.atualizar_job(
            job_id,
            status="cancelled",
            finished_at=topgear_db._agora(),
        )
        print(f"[topgear {job_id[:8]}] cancelado", flush=True)
    except (ErroParseAddon, sr.SimcError, ValueError, OSError) as exc:
        topgear_db.atualizar_job(
            job_id,
            status="error",
            finished_at=topgear_db._agora(),
            erro=str(exc),
        )
        print(f"[topgear {job_id[:8]}] erro: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001 - never leave a zombie "running" job
        topgear_db.atualizar_job(
            job_id,
            status="error",
            finished_at=topgear_db._agora(),
            erro=repr(exc),
        )
        print(f"[topgear {job_id[:8]}] erro inesperado: {exc!r}", flush=True)
    finally:
        registrar_fim_job()
