"""Background processor for the M+ dungeon ranking jobs.

Reaproveita o parser (SimC/AMR), o pré-voo e o motor ``masmorras.avaliar``.
Exceções inesperadas nunca deixam o job em ``running``. O pré-voo não publica
DPS (A-02): 5 iterações só confirmam que o simc roda o perfil.

Com ``loadouts`` no pedido (T9) cada build é medida contra a própria referência
``ref`` (P4), o conjunto montado passa por uma execução de confirmação e o
ranking das masmorras usa a média ponderada das builds. Com ``medir_pesos``
(T11) cada build ganha a sua escala do Pawn, medida pelo simc.
"""

from __future__ import annotations

import json
import time
from collections import Counter

from .. import simc_runner as sr
from ..data import catalog
from ..data import trilhas
from ..data.classes import atributo_da_classe, tipo_armadura_da_classe
from ..data.pesos_medidos import medir_escala
from ..exportar.pawn import escalas_das_builds
from ..masmorras.avaliar import agrupar, montar_opcoes, ordenar, rodar_ranking
from ..masmorras.builds import (
    ResultadoBuild,
    avaliacoes_medias,
    cenario_da_build,
    matriz_builds,
    pesos_normalizados,
    rodar_build,
)
from ..masmorras.catalogo import elegivel, itens_por_masmorra
from ..masmorras.tier import plano_tier
from ..data import regras
from ..data.regras import marcas_por_slot
from ..masmorras.craft import (
    BRASOES_CRAFT,
    CENTELHAS,
    CENTELHAS_DUAS_MAOS,
    MOEDA_CRAFT,
    itens_craftaveis,
    nivel_craft,
    rodar_craft,
)
from ..masmorras.sonda import sondar_atributos
from ..masmorras.cofre import (
    MASMORRA_COFRE,
    montar_opcoes_cofre,
    opcoes_do_cofre,
    rodar_ranking_cofre,
)
from ..masmorras.modelos import (
    BuildResultado,
    ItemRanking,
    LinhaMatriz,
    MasmorraRanking,
    RankingRequest,
    RankingResult,
    TrocaBuild,
)
from ..parser.addon import ErroParseAddon
from ..parser.amr import parse_amr
from ..parser.combinar import combinar_textos
from ..topgear.catalisador import contexto_com_catalisador
from ..topgear.pools import construir_contexto
from ..topgear.runner import criar_simulador, estilo_de_luta, preflight
from ..topgear.search import conjunto_do_personagem
from . import masmorras_db
from .worker import registrar_fim_job, registrar_inicio_job, threads_para_job

BUILD_ATUAL = "Atual"


def _mensagem_orcamento(minutos: float) -> str:
    """Erro de tempo esgotado em linguagem de gente (o comando do simc fica no log)."""
    return (
        f"O tempo máximo ({minutos:.0f} min) acabou antes do fim. Aumente o tempo máximo em "
        "\"Mais opções\", marque menos builds ou reduza as iterações."
    )


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


def _degrau_do_item(item_id: int, nivel: dict) -> trilhas.Degrau | None:
    """Cofre: pelos bônus reais do item; masmorras: o nível do pedido."""
    bonus = nivel.get("por_item", {}).get(item_id)
    if bonus is not None:
        return trilhas.degrau_dos_bonus(bonus)
    return nivel.get("padrao")


def _item_ranking(avaliacao, nivel: dict) -> ItemRanking:
    d = _degrau_do_item(avaliacao.item.item_id, nivel)
    if d is not None and avaliacao.item.item_id not in nivel.get("por_item", {}):
        d = trilhas.degrau_no_slot(d, avaliacao.slot)
    ilvl = d.ilvl if d is not None else nivel["padrao"].ilvl
    nomes = catalog.nome_item(avaliacao.item.item_id)
    visual = catalog.visual_item(avaliacao.item.item_id)
    return ItemRanking(
        item_id=avaliacao.item.item_id,
        nome_pt=avaliacao.item.nome_pt or nomes.nome_pt,
        nome_en=nomes.nome_en,
        slot=avaliacao.item.slot,
        ilvl=avaliacao.ilvl if avaliacao.ilvl is not None else ilvl,
        etiqueta=avaliacao.etiqueta,
        delta_cru_pct=round(avaliacao.delta_cru, 3),
        delta_catalisado_pct=(
            round(avaliacao.delta_cat, 3) if avaliacao.delta_cat is not None else None
        ),
        limiar_pct=round(avaliacao.limiar_cru, 3),
        icone=visual.get("icone"),
        stats=visual.get("stats"),
        degrau=d.rotulo if d else None,
        upgrade=trilhas.custo_upgrade(d, slot=avaliacao.slot, marcas=nivel.get("marcas")),
    )


