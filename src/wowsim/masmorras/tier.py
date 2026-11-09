"""Forçar tier set (T23): o melhor conjunto de 4 peças de tier a partir das masmorras.

Depois do ranking normal, para cada slot de tier que o personagem ainda não usa
escolhe a melhor fonte (item de masmorra que o Catalisador converte naquele
slot, pelo ``delta_cat`` já medido), refaz o gêmeo no nível pedido para o tier
(``trilha_tier``/``rank_tier``) e mede **juntas, numa leitura** (P4) todas as
combinações que deixam o conjunto com 4 peças. O bônus de 2 e 4 peças entra no
número porque o simc simula o conjunto inteiro. Desenho: workflow T23.
"""

from __future__ import annotations

from itertools import combinations
from typing import Callable, Mapping

from ..data import tier as dados_tier
from ..data.trilhas import Degrau
from ..topgear.catalisador import gemeo_catalisado
from ..topgear.models import Candidato, Conjunto
from ..topgear.runner import LeituraSim
from ..topgear.search import _limiar_por_erro
from .avaliar import LIMIAR_PCT, Avaliacao

PECAS_ALVO = 4
Simulador = Callable[[Mapping[str, Conjunto], int], LeituraSim]


def _fontes_por_slot(avaliacoes: list[Avaliacao], slots: set[str]) -> dict[str, Avaliacao]:
    """Melhor item de masmorra por slot de tier, pelo ganho catalisado medido."""
    melhor: dict[str, Avaliacao] = {}
    for a in avaliacoes:
        if a.item.slot not in slots or a.delta_cat is None:
            continue
        atual = melhor.get(a.item.slot)
        if atual is None or a.delta_cat > (atual.delta_cat or float("-inf")):
            melhor[a.item.slot] = a
    return melhor


def _peca_tier(a: Avaliacao, slot: str, degrau: Degrau, classe: str | None) -> Candidato | None:
    cru = Candidato(
        slot=slot,
        item_id=a.item.item_id,
        bonus_id=degrau.bonus_id,
        bonus_ids=[degrau.bonus_id],
        ilvl=degrau.ilvl,
        fonte=f"mplus:{a.item.masmorra}",
        nome_pt=a.item.nome_pt,
    )
    return gemeo_catalisado(cru, classe)


def plano_tier(
    base: Conjunto,
    avaliacoes: list[Avaliacao],
    *,
    classe: str | None,
    degrau: Degrau,
    simular: Simulador,
    iteracoes: int,
) -> dict:
    """Combinações de 4 peças de tier, medidas no simc. Nunca levanta por falta de dado."""
    conjunto = dados_tier.conjunto_da_classe(classe)
    if conjunto is None:
        return {"disponivel": False, "motivo": "Sem dados de tier set para a sua classe."}

    slots = set(conjunto.slots)
    ids = conjunto.ids
    ja_tem = sorted(s for s in slots if base.item_id(s) in ids)
    faltam = PECAS_ALVO - len(ja_tem)
    saida: dict = {
        "disponivel": True,
        "nivel": f"{degrau.rotulo} ({degrau.ilvl})",
        "ja_equipadas": ja_tem,
        "faltam": max(0, faltam),
        "combinacoes": [],
        "melhor": None,
        "masmorras_do_plano": {},
        "sem_fonte": [],
    }
    if faltam <= 0:
        saida["motivo"] = "Você já usa 4 ou mais peças de tier."
        return saida

    fontes = _fontes_por_slot(avaliacoes, slots - set(ja_tem))
    saida["sem_fonte"] = sorted(slots - set(ja_tem) - set(fontes))
    if len(fontes) < faltam:
        saida["motivo"] = (
            f"Faltam {faltam} peça(s), mas só {len(fontes)} slot(s) de tier têm item de masmorra "
            "que o Catalisador converte."
        )
        return saida

    conjuntos: dict[str, Conjunto] = {}
    detalhes: dict[str, list[dict]] = {}
    for combo in combinations(sorted(fontes), faltam):
        conj = base
        pecas: list[dict] = []
        for slot in combo:
            a = fontes[slot]
            peca = _peca_tier(a, slot, degrau, classe)
            if peca is None:
                break
            conj = conj.com_troca(slot, peca)
            pecas.append(
                {
                    "slot": slot,
                    "item_tier": peca.item_id,
                    "nome_tier": peca.nome_pt,
                    "fonte_item_id": a.item.item_id,
                    "fonte_nome": a.item.nome_pt,
                    "masmorra": a.item.masmorra,
                }
            )
        else:
            nome = "tier_" + "_".join(combo)
            conjuntos[nome] = conj
            detalhes[nome] = pecas

    if not conjuntos:
        saida["motivo"] = "Nenhuma combinação pôde ser montada."
        return saida

    leitura = simular(conjuntos, iteracoes)
    base_dps = leitura.base_dps
    for nome, pecas in detalhes.items():
        dps = leitura.resultados.get(nome)
        if not base_dps or dps is None:
            continue
        saida["combinacoes"].append(
            {
                "slots": [p["slot"] for p in pecas],
                "pecas": pecas,
                "conversoes": len(pecas),  # cargas do Catalisador necessárias
                "ganho_pct": round(100.0 * (dps - base_dps) / base_dps, 3),
                "limiar_pct": round(
                    _limiar_por_erro(LIMIAR_PCT, leitura.base_erro, leitura.erros.get(nome)), 3
                ),
            }
        )
    saida["combinacoes"].sort(key=lambda c: -c["ganho_pct"])
    if saida["combinacoes"]:
        melhor = saida["combinacoes"][0]
        saida["melhor"] = melhor
        contagem: dict[str, int] = {}
        for p in melhor["pecas"]:
            contagem[p["masmorra"]] = contagem.get(p["masmorra"], 0) + 1
        saida["masmorras_do_plano"] = contagem
    return saida
