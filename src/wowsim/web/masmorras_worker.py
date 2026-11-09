"""Background processor for the M+ dungeon ranking jobs.

Reaproveita o parser (SimC/AMR), o pré-voo e o motor ``masmorras.avaliar``.
Exceções inesperadas nunca deixam o job em ``running``. O pré-voo não publica
DPS (A-02): 5 iterações só confirmam que o simc roda o perfil.
"""

from __future__ import annotations

import json
import time
from collections import Counter

from .. import simc_runner as sr
from ..data import catalog
from ..data.classes import atributo_da_classe, tipo_armadura_da_classe
from ..masmorras.avaliar import agrupar, ordenar, rodar_ranking
from ..masmorras.catalogo import elegivel, itens_por_masmorra
from ..masmorras.modelos import ItemRanking, MasmorraRanking, RankingRequest, RankingResult
from ..parser.addon import ErroParseAddon
from ..parser.combinar import combinar_textos
from ..topgear.runner import estilo_de_luta, preflight
from . import masmorras_db
from .worker import registrar_fim_job, registrar_inicio_job, threads_para_job


class _Cancelado(Exception):
    pass


def _registrar_progresso(job_id: str, evento: dict) -> None:
    print(
        f"[masmorras {job_id[:8]}] progresso: {json.dumps(evento, ensure_ascii=False)}",
        flush=True,
    )
    masmorras_db.atualizar_job(
        job_id, progresso_json=json.dumps(evento, ensure_ascii=False)
    )
    if masmorras_db.esta_cancelado(job_id):
        raise _Cancelado()


def _explicacao(direto: int, catalisar: int) -> str:
    partes: list[str] = []
    if direto:
        partes.append(f"{direto} item(ns) são upgrade direto")
    if catalisar:
        partes.append(
            f"{catalisar} servem para catalisar: valem pelo tier, não pelos atributos"
        )
    if not partes:
        return "Nenhum item medido é upgrade para o seu conjunto atual."
    return ". ".join(partes) + "."


def _item_ranking(avaliacao, ilvl: int) -> ItemRanking:
    nomes = catalog.nome_item(avaliacao.item.item_id)
    visual = catalog.visual_item(avaliacao.item.item_id)
    return ItemRanking(
        item_id=avaliacao.item.item_id,
        nome_pt=avaliacao.item.nome_pt or nomes.nome_pt,
        nome_en=nomes.nome_en,
        slot=avaliacao.item.slot,
        ilvl=ilvl,
        etiqueta=avaliacao.etiqueta,
        delta_cru_pct=round(avaliacao.delta_cru, 3),
        delta_catalisado_pct=(
            round(avaliacao.delta_cat, 3) if avaliacao.delta_cat is not None else None
        ),
        limiar_pct=round(avaliacao.limiar_cru, 3),
        icone=visual.get("icone"),
        stats=visual.get("stats"),
    )


def _masmorra_ranking(linha: dict, ilvl: int) -> MasmorraRanking:
    elegiveis = linha["elegiveis"]
    chance = (100.0 * linha["servem"] / elegiveis) if elegiveis else 0.0
    return MasmorraRanking(
        masmorra=linha["masmorra"],
        servem=linha["servem"],
        elegiveis=elegiveis,
        chance_pct=round(chance, 1),
        maior_pct=round(linha["maior"], 3),
        direto=linha["direto"],
        catalisar=linha["catalisar"],
        explicacao=_explicacao(linha["direto"], linha["catalisar"]),
        itens=[_item_ranking(a, ilvl) for a in linha["itens"]],
    )


def processar(job_id: str) -> None:
    job = masmorras_db.obter_job(job_id)
    if job is None:
        return
    if job.get("cancelado"):
        masmorras_db.atualizar_job(
            job_id, status="cancelled", finished_at=masmorras_db._agora()
        )
        return

    masmorras_db.atualizar_job(job_id, status="running", started_at=masmorras_db._agora())
    registrar_inicio_job()
    print(f"[masmorras {job_id[:8]}] iniciado", flush=True)

    try:
        pedido = RankingRequest(**job["request"])
        combo = combinar_textos(
            pedido.addon,
            pedido.amr,
            primario=pedido.primario,
            incluir_inv=True,
        )
        personagem = combo.personagem
        tipo = tipo_armadura_da_classe(personagem.classe)
        atributo = atributo_da_classe(personagem.classe)
        elegiveis_itens = [
            item
            for item in itens_por_masmorra()
            if elegivel(item, tipo_armadura=tipo, atributo=atributo)
        ]
        contagem_elegiveis = Counter(item.masmorra for item in elegiveis_itens)

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
                # Sem DPS: 5 iterações só confirmam que o simc roda o perfil.
                "duracao_s": round(pre.duracao_s, 2),
            },
        )
        if not pre.ok:
            raise sr.SimcFalhou(f"Pré-voo falhou: {pre.erro}")

        inicio = time.monotonic()

        def cancelado() -> bool:
            return masmorras_db.esta_cancelado(job_id)

        def restante() -> float | None:
            return pedido.orcamento_segundos - (time.monotonic() - inicio)

        base_out: dict = {}
        avaliacoes = rodar_ranking(
            personagem,
            elegiveis_itens,
            cenario=pedido.scenario,
            ilvl=pedido.ilvl,
            it_triagem=pedido.iteracoes_triagem,
            it_refino=pedido.iteracoes_refino,
            threads=threads_para_job(),
            cancelar=cancelado,
            orcamento_restante=restante,
            base_out=base_out,
        )
        if masmorras_db.esta_cancelado(job_id):
            raise _Cancelado()

        linhas = ordenar(agrupar(avaliacoes, dict(contagem_elegiveis)), por="quantidade")
        avisos = [
            a.detalhe
            for a in combo.avisos
            if a.severidade != "info" or a.codigo == "combinar_inv_mesclado"
        ]
        resultado = RankingResult(
            base_dps=float(base_out.get("base_dps") or 0.0),
            cenario=pedido.scenario,
            ilvl=pedido.ilvl,
            iteracoes=pedido.iteracoes_refino,
            masmorras=[_masmorra_ranking(linha, pedido.ilvl) for linha in linhas],
            avisos=avisos,
        )

        masmorras_db.atualizar_job(
            job_id,
            status="done",
            finished_at=masmorras_db._agora(),
            resultado_json=json.dumps(resultado.model_dump(mode="json"), ensure_ascii=False),
        )
        print(
            f"[masmorras {job_id[:8]}] concluido: base={resultado.base_dps:.0f} dps, "
            f"{len(resultado.masmorras)} masmorras",
            flush=True,
        )
    except _Cancelado:
        masmorras_db.atualizar_job(
            job_id, status="cancelled", finished_at=masmorras_db._agora()
        )
        print(f"[masmorras {job_id[:8]}] cancelado", flush=True)
    except (ErroParseAddon, sr.SimcError, ValueError, OSError) as exc:
        masmorras_db.atualizar_job(
            job_id, status="error", finished_at=masmorras_db._agora(), erro=str(exc)
        )
        print(f"[masmorras {job_id[:8]}] erro: {exc}", flush=True)
    except Exception as exc:  # noqa: BLE001 - nunca deixar job zumbi
        masmorras_db.atualizar_job(
            job_id, status="error", finished_at=masmorras_db._agora(), erro=repr(exc)
        )
        print(f"[masmorras {job_id[:8]}] erro inesperado: {exc!r}", flush=True)
    finally:
        registrar_fim_job()