def _com_plano_tier(masmorras: list[MasmorraRanking], plano: dict | None) -> list[MasmorraRanking]:
    """Com tier forçado, as masmorras que dão peças do melhor plano vêm primeiro."""
    contagem = (plano or {}).get("masmorras_do_plano") or {}
    if not contagem:
        return masmorras
    for m in masmorras:
        m.pecas_tier = int(contagem.get(m.masmorra, 0))
    return sorted(masmorras, key=lambda m: -m.pecas_tier)  # estável: mantém a ordem dentro do grupo


def _masmorra_ranking(linha: dict, nivel: dict) -> MasmorraRanking:
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
        itens=[_item_ranking(a, nivel) for a in linha["itens"]],
    )


def builds_do_pedido(personagem, nomes: list[str]) -> dict[str, str | None]:
    """Nome da build -> import string. ``Atual`` = talentos do export."""
    saida: dict[str, str | None] = {}
    for nome in nomes:
        if nome == BUILD_ATUAL:
            saida[nome] = personagem.talents_atual
        elif nome in personagem.loadouts:
            saida[nome] = personagem.loadouts[nome]
        else:
            raise ValueError(
                f"A build {nome!r} não está no export do SimC (loadouts salvos)."
            )
    return saida


def _troca(slot: str, ganho: float, candidato) -> TrocaBuild:
    d = trilhas.degrau_dos_bonus(candidato.bonus_ids or ([candidato.bonus_id] if candidato.bonus_id else []))
    nomes = catalog.nome_item(candidato.item_id) if candidato.item_id else None
    visual = catalog.visual_item(candidato.item_id) if candidato.item_id else {}
    return TrocaBuild(
        slot=slot,
        item_id=candidato.item_id,
        nome_pt=candidato.nome_pt or (nomes.nome_pt if nomes else None),
        nome_en=candidato.nome_en or (nomes.nome_en if nomes else None),
        ilvl=candidato.ilvl,
        catalisado=candidato.catalisado,
        ganho_pct=round(ganho, 3),
        icone=visual.get("icone"),
        stats=visual.get("stats") or None,
        degrau=d.rotulo if d else None,
        upgrade=trilhas.custo_upgrade(d),
    )


def _build_resultado(r: ResultadoBuild) -> BuildResultado:
    return BuildResultado(
        nome=r.nome,
        cenario=r.cenario,
        ref_dps=r.ref_dps,
        delta_conjunto_pct=(
            round(r.delta_conjunto, 3) if r.delta_conjunto is not None else None
        ),
        limiar_conjunto_pct=(
            round(r.limiar_conjunto, 3) if r.limiar_conjunto is not None else None
        ),
        trocas=(trocas := [_troca(slot, ganho, cand) for slot, ganho, cand in r.trocas]),
        brasoes=_somar_brasoes(trocas),
        conjunto_itens=[
            cand.model_dump(mode="json", exclude_none=True)
            for cand in r.conjunto.itens.values()
            if cand.item_id is not None
        ],
        avisos=r.avisos,
    )


def _somar_brasoes(trocas: list[TrocaBuild]) -> dict[str, int]:
    total: dict[str, int] = {}
    for t in trocas:
        if t.upgrade and t.upgrade.get("brasoes"):
            total[t.upgrade["moeda"]] = total.get(t.upgrade["moeda"], 0) + int(t.upgrade["brasoes"])
    return total


