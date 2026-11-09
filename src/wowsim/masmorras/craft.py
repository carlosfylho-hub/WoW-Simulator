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
CENTELHAS_DUAS_MAOS = 4
MASMORRA_CRAFT = "Craft"
MOEDA_CRAFT = {"heroi": "Brasão de Herói", "mito": "Brasão Mítico"}


def nivel_craft(trilha: str = "mito") -> int:
    """Nível máximo do craft com 80 brasões da trilha (Icy Veins: Herói 318, Mito 331)."""
    from ..data import regras

    tabela = regras.craft().get("ilvl_max") or {"heroi": 318, "mito": 331}
    return int(tabela.get(trilha) or ILVL_CRAFT)


# Armas: tipo pelo texto do slot da receita -> (slot do simc, mãos).
_TIPOS_ARMA = (
    ("escudo", "escudo", "off_hand", "1h"),
    ("mão secundária", "foco", "off_hand", "1h"),
    ("arma de fogo", "arma_fogo", "main_hand", "2h"),
    ("cajado", "cajado", "main_hand", "2h"),
    ("haste", "arma_haste", "main_hand", "2h"),
    ("2m", "arma_2m", "main_hand", "2h"),
    ("adaga", "adaga", "main_hand", "1h"),
    ("glaive", "glaive", "main_hand", "1h"),
    ("espada", "espada", "main_hand", "1h"),
    ("machado", "machado", "main_hand", "1h"),
    ("maça", "maca", "main_hand", "1h"),
    ("punho", "punho", "main_hand", "1h"),
)
# Proficiência de armas por classe (regra fixa do jogo).
ARMAS_DA_CLASSE = {
    "deathknight": {"espada", "machado", "maca", "arma_haste", "arma_2m"},
    "demonhunter": {"glaive", "espada", "machado", "punho", "adaga"},
    "druid": {"adaga", "maca", "cajado", "arma_haste", "punho", "foco"},
    "evoker": {"adaga", "espada", "machado", "maca", "cajado", "punho", "foco"},
    "hunter": {"arma_fogo", "arma_haste", "cajado", "espada", "machado", "adaga", "punho", "arma_2m"},
    "mage": {"adaga", "espada", "cajado", "foco"},
    "monk": {"espada", "machado", "maca", "arma_haste", "cajado", "punho"},
    "paladin": {"espada", "machado", "maca", "arma_haste", "escudo", "arma_2m"},
    "priest": {"adaga", "maca", "cajado", "foco"},
    "rogue": {"adaga", "espada", "machado", "maca", "punho"},
    "shaman": {"adaga", "machado", "maca", "cajado", "punho", "escudo", "foco"},
    "warlock": {"adaga", "espada", "cajado", "foco"},
    "warrior": {"adaga", "espada", "machado", "maca", "arma_haste", "cajado", "punho", "escudo", "arma_2m"},
}
_LISTAS_ARMAS = [
    ("ferraria", "armas_uma_mao"), ("ferraria", "armas_duas_maos"), ("ferraria", "escudos"),
    ("escrivania", "armas"), ("escrivania", "maos_secundarias"), ("engenharia", "armas_de_fogo"),
]


def tipo_da_arma(texto: str | None) -> tuple[str, str, str] | None:
    """(tipo, slot, mãos) pelo texto da receita; None se não for arma de combate."""
    t = (texto or "").lower()
    if "mira" in t:
        return None
    for marca, tipo, slot, maos in _TIPOS_ARMA:
        if marca in t:
            return tipo, slot, maos
    return None

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
    slot: str                 # interno: head, finger, back, main_hand, off_hand
    embutido: bool            # já vem com embelezamento (não aceita outro)
    maos: str | None = None   # armas: "1h" ou "2h"


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
    # Dados visuais do Wowhead (A8). Só para a tela; nenhum número daqui vira DPS.
    icone_url: str | None = None
    texto_completo: str | None = None
    materiais: list[str] = field(default_factory=list)
    usado_em: list[str] = field(default_factory=list)


