"""Catalisador: converte itens dos slots de tier na peça de tier da classe.

Regra de jogo (Season 2, registrada em ``dados/season2_context.json``): o
Catalisador troca o item pela peça de tier do spec **sem mudar trilha nem nível
de aprimoramento**, e preserva os stats base do item original. No SimC isso é a
peça de tier (``id=<tier>``) com ``redirected_base_stats=<item original>``, o
mesmo formato que o addon exporta para peças já catalisadas.

O valor do tier vem do bônus de 2/4 peças, que o SimC calcula sozinho pelo
``id_set`` do item. Uma peça isolada vale o mesmo que a original; por isso há
dois mecanismos complementares:

* **gêmeos** na pool: cada candidato de um slot de tier ganha uma versão
  catalisada, medida no contexto do conjunto atual (cobre "falta 1 peça");
* **pacotes**: combinações de 2 e 4 peças a partir do melhor conjunto (cobre
  "tenho 0 ou 1 peça"), onde nenhuma troca isolada mostraria ganho.

Nada aqui estima dano: só gera candidatos e conjuntos para o SimC medir.
"""

from __future__ import annotations

import itertools
from typing import Iterable, Mapping

from ..data import catalog, tier
from ..models import Personagem
from .models import Candidato, Conjunto, ContextoSpec

SLOTS_TIER = tier.SLOTS_TIER
# Bônus do tier set existem em 2 e 4 peças.
ALVOS_PECAS = (2, 4)


def gemeo_catalisado(origem: Candidato, classe: str | None) -> Candidato | None:
    """Versão catalisada de ``origem``, ou ``None`` se não for conversível.

    Não converte: peça que já é de tier, peça já catalisada, item sem id, slot
    sem tier ou craftado (a conversão de itens fabricados não é confirmada nos
    dados do projeto, então fica de fora em vez de arriscar um resultado falso).
    """
    conjunto = tier.conjunto_da_classe(classe)
    if conjunto is None or origem.slot not in conjunto.slots:
        return None
    if origem.item_id is None or origem.item_id in conjunto.ids:
        return None
    if origem.catalisado or origem.craftado:
        return None

    id_tier = conjunto.item_do_slot(origem.slot)
    if id_tier is None:
        return None

    nomes_tier = catalog.nome_item(id_tier)
    nome_tier = nomes_tier.nome_pt or nomes_tier.nome_en or conjunto.nomes_en.get(origem.slot)
    nome_origem = origem.nome_pt or origem.nome_en or f"item {origem.item_id}"
    return origem.model_copy(
        update={
            "item_id": id_tier,
            "redirected_base_stats": origem.item_id,
            "fonte": f"catalisador:{origem.fonte}",
            "nome_pt": f"{nome_tier} (catalisado de {nome_origem})" if nome_tier else None,
            "nome_en": nomes_tier.nome_en,
            # Os stats exibidos e usados na poda são os do item de origem.
            "stats": origem.stats or catalog.stats_item(origem.item_id) or None,
            "icone": None,
        }
    )


def adicionar_gemeos(
    pools: Mapping[str, list[Candidato]], classe: str | None
) -> dict[str, list[Candidato]]:
    """Pools com a versão catalisada de cada candidato dos slots de tier."""
    saida: dict[str, list[Candidato]] = {}
    for slot, candidatos in pools.items():
        lista = list(candidatos)
        if slot in SLOTS_TIER:
            vistos = {
                (c.item_id, c.redirected_base_stats, c.ilvl, tuple(c.bonus_ids))
                for c in lista
            }
            for candidato in candidatos:
                gemeo = gemeo_catalisado(candidato, classe)
                if gemeo is None:
                    continue
                chave = (
                    gemeo.item_id,
                    gemeo.redirected_base_stats,
                    gemeo.ilvl,
                    tuple(gemeo.bonus_ids),
                )
                if chave in vistos:
                    continue
                vistos.add(chave)
                lista.append(gemeo)
        saida[slot] = lista
    return saida


def pecas_de_tier(conjunto: Conjunto, classe: str | None) -> list[str]:
    """Slots do conjunto que já têm peça de tier da classe."""
    ids = tier.ids_tier(classe)
    return [slot for slot in SLOTS_TIER if conjunto.item_id(slot) in ids]


def contexto_com_catalisador(
    ctx: ContextoSpec,
    personagem: Personagem,
    classe: str | None,
    max_catalisados: int | None,
) -> ContextoSpec:
    """Contexto com ids de tier, peças já catalisadas e o teto de cargas."""
    equipados = {
        (item.item_id, item.redirected_base_stats)
        for item in personagem.equipado.values()
        if item.item_id is not None and item.redirected_base_stats
    }
    return ctx.model_copy(
        update={
            "tier_ids": set(ctx.tier_ids) | set(tier.ids_tier(classe)),
            "max_catalisados": max_catalisados,
            "catalisados_equipados": set(ctx.catalisados_equipados) | equipados,
        }
    )


def pacotes_de_tier(
    melhor: Conjunto,
    classe: str | None,
    travados: Iterable[str] = (),
    *,
    alvos: Iterable[int] = ALVOS_PECAS,
) -> dict[str, Conjunto]:
    """Conjuntos que completam 2 e 4 peças catalisando os itens atuais.

    Parte do melhor conjunto: para cada alvo, escolhe quais slots catalisar
    (todas as combinações) usando o item que já está equipado ali como origem.
    Como o Catalisador preserva os stats, o item de maior valor por slot continua
    sendo a melhor origem. Combinações acima do teto de cargas são descartadas
    depois, pelo validador.
    """
    if tier.conjunto_da_classe(classe) is None:
        return {}
    travados = set(travados)
    ja_tier = pecas_de_tier(melhor, classe)

    elegiveis: dict[str, Candidato] = {}
    for slot in SLOTS_TIER:
        if slot in travados or slot in ja_tier:
            continue
        origem = melhor.itens.get(slot)
        if origem is None:
            continue
        gemeo = gemeo_catalisado(origem, classe)
        if gemeo is not None:
            elegiveis[slot] = gemeo

    pacotes: dict[str, Conjunto] = {}
    for alvo in sorted(set(alvos)):
        faltam = alvo - len(ja_tier)
        if faltam <= 0 or faltam > len(elegiveis):
            continue
        for combo in itertools.combinations(sorted(elegiveis), faltam):
            conjunto = melhor
            for slot in combo:
                conjunto = conjunto.com_troca(slot, elegiveis[slot])
            pacotes[f"cat{alvo}pc_{'-'.join(combo)}"] = conjunto
    return pacotes