def _linha_matriz(linha: dict) -> LinhaMatriz:
    item = linha["item"]
    nomes = catalog.nome_item(item.item_id)
    visual = catalog.visual_item(item.item_id)
    return LinhaMatriz(
        item_id=item.item_id,
        nome_pt=item.nome_pt or nomes.nome_pt,
        nome_en=nomes.nome_en,
        masmorra=item.masmorra,
        slot=item.slot,
        icone=visual.get("icone"),
        stats=visual.get("stats") or None,
        deltas={b: round(v, 3) for b, v in linha["deltas"].items()},
        limiares={b: round(v, 3) for b, v in linha["limiares"].items()},
        etiquetas=linha["etiquetas"],
        media_pct=round(linha["media_pct"], 3),
        divergente=linha["divergente"],
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
        builds = builds_do_pedido(personagem, pedido.loadouts)
        nivel_pedido = pedido.degrau()
        nivel: dict = {
            "padrao": nivel_pedido,
            "por_item": {},
            "marcas": marcas_por_slot(personagem.slot_high_watermarks),
        }
        importacao = None
        elegiveis_itens: list = []
        if pedido.modo == "masmorras":
            elegiveis_itens = [
                item
                for item in itens_por_masmorra()
                if elegivel(item, tipo_armadura=tipo, atributo=atributo)
            ]
            contagem_elegiveis = Counter(item.masmorra for item in elegiveis_itens)
        elif pedido.modo == "craft":
            contagem_elegiveis = Counter()
        else:
            amr_texto = (pedido.amr or "").strip()
            if not amr_texto and (pedido.addon or "").strip().startswith("$"):
                amr_texto = pedido.addon.strip()
            if not amr_texto:
                raise ValueError(
                    "O Grande Cofre exige um export do AskMrRobot com o .gv."
                )
            importacao = parse_amr(amr_texto)
            itens_cofre = [op for op in opcoes_do_cofre(importacao) if op["slots"]]
            if not itens_cofre:  # V-1
                raise ValueError(
                    "O export do AMR não traz opções do Grande Cofre. O cofre só abre depois do "
                    "reset semanal (terça): abra o cofre no jogo, faça um novo export no addon do "
                    "AMR e cole no Perfil."
                )
            nivel["por_item"] = {op["item_id"]: op["bonus_ids"] for op in itens_cofre}
            contagem_elegiveis = Counter({MASMORRA_COFRE: len(itens_cofre)})

        if not personagem.talents_atual:
            # Perfil só do AMR: sem talentos o simc roda uma spec "pelada" e o DPS
            # sai dezenas de vezes menor (ex.: 3 mil em vez de 140 mil) — inútil.
            raise ValueError(
                "O perfil não tem talentos: ele veio só do AMR. Para simular, cole no Perfil o "
                "export do addon SimulationCraft (/simc no jogo); o AMR fica como complemento "
                "(Grande Cofre e itens na bolsa)."
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
        resultados_build: list[ResultadoBuild] = []
        avisos_execucao: list[str] = []
        if any("does not support fight style" in a for a in getattr(pre, "avisos", ())):
            avisos_execucao.append(
                f"O próprio SimulationCraft avisa que a sua spec ({personagem.spec or '?'}) não "
                f"tem suporte ao cenário {estilo_de_luta(pedido.scenario)}: os números podem não "
                "ser confiáveis. Compare com o cenário Patchwerk (chefe único) antes de decidir."
            )
        resultado_craft = None
        if pedido.modo == "craft":
            # T22: peça + missiva por slot e embelezamentos, medidos pelo simc.
            if builds:
                avisos_execucao.append("O modo Craft mede só a build atual (as builds marcadas foram ignoradas).")
                builds = {}
            ctx_craft = contexto_com_catalisador(
                construir_contexto(classe=personagem.classe, spec=personagem.spec, tipo_armadura=tipo),
                personagem, personagem.classe, pedido.max_catalisados,
            )
            # A mão secundária que o personagem JÁ usa (ex.: lanterna craftada) é
            # válida com uma arma de 1 mão craftada; a lista padrão só tem drops de M+.
            oh_atual = conjunto_do_personagem(personagem).item_id("off_hand")
            if oh_atual is not None:
                ctx_craft = ctx_craft.model_copy(update={"offs_validos": {*ctx_craft.offs_validos, oh_atual}})
            _registrar_progresso(job_id, {"estagio": "craft: peças e missivas"})
            ilvl_craft = nivel_craft(pedido.trilha_craft)
            resultado_craft = rodar_craft(
                conjunto_do_personagem(personagem),
                itens_craftaveis(tipo, personagem.classe),
                ilvl=ilvl_craft,
                ctx=ctx_craft,
                simular=criar_simulador(
                    personagem,
                    fight_style=estilo_de_luta(pedido.scenario),
                    threads=threads_para_job(),
                    cancelar=cancelado,
                    orcamento_restante=restante,
                ),
                it_triagem=pedido.iteracoes_triagem,
                it_refino=pedido.iteracoes_refino,
                max_refino=pedido.max_refino,
                # Sonda curta de atributos (P-051/A4) só se ainda houver folga
                # de orçamento; é visual e não entra em cálculo de DPS.
                sondar=(
                    (
                        lambda candidatos: sondar_atributos(
                            personagem,
                            candidatos,
                            fight_style=estilo_de_luta(pedido.scenario),
                        )
                    )
                    if (restante() or 0) > 20
                    else None
                ),
            )
            base_out["base_dps"] = resultado_craft.base_dps
            avaliacoes = []
        elif builds:
            # T9: uma medição por build, cada uma contra o próprio ``ref`` (P4).
            base = conjunto_do_personagem(personagem)
            if pedido.modo == "cofre":
                conjuntos, opcoes = montar_opcoes_cofre(
                    base, importacao, classe=personagem.classe
                )
            else:
                conjuntos, opcoes = montar_opcoes(
                    base, elegiveis_itens, ilvl=nivel_pedido.ilvl, classe=personagem.classe,
                    bonus=nivel_pedido.bonus_id,
                )
            ctx = contexto_com_catalisador(
                construir_contexto(
                    classe=personagem.classe, spec=personagem.spec, tipo_armadura=tipo
                ),
                personagem,
                personagem.classe,
                pedido.max_catalisados,
            )
            for posicao, (nome, codigo) in enumerate(builds.items(), start=1):
                cenario = pedido.cenarios_loadouts.get(nome) or cenario_da_build(nome)
                _registrar_progresso(
                    job_id,
                    {"estagio": f"build {posicao}/{len(builds)}: {nome}", "cenario": cenario},
                )
                simular = criar_simulador(
                    personagem,
                    fight_style=estilo_de_luta(cenario),
                    threads=threads_para_job(),
                    cancelar=cancelado,
                    orcamento_restante=restante,
                )
                try:
                    resultados_build.append(
                        rodar_build(
                            base, conjuntos, opcoes,
                            nome=nome, codigo=codigo, cenario=cenario, ctx=ctx,
                            simular=simular,
                            it_triagem=pedido.iteracoes_triagem,
                            it_refino=pedido.iteracoes_refino,
                            max_refino=pedido.max_refino,
                        )
                    )
                except sr.SimcOrcamentoEsgotado:
                    if not resultados_build:
                        raise
                    # Guarda o que já foi medido em vez de perder tudo.
                    feitas = ", ".join(r.nome for r in resultados_build)
                    faltaram = ", ".join(list(builds)[posicao - 1:])
                    avisos_execucao.append(
                        f"O tempo máximo acabou: resultado só com {feitas}; ficaram de fora {faltaram}."
                    )
                    break
            por_build = {r.nome: r.avaliacoes for r in resultados_build}
            avaliacoes = avaliacoes_medias(por_build, pedido.pesos_loadouts)
            base_out["base_dps"] = resultados_build[0].ref_dps
        elif pedido.modo == "cofre":
            avaliacoes = rodar_ranking_cofre(
                personagem,
                importacao,
                cenario=pedido.scenario,
                it_triagem=pedido.iteracoes_triagem,
                it_refino=pedido.iteracoes_refino,
                threads=threads_para_job(),
                cancelar=cancelado,
                orcamento_restante=restante,
                base_out=base_out,
                max_refino=pedido.max_refino,
            )
        else:
            avaliacoes = rodar_ranking(
                personagem,
                elegiveis_itens,
                cenario=pedido.scenario,
                ilvl=nivel_pedido.ilvl,
                bonus=nivel_pedido.bonus_id,
                it_triagem=pedido.iteracoes_triagem,
                it_refino=pedido.iteracoes_refino,
                threads=threads_para_job(),
                cancelar=cancelado,
                orcamento_restante=restante,
                base_out=base_out,
                max_refino=pedido.max_refino,
            )
        if masmorras_db.esta_cancelado(job_id):
            raise _Cancelado()

        # T23: forçar tier set — melhor plano de 4 peças, medido junto (bônus de conjunto incluso).
        plano_tier_saida = None
        if pedido.forcar_tier and pedido.modo == "masmorras":
            _registrar_progresso(job_id, {"estagio": "tier set: combinações de 4 peças"})
            plano_tier_saida = plano_tier(
                conjunto_do_personagem(personagem),
                avaliacoes,
                classe=personagem.classe,
                degrau=trilhas.degrau(pedido.trilha_tier, pedido.rank_tier),
                simular=criar_simulador(
                    personagem,
                    fight_style=estilo_de_luta(pedido.scenario),
                    threads=threads_para_job(),
                    cancelar=cancelado,
                    orcamento_restante=restante,
                ),
                iteracoes=pedido.iteracoes_refino,
                max_catalisados=pedido.max_catalisados,
            )
            if builds:
                avisos_execucao.append(
                    "O plano de tier set foi medido com os talentos atuais e o cenário principal (não por build)."
                )

        # T11: escala do Pawn por build (ou da build atual, sem loadouts).
        pawn: dict = {"builds": {}, "mistura": None, "iguais": []}
        if pedido.medir_pesos and (restante() or 0) < 30:
            avisos_execucao.append("Escala do Pawn não medida: o tempo máximo acabou antes.")
        elif pedido.medir_pesos:
            alvos = [(r.nome, r.codigo, r.cenario) for r in resultados_build] or [
                (BUILD_ATUAL, personagem.talents_atual, pedido.scenario)
            ]
            medicoes = {}
            for nome, codigo, cenario in alvos:
                _registrar_progresso(
                    job_id,
                    {"estagio": f"escala do Pawn: {nome}", "iteracoes": pedido.iteracoes_pesos},
                )
                medicoes[nome] = medir_escala(
                    personagem,
                    talentos=codigo,
                    fight_style=estilo_de_luta(cenario),
                    iterations=pedido.iteracoes_pesos,
                    threads=threads_para_job(),
                    timeout=max(1.0, restante() or 1.0),
                    cancelar=cancelado,
                )
            pawn = escalas_das_builds(
                medicoes,
                pedido.pesos_loadouts,
                personagem=personagem.nome or "WSIM",
                classe=personagem.classe,
                spec=personagem.spec,
            )

        linhas = ordenar(agrupar(avaliacoes, dict(contagem_elegiveis)), por="quantidade")
        # P-053: o .inv mesclado é informação, não alerta. Vai para um campo
        # próprio (texto secundário na tela), fora da lista âmbar de avisos.
        informacoes = [
            a.detalhe
            for a in combo.avisos
            if a.severidade == "info" or a.codigo == "combinar_inv_mesclado"
        ]
        avisos = [
            a.detalhe
            for a in combo.avisos
            if a.severidade != "info" and a.codigo != "combinar_inv_mesclado"
        ]
        avisos.extend(avisos_execucao)
        builds_saida = [_build_resultado(r) for r in resultados_build]
        for b in builds_saida:
            escala = pawn["builds"].get(b.nome)
            if escala:
                b.pawn = escala["string"]
                b.pawn_pesos = escala["pesos_pct_por_ponto"]
        concluidas = [r.nome for r in resultados_build]
        pesos_builds = (
            pesos_normalizados(concluidas, pedido.pesos_loadouts) if concluidas else {}
        )
        if concluidas:
            avisos.append(
                "Ranking pela média ponderada das builds: "
                + ", ".join(f"{b} {round(100 * w)}%" for b, w in pesos_builds.items())
                + "."
            )
        matriz = (
            [
                _linha_matriz(linha)
                for linha in matriz_builds(
                    {r.nome: r.avaliacoes for r in resultados_build},
                    pedido.pesos_loadouts,
                )
            ]
            if resultados_build
            else []
        )
        craft_saida = None
        if resultado_craft is not None:
            plano_pecas = []
            if resultado_craft.plano:
                for linha in [resultado_craft.plano.get("melhor") or {}, *resultado_craft.plano.get("alternativas", [])]:
                    plano_pecas += linha.get("pecas", [])
            for peca in [*resultado_craft.pecas, *plano_pecas]:
                visual = catalog.visual_item(peca["item_id"])
                peca["icone"] = visual.get("icone")
            craft_saida = {
                "pecas": resultado_craft.pecas,
                "embelezamentos": resultado_craft.embelezamentos,
                "bloqueados": resultado_craft.bloqueados,
                "plano": resultado_craft.plano,
                "custo": {
                    "ilvl": ilvl_craft,
                    "nivel": f"{'Herói' if pedido.trilha_craft == 'heroi' else 'Mítico'} qualidade 5",
                    "brasoes": int(regras.craft().get("brasoes") or BRASOES_CRAFT),
                    "moeda": MOEDA_CRAFT[pedido.trilha_craft],
                    "centelhas": CENTELHAS,
                    "nota": (
                        f"Por peça. Arma de 2 mãos usa {CENTELHAS_DUAS_MAOS} Centelhas de Marés. "
                        "Armas craftadas também aceitam a Forja do Veneno depois "
                        f"({'318→325' if pedido.trilha_craft == 'heroi' else '331→337'})."
                    ),
                },
                "limite_embelezamentos": "Único-equipado: Embelezado (2) — no máximo 2 efeitos ativos.",
                "avisos": resultado_craft.avisos,
            }
        resultado = RankingResult(
            craft=craft_saida,
            base_dps=float(base_out.get("base_dps") or 0.0),
            cenario=pedido.scenario,
            ilvl=nivel_pedido.ilvl,
            nivel=nivel_pedido.rotulo if pedido.modo == "masmorras" else None,
            iteracoes=pedido.iteracoes_refino,
            masmorras=_com_plano_tier([_masmorra_ranking(linha, nivel) for linha in linhas], plano_tier_saida),
            tier=plano_tier_saida,
            avisos=avisos,
            informacoes=informacoes,
            builds=builds_saida,
            matriz=matriz,
            pesos_builds=pesos_builds,
            pawn_atual=(
                (pawn["builds"].get(BUILD_ATUAL) or {}).get("string")
                if not resultados_build
                else None
            ),
            pawn_mistura=pawn["mistura"],
            pawn_iguais=pawn["iguais"],
        )

        masmorras_db.atualizar_job(
            job_id,
            status="done",
            finished_at=masmorras_db._agora(),
            resultado_json=json.dumps(resultado.model_dump(mode="json"), ensure_ascii=False),
        )
        print(
            f"[masmorras {job_id[:8]}] concluido: base={resultado.base_dps:.0f} dps, "
            f"{len(resultado.masmorras)} masmorras, {len(builds_saida)} builds",
            flush=True,
        )
    except _Cancelado:
        masmorras_db.atualizar_job(
            job_id, status="cancelled", finished_at=masmorras_db._agora()
        )
        print(f"[masmorras {job_id[:8]}] cancelado", flush=True)
    except sr.SimcOrcamentoEsgotado as exc:
        print(f"[masmorras {job_id[:8]}] erro: {exc}", flush=True)  # comando completo só no log
        minutos = float(job["request"].get("orcamento_segundos") or 900) / 60
        masmorras_db.atualizar_job(
            job_id, status="error", finished_at=masmorras_db._agora(),
            erro=_mensagem_orcamento(minutos),
        )
    except (ErroParseAddon, sr.SimcError, ValueError, OSError) as exc:
        if isinstance(exc, sr.SimcCancelado) or masmorras_db.esta_cancelado(job_id):
            masmorras_db.atualizar_job(
                job_id, status="cancelled", finished_at=masmorras_db._agora()
            )
            print(f"[masmorras {job_id[:8]}] cancelado", flush=True)
        else:
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
