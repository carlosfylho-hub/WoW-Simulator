"""Modo Craft: qual peça craftar (item + missiva) e qual embelezamento usar.

Tudo é medido pelo simc (P1): o item craftado entra com ``ilevel=331`` (Mítico
qualidade 5), ``crafted_stats=a/b`` (o par da missiva) e, na 2ª fase,
``embellishment=<token>`` (``item_t::decode_embellishment``). P4: cada leitura
usa a própria base. Custo por peça: 80 Brasões Míticos (confirmado pelo usuário
em 2026-11-09) + 2 Centelhas de Marés (4 em arma de 2 mãos).
Desenho em docs/WORKFLOW-IMPLEMENTACAO.md §8B (T22).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations

from ..data import catalog
from ..topgear.constraints import validar
from ..topgear.models import Candidato, Conjunto, ContextoSpec
from ..topgear.runner import LeituraSim
from .avaliar import LIMIAR_PCT, Avaliacao, Opcao, avaliar, itens_para_refinar
from .catalogo import ItemDeMasmorra

ILVL_CRAFT = 331
BRASOES_CRAFT = 80
CENTELHAS = 2
MASMORRA_CRAFT = "Craft"

# IDs de atributo do simc para crafted_stats (stat_e: crit 32, haste 36, vers 40, mastery 49).
ID_STAT = {"crit": 32, "haste": 36, "versatility": 40, "mastery": 49}
NOME_STAT = {"crit": "Crítico", "haste": "Aceleração", "versatility": "Versatilidade", "mastery": "Maestria"}
PARES = [tuple(sorted(p)) for p in combinations(ID_STAT, 2)]  # 6 pares

# Listas do craft_receitas_s2.json por tipo de armadura; acessórios valem para todos.
_LISTAS_ARMADURA = {
    "tecido": [("alfaiataria", "armaduras_tecido"), ("alfaiataria", "capas")],
    "couro": [("couraria", "armaduras_couro"), ("alfaiataria", "capas")],
    "malha": [("couraria", "armaduras_malha"), ("alfaiataria", "capas")],
    "placa": [("ferraria", "armaduras_placa"), ("alfaiataria", "capas")],
}
_LISTAS_ACESSORIOS = [("joalheria", "aneis"), ("joalheria", "pescocos")]
SLOTS_ARMADURA = {"head", "shoulder", "chest", "wrist", "hands", "waist", "legs", "feet", "back"}
SLOTS_ACESSORIO = {"neck", "finger"}
SLOTS_DUPLOS = {"finger": ("finger1", "finger2")}


@dataclass(frozen=True)
class ItemCraft:
    item_id: int
    nome_pt: str | None
    nome_en: str | None
    slot: str                 # interno: head, finger, back...
    embutido: bool            # já vem com embelezamento (não aceita outro)


@dataclass(frozen=True)
class Embelezamento:
    reagente_id: int
    nome_pt: str | None
    nome_en: str
    token_simc: str
    alvo: str | None
    descricao: str | None
    # Bônus que o item equipado carrega quando este embelezamento foi aplicado
    # (``bonus_id`` de dados/derivados/embelezamentos.json). Permite reconhecer,
    # no export do SimC, qual reagente já está em uso (P-052).
    bonus_id: int | None = None


def _construir(e: dict) -> Embelezamento:
    return Embelezamento(
        e["reagente_id"],
        e.get("nome_pt"),
        e["nome_en"],
        e["token_simc"],
        e.get("alvo"),
        e.get("descricao"),
        e.get("bonus_id"),
    )


@lru_cache(maxsize=1)
def embelezamentos() -> tuple[Embelezamento, ...]:
    """Embelezamentos que o simc conhece (dados/derivados/embelezamentos.json)."""
    dados = catalog._derivado("embelezamentos.json").get("embelezamentos", [])
    return tuple(
        _construir(e) for e in dados if e.get("alvo")
    )


def embelezamentos_com_bonus() -> tuple[Embelezamento, ...]:
    """Todos os embelezamentos com ``bonus_id`` (inclusive alvo=None, de engenharia)."""
    dados = catalog._derivado("embelezamentos.json").get("embelezamentos", [])
    return tuple(_construir(e) for e in dados if e.get("bonus_id") is not None)


def _cabe(emb: Embelezamento, slot: str) -> bool:
    grupo = "finger" if slot.startswith("finger") else slot
    if emb.alvo == "qualquer":
        return True
    if emb.alvo in ("armadura", "arma_ou_armadura"):
        return grupo in SLOTS_ARMADURA
    if emb.alvo == "acessorio":
        return grupo in SLOTS_ACESSORIO
    return False  # "arma": o modo Craft não monta armas


def itens_craftaveis(tipo_armadura: str | None) -> list[ItemCraft]:
    """Peças craftáveis com id para o tipo de armadura, mais anéis e colar."""
    receitas = catalog._dados("craft_receitas_s2.json").get("receitas", {})
    listas = _LISTAS_ARMADURA.get(tipo_armadura or "", []) + _LISTAS_ACESSORIOS
    embutidos = {
        r["item_id"]: r for r in __import__("wowsim.data.embellishments", fromlist=["x"]).listar_craftados()
    }
    saida: dict[tuple[int, str], ItemCraft] = {}
    for prof, chave in listas:
        for item in receitas.get(prof, {}).get(chave, []) or []:
            item_id = item.get("id")
            if not item_id or "competitor" in (item.get("nome_en") or "").lower():
                continue  # sem id não dá para simular; PvP fica de fora
            slot = catalog.normalizar_slot(item.get("slot"))
            if slot is None:
                continue
            slot = "finger" if slot in ("finger1", "finger2") else slot
            if slot not in SLOTS_ARMADURA | SLOTS_ACESSORIO:
                continue
            emb = embutidos.get(item_id, {})
            saida[(item_id, slot)] = ItemCraft(
                int(item_id), item.get("nome_pt") or emb.get("nome_pt"), item.get("nome_en"),
                slot, bool(emb.get("embutido")),
            )
    return sorted(saida.values(), key=lambda i: (i.slot, i.item_id))


def _nome(item_id: int, slot: str, par: tuple[str, str], emb: str | None = None) -> str:
    return f"f_{item_id}_{slot}_{par[0]}_{par[1]}" + (f"_e_{emb}" if emb else "")


def candidato(item: ItemCraft, slot: str, par: tuple[str, str], emb: Embelezamento | None = None) -> Candidato:
    return Candidato(
        slot=slot,
        item_id=item.item_id,
        ilvl=ILVL_CRAFT,
        ilevel=ILVL_CRAFT,
        crafted_stats=[ID_STAT[par[0]], ID_STAT[par[1]]],
        embelezamento_simc=emb.token_simc if emb else None,
        embelezamento=item.embutido or emb is not None,
        craftado=True,
        fonte="craft",
        nome_pt=item.nome_pt,
        nome_en=item.nome_en,
    )


def montar_opcoes_craft(
    base: Conjunto, itens: list[ItemCraft]
) -> tuple[
    dict[str, Conjunto],
    dict[str, Opcao],
    dict[str, tuple[ItemCraft, tuple[str, str], str]],
]:
    """Cada peça × cada par de secundários, em cada slot onde cabe."""
    conjuntos: dict[str, Conjunto] = {}
    opcoes: dict[str, Opcao] = {}
    meta: dict[str, tuple[ItemCraft, tuple[str, str], str]] = {}
    for item in itens:
        dm = ItemDeMasmorra(item.item_id, item.nome_pt, item.slot, MASMORRA_CRAFT, "craft", None)
        for slot in SLOTS_DUPLOS.get(item.slot, (item.slot,)):
            for par in PARES:
                nome = _nome(item.item_id, slot, par)
                conjuntos[nome] = base.com_troca(slot, candidato(item, slot, par))
                opcoes[nome] = Opcao(nome, dm, slot, False, ilvl=ILVL_CRAFT)
                meta[nome] = (item, par, slot)
    return conjuntos, opcoes, meta


@dataclass
class ResultadoCraft:
    base_dps: float | None
    pecas: list[dict] = field(default_factory=list)
    embelezamentos: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    # Peças (por slot) que estourariam o teto de 2 embelezamentos e por isso não
    # foram medidas. Vão para a tela como "para usar, troque um embelezado".
    bloqueados: list[dict] = field(default_factory=list)


def _par_texto(par: tuple[str, str]) -> str:
    return f"{NOME_STAT[par[0]]} + {NOME_STAT[par[1]]}"


def _agrupar_bloqueados(
    itens_bloqueados: list[tuple[str, list[str]]],
    meta_original: dict[str, tuple[ItemCraft, tuple[str, str], str]],
    base: Conjunto,
) -> list[dict]:
    """Uma linha por (item, slot) que estouraria o teto de embelezamentos (P-049)."""
    from .embelezados import embelezados_do_conjunto

    atuais = embelezados_do_conjunto(base)
    slots_atuais = ", ".join(a.slot for a in atuais) or "nenhum"
    agrupado: dict[tuple[int, str], dict] = {}
    for nome, motivos in itens_bloqueados:
        item, _par, slot = meta_original[nome]
        chave = (item.item_id, slot)
        if chave in agrupado:
            continue
        if item.embutido:
            motivo = (
                "Peça já vem com embelezamento embutido e somaria um 3º efeito; "
                f"para usar, troque um dos seus embelezados ({slots_atuais})."
            )
        else:
            motivo = "; ".join(motivos)
        agrupado[chave] = {
            "slot": slot,
            "item_id": item.item_id,
            "nome_pt": item.nome_pt,
            "nome_en": item.nome_en,
            "embutido": item.embutido,
            "motivo": motivo,
        }
    return sorted(agrupado.values(), key=lambda b: (b["slot"], b["item_id"]))


def trocar_embelezamento(base: Conjunto, atual, novo: Embelezamento) -> Conjunto:
    """Troca o reagente de um embelezado atual pelo ``novo`` no mesmo slot (P-050)."""
    candidato_atual = base.itens[atual.slot]
    bonus = [
        b
        for b in (candidato_atual.bonus_ids or [])
        if not (atual.aplicado is not None and b == atual.aplicado.bonus_id)
    ]
    novo_item = candidato_atual.model_copy(
        update={
            "bonus_ids": bonus,
            "embelezamento_simc": novo.token_simc,
            "embelezamento": True,
        }
    )
    return base.com_troca(atual.slot, novo_item)


def rodar_craft(
    base: Conjunto,
    itens: list[ItemCraft],
    *,
    ctx: ContextoSpec,
    simular,
    it_triagem: int,
    it_refino: int,
    max_refino: int = 24,
    sondar=None,
) -> ResultadoCraft:
    """Fase 1: melhor peça+missiva por slot. Fase 2: cada embelezamento no melhor slot onde cabe."""
    conjuntos, opcoes, meta = montar_opcoes_craft(base, itens)
    if not conjuntos:
        return ResultadoCraft(None, avisos=["Nenhuma peça craftável com dados para o seu tipo de armadura."])

    # P-049: a fase 1 mede no simc, que NÃO impõe o limite de 2 embelezamentos.
    # Valida cada conjunto ANTES de simular; o que estoura o teto não entra no
    # ranking (senão o ganho medido inclui um 3º efeito que o jogo desliga).
    meta_original = dict(meta)
    validos: dict[str, Conjunto] = {}
    bloqueados_itens: list[tuple[str, list[str]]] = []
    for nome, conjunto_c in conjuntos.items():
        ok, motivos = validar(conjunto_c, ctx)
        if ok:
            validos[nome] = conjunto_c
        else:
            bloqueados_itens.append((nome, motivos))
    conjuntos = validos
    opcoes = {n: opcoes[n] for n in validos}
    meta = {n: meta[n] for n in validos}
    bloqueados = _agrupar_bloqueados(bloqueados_itens, meta_original, base)
    if not conjuntos:
        return ResultadoCraft(
            None,
            bloqueados=bloqueados,
            avisos=[
                "Nenhuma peça craftável pode ser medida sem estourar o limite de 2 embelezamentos."
            ],
        )

    leitura = simular(conjuntos, it_triagem)
    triagem = avaliar(leitura, opcoes)
    vivos = itens_para_refinar(triagem, max_refino)
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    avaliacoes: list[Avaliacao] = triagem
    base_dps = leitura.base_dps
    if nomes:
        leitura = simular({n: conjuntos[n] for n in nomes}, it_refino)
        refino = avaliar(leitura, {n: opcoes[n] for n in nomes})
        base_dps = leitura.base_dps or base_dps
        refinados = {a.item.item_id for a in refino}
        avaliacoes = refino + [a for a in triagem if a.item.item_id not in refinados]

    # Melhor peça por slot (avaliar já escolhe o melhor par de cada item).
    melhor_por_slot: dict[str, tuple[Avaliacao, ItemCraft, tuple[str, str], str]] = {}
    # Melhor peça NÃO embutida por slot: é ela que recebe um embelezamento novo,
    # porque a embutida já consome um dos 2 efeitos (P-050).
    melhor_nao_embutido: dict[str, tuple[Avaliacao, ItemCraft, tuple[str, str], str]] = {}
    for a in avaliacoes:
        item, par, _slot = meta[a.nome_cru]
        atual = melhor_por_slot.get(a.slot)
        if atual is None or a.delta_cru > atual[0].delta_cru:
            melhor_por_slot[a.slot] = (a, item, par, a.nome_cru)
        if not item.embutido:
            sem_emb = melhor_nao_embutido.get(a.slot)
            if sem_emb is None or a.delta_cru > sem_emb[0].delta_cru:
                melhor_nao_embutido[a.slot] = (a, item, par, a.nome_cru)

    pecas = [
        {
            "slot": slot,
            "item_id": item.item_id,
            "nome_pt": item.nome_pt,
            "nome_en": item.nome_en,
            "missiva": _par_texto(par),
            "secundarios": [par[0], par[1]],
            "ganho_pct": round(a.delta_cru, 3),
            "limiar_pct": round(a.limiar_cru, 3),
            "serve": a.delta_cru > a.limiar_cru,
            "embutido": item.embutido,
            "ilvl": ILVL_CRAFT,
        }
        for slot, (a, item, par, _) in sorted(melhor_por_slot.items(), key=lambda kv: -kv[1][0].delta_cru)
    ]

    # P-051 (A4): atributos reais da peça craftada, lidos do simc (players[i].gear).
    # É só para a tooltip; nunca entra em cálculo de DPS. Falha da sonda não
    # derruba o ranking — a tooltip apenas fica sem os atributos.
    if sondar is not None and pecas:
        alvo = {
            f"{slot}_{item.item_id}": candidato(item, slot, par)
            for slot, (_a, item, par, _nome) in melhor_por_slot.items()
        }
        try:
            stats_por_peca = sondar(alvo) or {}
        except Exception:  # noqa: BLE001 - sonda é opcional/visual
            stats_por_peca = {}
        for p in pecas:
            p["stats"] = stats_por_peca.get(f"{p['slot']}_{p['item_id']}")

    # Fase 2 — embelezamentos, sempre respeitando o teto de 2 (P-050):
    #  * ainda há espaço: aplica E na melhor peça não embutida que o aceita;
    #  * no teto, com reagente aplicado: TROCA o reagente atual por E no mesmo slot
    #    (a contagem continua igual);
    #  * no teto só com embutidos: troca a peça embutida por uma craftada com E.
    from .embelezados import embelezados_do_conjunto

    avisos: list[str] = []
    fase2: dict[str, Conjunto] = {}
    # nome -> (emb, slot, tipo, ref_sem_emb | None, nome_do_atual)
    por_emb: dict[str, tuple[Embelezamento, str, str, str | None, str | None]] = {}
    embelezados = embelezados_do_conjunto(base)
    no_teto = len(embelezados) >= ctx.max_embelezamentos

    for emb in embelezamentos():
        if no_teto:
            aplicados = [
                a for a in embelezados
                if a.aplicado is not None and not a.embutido and _cabe(emb, a.slot)
            ]
            embutidos = [a for a in embelezados if a.embutido and _cabe(emb, a.slot)]
            mediu = False
            # (a) trocar o reagente de um embelezado aplicado (total não sobe).
            for atual in aplicados:
                if atual.aplicado.reagente_id == emb.reagente_id:
                    continue  # já é este embelezamento
                conjunto = trocar_embelezamento(base, atual, emb)
                ok, _motivos = validar(conjunto, ctx)
                if not ok:
                    continue
                nome = f"swap_{emb.token_simc}_{atual.slot}"
                fase2[nome] = conjunto
                por_emb[nome] = (emb, atual.slot, "troca", None, atual.aplicado.nome_pt)
                mediu = True
            # (b) no teto só com embutidos: substitui a peça embutida inteira.
            if not mediu:
                for atual in embutidos:
                    melhor = melhor_nao_embutido.get(atual.slot)
                    if melhor is None:
                        continue
                    _a, item, par, _nome_melhor = melhor
                    conjunto = base.com_troca(
                        atual.slot, candidato(item, atual.slot, par, emb)
                    )
                    ok, _motivos = validar(conjunto, ctx)
                    if not ok:
                        continue
                    nome = f"peca_{emb.token_simc}_{atual.slot}"
                    fase2[nome] = conjunto
                    por_emb[nome] = (emb, atual.slot, "peca", None, str(atual.item_id))
                    mediu = True
            if not mediu and not aplicados and not embutidos:
                avisos.append(
                    f"{emb.nome_pt or emb.nome_en}: não medido "
                    "(o limite de 2 embelezamentos já está cheio)."
                )
            continue

        # (c) ainda há espaço: aplica E na melhor peça não embutida que o aceita.
        alvo = next(
            (
                (slot, nome)
                for slot, (a, item, par, nome) in sorted(melhor_nao_embutido.items(), key=lambda kv: -kv[1][0].delta_cru)
                if _cabe(emb, slot)
            ),
            None,
        )
        if alvo is None:
            continue
        slot, nome_sem = alvo
        item, par, _slot = meta[nome_sem]
        conjunto = base.com_troca(slot, candidato(item, slot, par, emb))
        ok, motivos = validar(conjunto, ctx)
        if not ok:
            avisos.append(f"{emb.nome_pt or emb.nome_en}: não medido ({'; '.join(motivos)})")
            continue
        nome = _nome(item.item_id, slot, par, emb.token_simc)
        fase2[nome] = conjunto
        fase2[nome_sem] = conjuntos[nome_sem]  # a mesma peça sem embelezamento, NA MESMA leitura (P4)
        por_emb[nome] = (emb, slot, "adicionar", nome_sem, None)

    embs: list[dict] = []
    if fase2:
        leitura2 = simular(fase2, it_refino)
        base2 = leitura2.base_dps
        for nome, (emb, slot, tipo, ref, atual_nome) in por_emb.items():
            com = leitura2.resultados.get(nome)
            if not base2 or com is None:
                continue
            if tipo == "adicionar":
                referencia = leitura2.resultados.get(ref) if ref else None
                if referencia is None:
                    continue
                erros_ref = [leitura2.erros.get(nome), leitura2.erros.get(ref)]
            else:  # troca/peça: compara com a base da mesma leitura (P4)
                referencia = base2
                erros_ref = [leitura2.erros.get(nome), leitura2.base_erro]
            erro = max(
                [LIMIAR_PCT, *(abs(e) for e in erros_ref if e is not None)]
            )
            embs.append(
                {
                    "nome_pt": emb.nome_pt,
                    "nome_en": emb.nome_en,
                    "descricao": emb.descricao,
                    "reagente_id": emb.reagente_id,
                    "slot_medido": slot,
                    "tipo": tipo,
                    "troca_de": atual_nome,
                    "ganho_pct": round(100.0 * (com - referencia) / base2, 3),
                    "ganho_total_pct": round(100.0 * (com - base2) / base2, 3),
                    "limiar_pct": round(erro, 3),
                }
            )
        embs.sort(key=lambda e: -e["ganho_pct"])
    return ResultadoCraft(base_dps, pecas, embs, avisos, bloqueados)
