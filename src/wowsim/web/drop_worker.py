"""Background processor for Droptimizer jobs.

Reaproveita o parser (SimC/AMR), o construtor de simulador e o chunking do Top
Gear. Exceções inesperadas nunca deixam o job em ``running``.
"""

from __future__ import annotations

import json
import time

from .. import simc_runner as sr
from ..data import catalog
from ..droptimizer import (
    DropRequest,
    agrupar_por_slot,
    deduplicar,
    executar_droptimizer,
    possuidos_da_mochila,
)
from ..parser.addon import ErroParseAddon
from ..parser.combinar import combinar_textos
from ..topgear.pools import construir_contexto, construir_pools
from ..topgear.runner import criar_simulador, estilo_de_luta, preflight
from . import drop_db
from .topgear_worker import atributo_da_classe, tipo_armadura_da_classe
from .worker import registrar_fim_job, registrar_inicio_job, threads_para_job


class _Cancelado(Exception):
    pass


def _registrar_progresso(job_id: str, evento: dict) -> None:
    print(
        f"[drop {job_id[:8]}] progresso: {json.dumps(evento, ensure_ascii=False)}",
        flush=True,
    )
    drop_db.atualizar_job(
        job_id, progresso_json=json.dumps(evento, ensure_ascii=False)
    )
    if drop_db.esta_cancelado(job_id):
        raise _Cancelado()


def _identidade(slot: str, item_id: int | None, bonus_ids) -> tuple:
    return (slot, item_id, tuple(sorted(bonus_ids or ())))


def _possuidos(personagem) -> list:
    # A mochila já inclui ``Gear from Bags`` (SimC) e o ``.inv`` AMR (via combinar).
    # Remove possuídos que coincidem com o equipado (o ``.inv`` mistura os dois).
    equipados = {
        _identidade(slot, item.item_id, item.bonus_ids)
        for slot, item in personagem.equipado.items()
        if item.item_id is not None
    }
    filtrados = [
        item
        for item in possuidos_da_mochila(personagem)
        if _identidade(item.slot, item.item_id, item.bonus_ids) not in equipados
    ]
    return deduplicar(filtrados)


def _ilvl_referencia(item) -> int | None:
    if item.ilvl_comentario is not None:
        return item.ilvl_comentario
    try:
        return catalog.ilvl_do_item(item)
    except Exception:  # noqa: BLE001 - catálogo pode não conhecer o item
        return None


def _candidatos(pedido: DropRequest, personagem, possuidos) -> dict:
    if pedido.modo in ("best_in_bags", "worst_in_bags"):
        return agrupar_por_slot(possuidos)

    # upgrade: pools de catálogo. Compara por (slot, item_id) contra equipado e
    # possuído; só exclui um candidato de mesmo item_id que NÃO supera o ilvl
    # possuído (a trilha superior do mesmo item é um upgrade legítimo — P0-01).
    tipo = tipo_armadura_da_classe(personagem.classe)
    atributo = atributo_da_classe(personagem.classe)
    pools = construir_pools(
        tipo_armadura=tipo, atributo=atributo, pool_por_slot=pedido.pool_por_slot
    )

    referencia: dict[tuple[str, int], int] = {}

    def _registrar(slot: str, item_id: int | None, ilvl: int | None) -> None:
        if item_id is None or ilvl is None:
            return
        chave = (slot, item_id)
        referencia[chave] = max(referencia.get(chave, 0), ilvl)

    for slot, item in personagem.equipado.items():
        _registrar(slot, item.item_id, _ilvl_referencia(item))
    for item in possuidos:
        _registrar(item.slot, item.item_id, item.ilvl)

    saida: dict = {}
    for slot, candidatos in pools.items():
        filtrados = []
        for cand in candidatos:
            if cand.item_id is None:
                continue
            ref = referencia.get((slot, cand.item_id))
            if ref is not None and (cand.ilvl is None or cand.ilvl <= ref):
                # Mesmo item já possuído/equipado sem superar ilvl: não é upgrade.
                continue
            filtrados.append(cand)
        if filtrados:
            saida[slot] = filtrados
    return saida


def processar(job_id: str) -> None:
    job = drop_db.obter_job(job_id)
    if job is None:
        return
    if job.get("cancelado"):
        drop_db.atualizar_job(
            job_id, status="cancelled", finished_at=drop_db._agora()
        )
        return

    drop_db.atualizar_job(job_id, status="running", started_at=drop_db._agora())
    registrar_inicio_job()
    print(f"[drop {job_id[:8]}] iniciado", flush=True)

    try:
        pedido = DropRequest(**job["request"])
        combo = combinar_textos(
            pedido.addon,
            pedido.amr,
            primario=pedido.primario,
            classe_hint=pedido.classe_hint,
            spec_hint=pedido.spec_hint,
            incluir_inv=pedido.incluir_inv,
        )
        personagem = combo.personagem
        possuidos = _possuidos(personagem)
        candidatos = _candidatos(pedido, personagem, possuidos)
        tipo = tipo_armadura_da_classe(personagem.classe)
        contexto = construir_contexto(
            classe=personagem.classe, spec=personagem.spec, tipo_armadura=tipo
        )

        pre = preflight(
            personagem,
            fight_style=estilo_de_luta(pedido.scenario),
            threads=threads_para_job(),
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
            return drop_db.esta_cancelado(job_id)

        def restante() -> float | None:
            return pedido.orcamento_segundos - (time.monotonic() - inicio_busca)

        simulador_base = criar_simulador(
            personagem,
            fight_style=estilo_de_luta(pedido.scenario),
            threads=threads_para_job(),
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

        resultado = executar_droptimizer(
            personagem,
            candidatos,
            simulador=simulador_conferindo,
            request=pedido,
            ctx=contexto,
            progresso=lambda evento: _registrar_progresso(job_id, evento),
        )
        resultado.avisos.extend(
            a.detalhe
            for a in combo.avisos
            if a.severidade != "info" or a.codigo == "combinar_inv_mesclado"
        )
        resultado.avisos.extend(_avisos_possuidos(pedido, possuidos))

        if drop_db.esta_cancelado(job_id):
            raise _Cancelado()

        drop_db.atualizar_job(
            job_id,
            status="done",
            finished_at=drop_db._agora(),
            resultado_json=json.dumps(resultado.model_dump(mode="json"), ensure_ascii=False),
        )
        print(
            f"[drop {job_id[:8]}] concluido: base={resultado.base_dps:.0f} dps, "
            f"{len(resultado.itens)} itens",
            flush=True,
        )
    except _Cancelado:
        drop_db.atualizar_job(
            job_id, status="cancelled", finished_at=drop_db._agora()
        )
        print(f"[drop {job_id[:8]}] cancelado", flush=True)
    except (ErroParseAddon, sr.SimcError, ValueError, OSError) as exc:
        drop_db.atualizar_job(
            job_id, status="error", finished_at=drop_db._agora(), erro=str(exc)
        )
        print(f"[drop {job_id[:8]}] erro: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001 - nunca deixar job zumbi
        drop_db.atualizar_job(
            job_id, status="error", finished_at=drop_db._agora(), erro=repr(exc)
        )
        print(f"[drop {job_id[:8]}] erro inesperado: {exc!r}", flush=True)
    finally:
        registrar_fim_job()


def _avisos_possuidos(pedido: DropRequest, possuidos) -> list[str]:
    if pedido.modo in ("best_in_bags", "worst_in_bags") and not possuidos:
        return [
            "Nenhum item possuído encontrado; use um export com bolsas "
            "(Gear from Bags) ou um AMR com .inv."
        ]
    return []