def _construir(e: dict) -> Embelezamento:
    return Embelezamento(
        e["reagente_id"],
        e.get("nome_pt"),
        e["nome_en"],
        e["token_simc"],
        e.get("alvo"),
        e.get("descricao"),
        e.get("bonus_id"),
        e.get("icone_url"),
        e.get("texto_completo"),
        list(e.get("materiais") or []),
        list(e.get("usado_em") or []),
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


def itens_craftaveis(tipo_armadura: str | None, classe: str | None = None) -> list[ItemCraft]:
    """Peças craftáveis com id para o tipo de armadura, anéis, colar e (com a classe) armas."""
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
    permitidas = ARMAS_DA_CLASSE.get(classe or "", set())
    for prof, chave in _LISTAS_ARMAS if permitidas else []:
        for item in receitas.get(prof, {}).get(chave, []) or []:
            item_id = item.get("id")
            if not item_id or item.get("pvp") or "competitor" in (item.get("nome_en") or "").lower():
                continue
            if "Rara" in str(item.get("qualidade") or "") or "Incomum" in str(item.get("qualidade") or ""):
                continue  # só épicos sobem com Centelha e brasões
            tipo = tipo_da_arma(item.get("slot") or item.get("tipo"))
            if tipo is None or tipo[0] not in permitidas:
                continue
            emb = embutidos.get(item_id, {})
            saida[(item_id, tipo[1])] = ItemCraft(
                int(item_id), item.get("nome_pt") or emb.get("nome_pt"), item.get("nome_en"),
                tipo[1], bool(emb.get("embutido") or item.get("embelezado_embutido")), tipo[2],
            )
    return sorted(saida.values(), key=lambda i: (i.slot, i.item_id))


def _nome(item_id: int, slot: str, par: tuple[str, str], emb: str | None = None) -> str:
    return f"f_{item_id}_{slot}_{par[0]}_{par[1]}" + (f"_e_{emb}" if emb else "")


def _gema_e_encanto(item: ItemCraft, atual: Candidato | None, gema_padrao: int | None):
    """A peça nova herda o encantamento do slot e as gemas (só nos engastes que ela tem).

    Sem isso a peça craftada ia ao simc "pelada" e perdia o encantamento/gema que a
    peça atual tem no mesmo slot — o ganho saía subestimado.
    """
    enchant = atual.enchant_id if atual is not None else None
    n = catalog.engastes(item.item_id) or 0
    gemas = list(atual.gem_ids if atual is not None else [])[:n]
    while gema_padrao and len(gemas) < n:
        gemas.append(gema_padrao)
    return enchant, gemas


def gema_mais_usada(base: Conjunto) -> int | None:
    contagem: dict[int, int] = {}
    for c in base.itens.values():
        for g in c.gem_ids or []:
            contagem[g] = contagem.get(g, 0) + 1
    return max(contagem, key=contagem.get) if contagem else None


def candidato(
    item: ItemCraft, slot: str, par: tuple[str, str], emb: Embelezamento | None = None,
    ilvl: int = ILVL_CRAFT, atual: Candidato | None = None, gema_padrao: int | None = None,
) -> Candidato:
    enchant, gemas = _gema_e_encanto(item, atual, gema_padrao)
    return Candidato(
        slot=slot,
        item_id=item.item_id,
        enchant_id=enchant,
        gem_ids=gemas,
        ilvl=ilvl,
        ilevel=ilvl,
        tipo_arma=item.maos or "desconhecido",
        crafted_stats=[ID_STAT[par[0]], ID_STAT[par[1]]],
        embelezamento_simc=emb.token_simc if emb else None,
        embelezamento=item.embutido or emb is not None,
        craftado=True,
        fonte="craft",
        nome_pt=item.nome_pt,
        nome_en=item.nome_en,
    )


def _troca_arma(base: Conjunto, item: ItemCraft, cand: Candidato) -> Conjunto | None:
    """Arma craftada no conjunto, respeitando 1 mão + secundária x 2 mãos."""
    tem_secundaria = base.itens.get("off_hand") is not None
    if item.maos == "2h":
        itens = dict(base.itens)
        itens["main_hand"] = cand
        itens.pop("off_hand", None)
        return base.model_copy(update={"itens": itens})
    if not tem_secundaria:
        return None  # usa 2 mãos hoje: 1 mão ou secundária sozinha não fecham o par
    return base.com_troca(item.slot, cand)


def montar_opcoes_craft(
    base: Conjunto, itens: list[ItemCraft], ilvl: int = ILVL_CRAFT
) -> tuple[
    dict[str, Conjunto],
    dict[str, Opcao],
    dict[str, tuple[ItemCraft, tuple[str, str], str]],
]:
    """Cada peça × cada par de secundários, em cada slot onde cabe."""
    conjuntos: dict[str, Conjunto] = {}
    opcoes: dict[str, Opcao] = {}
    meta: dict[str, tuple[ItemCraft, tuple[str, str], str]] = {}
    gema = gema_mais_usada(base)
    for item in itens:
        dm = ItemDeMasmorra(item.item_id, item.nome_pt, item.slot, MASMORRA_CRAFT, "craft", None)
        for slot in SLOTS_DUPLOS.get(item.slot, (item.slot,)):
            for par in PARES:
                nome = _nome(item.item_id, slot, par)
                cand = candidato(item, slot, par, ilvl=ilvl, atual=base.itens.get(slot), gema_padrao=gema)
                if item.maos:
                    conj = _troca_arma(base, item, cand)
                    if conj is None:
                        continue
                else:
                    conj = base.com_troca(slot, cand)
                conjuntos[nome] = conj
                opcoes[nome] = Opcao(nome, dm, slot, False, ilvl=ilvl)
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
    # Plano de 2 peças: melhor dupla e alternativas, medidas juntas.
    plano: dict | None = None


MAX_SLOTS_PLANO = 6
ALTERNATIVAS_PLANO = 3


def plano_de_duas(base, melhor_por_slot, conjuntos, meta, *, ctx, simular, iteracoes, ilvl) -> dict | None:
    """Duplas de peças craftadas medidas juntas; None se menos de 2 peças têm ganho.

    Entram as peças com ganho positivo sozinhas, mesmo dentro da margem: medir a
    dupla com mais iterações separa o que a triagem não separou.
    """
    servem = sorted(
        ((s, v) for s, v in melhor_por_slot.items() if v[0].delta_cru > 0),
        key=lambda kv: -kv[1][0].delta_cru,
    )[:MAX_SLOTS_PLANO]
    if len(servem) < 2:
        return None
    duplas: dict[str, tuple] = {}
    for (s1, v1), (s2, v2) in combinations(servem, 2):
        _a1, i1, p1, n1 = v1
        _a2, i2, p2, n2 = v2
        if {s1, s2} <= {"main_hand", "off_hand"} and (i1.maos == "2h" or i2.maos == "2h"):
            continue  # 2 mãos já ocupa a secundária
        if i1.item_id == i2.item_id:
            continue  # único-equipado (ex.: o mesmo anel nos dois dedos)
        conj = conjuntos[n1]
        for s, cand in conjuntos[n2].itens.items():
            if base.itens.get(s) is not cand:
                conj = conj.com_troca(s, cand)
        if i2.maos == "2h":
            itens_c = dict(conj.itens)
            itens_c.pop("off_hand", None)
            conj = conj.model_copy(update={"itens": itens_c})
        ok, _m = validar(conj, ctx)
        if not ok:
            continue
        duplas[f"par_{s1}_{s2}"] = (conj, [(s1, i1, p1), (s2, i2, p2)])
    if not duplas:
        return {"melhor": None, "alternativas": [], "motivo": "Nenhuma dupla cabe no limite de 2 embelezamentos."}
    leitura = simular({n: c for n, (c, _) in duplas.items()}, iteracoes)
    if not leitura.base_dps:
        return None
    linhas = []
    for nome, (conj, pecas) in duplas.items():
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        erro = max([LIMIAR_PCT, *(abs(e) for e in (leitura.base_erro, leitura.erros.get(nome)) if e is not None)])
        linhas.append({
            "slots": [p[0] for p in pecas],
            "pecas": [
                {
                    "slot": s, "item_id": i.item_id, "nome_pt": i.nome_pt, "nome_en": i.nome_en,
                    "missiva": _par_texto(p), "embutido": i.embutido, "ilvl": ilvl,
                    "centelhas": CENTELHAS_DUAS_MAOS if i.maos == "2h" else CENTELHAS,
                }
                for s, i, p in pecas
            ],
            "dps": round(dps, 1),
            "ganho_pct": round(100.0 * (dps - leitura.base_dps) / leitura.base_dps, 3),
            "limiar_pct": round(erro, 3),
            "_conjunto": conj,
        })
    linhas.sort(key=lambda l: -l["ganho_pct"])
    melhor = linhas[0]
    for l in linhas:
        l["diferenca_pct"] = round(l["ganho_pct"] - melhor["ganho_pct"], 3)
    conjunto = melhor["_conjunto"]
    for l in linhas:
        l.pop("_conjunto", None)
    return {
        "melhor": melhor,
        "alternativas": linhas[1 : 1 + ALTERNATIVAS_PLANO],
        "base_dps": round(leitura.base_dps, 1),
        "iteracoes": iteracoes,
        "nota": (
            "As outras peças continuam as que você usa hoje. Para trocar os demais slots por "
            "drops, use Masmorras M+."
        ),
        "_conjunto": conjunto,
    }


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
    ilvl: int = ILVL_CRAFT,
) -> ResultadoCraft:
    """Fase 1: melhor peça+missiva por slot. Fase 2: cada embelezamento no melhor slot onde cabe."""
    conjuntos, opcoes, meta = montar_opcoes_craft(base, itens, ilvl)
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
            "ilvl": ilvl,
            "centelhas": CENTELHAS_DUAS_MAOS if item.maos == "2h" else CENTELHAS,
        }
        for slot, (a, item, par, _) in sorted(melhor_por_slot.items(), key=lambda kv: -kv[1][0].delta_cru)
    ]

    # P-051 (A4): atributos reais da peça craftada, lidos do simc (players[i].gear).
    # É só para a tooltip; nunca entra em cálculo de DPS. Falha da sonda não
    # derruba o ranking — a tooltip apenas fica sem os atributos.
    if sondar is not None and pecas:
        alvo = {
            f"{slot}_{item.item_id}": candidato(
                item, slot, par, ilvl=ilvl, atual=base.itens.get(slot), gema_padrao=gema_mais_usada(base)
            )
            for slot, (_a, item, par, _nome) in melhor_por_slot.items()
        }
        try:
            stats_por_peca = sondar(alvo) or {}
        except Exception:  # noqa: BLE001 - sonda é opcional/visual
            stats_por_peca = {}
        for p in pecas:
            p["stats"] = stats_por_peca.get(f"{p['slot']}_{p['item_id']}")

    # Fase 3 (pedido do usuário 2026-11-09): o plano é craftar DUAS peças, não
    # todas. Mede juntas as duplas entre as melhores peças (o resto continua o
    # que você usa hoje) e devolve a melhor e as alternativas com a diferença.
    base_original = base
    plano = plano_de_duas(
        base, melhor_por_slot, conjuntos, meta, ctx=ctx, simular=simular,
        iteracoes=max(it_refino, 2_000), ilvl=ilvl,
    )
    if plano is not None and plano["melhor"] is not None:
        # Tooltip: a peça do plano é a mesma (item + missiva) da lista "sozinha";
        # reaproveita os atributos que a sonda leu do simc.
        stats_por_peca = {(p["slot"], p["item_id"]): p.get("stats") for p in pecas}
        for linha in [plano["melhor"], *plano["alternativas"]]:
            for p in linha["pecas"]:
                p["stats"] = stats_por_peca.get((p["slot"], p["item_id"]))
        base = plano["_conjunto"]
        pares_slots = set(plano["melhor"]["slots"])
        melhor_nao_embutido = {s: v for s, v in melhor_nao_embutido.items() if s in pares_slots}
    else:
        plano = None

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
                        atual.slot,
                        candidato(
                            item, atual.slot, par, emb, ilvl=ilvl,
                            atual=base.itens.get(atual.slot), gema_padrao=gema_mais_usada(base),
                        ),
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
        conjunto = base.com_troca(
            slot,
            candidato(
                item, slot, par, emb, ilvl=ilvl,
                atual=(base_original.itens.get(slot)), gema_padrao=gema_mais_usada(base_original),
            ),
        )
        ok, motivos = validar(conjunto, ctx)
        if not ok:
            avisos.append(f"{emb.nome_pt or emb.nome_en}: não medido ({'; '.join(motivos)})")
            continue
        nome = _nome(item.item_id, slot, par, emb.token_simc)
        fase2[nome] = conjunto
        if plano is None:
            fase2[nome_sem] = conjuntos[nome_sem]  # a mesma peça sem embelezamento, NA MESMA leitura (P4)
            por_emb[nome] = (emb, slot, "adicionar", nome_sem, None)
        else:
            # Com plano, a base desta leitura JÁ tem a peça sem embelezamento.
            por_emb[nome] = (emb, slot, "adicionar", None, None)

    embs: list[dict] = []
    if fase2:
        # V-5: embelezamentos diferem por décimos de %; com poucas iterações a
        # ordem entre eles fica dentro do ruído.
        leitura2 = simular(fase2, max(it_refino, 3_000))
        base2 = leitura2.base_dps
        for nome, (emb, slot, tipo, ref, atual_nome) in por_emb.items():
            com = leitura2.resultados.get(nome)
            if not base2 or com is None:
                continue
            if tipo == "adicionar" and ref:
                referencia = leitura2.resultados.get(ref)
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
                    "icone_url": emb.icone_url,
                    "texto_completo": emb.texto_completo,
                    "materiais": emb.materiais,
                    "usado_em": emb.usado_em,
                    "ganho_pct": round(100.0 * (com - referencia) / base2, 3),
                    "ganho_total_pct": round(100.0 * (com - base2) / base2, 3),
                    "limiar_pct": round(erro, 3),
                }
            )
        embs.sort(key=lambda e: -e["ganho_pct"])
    if plano is not None:
        plano.pop("_conjunto", None)
    return ResultadoCraft(base_dps, pecas, embs, avisos, bloqueados, plano)
