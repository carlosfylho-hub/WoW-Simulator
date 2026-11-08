# REFERÊNCIA VALIDADA — docs/WORKFLOW-IMPLEMENTACAO.md explica onde e como usar.
# Não é importado pelo pacote. Foi rodado contra fixtures/ reais em 2026-11-08.
"""Prototipo: pool de M+ por masmorra, elegibilidade e classificacao dos itens."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from wowsim.data import catalog

# Os berloques ficam em subsecoes nomeadas pela masmorra, sem campo dungeon_pt.
# Chave da subsecao -> nome PT-BR usado nos demais itens (conferido em dados/).
MASMORRA_DA_SUBSECAO = {
    "altar_das_presas": "Altar das Presas",
    "murder_row": "Murder Row",
    "o_vale_ofuscante": "O Vale Ofuscante",
    "arena_rasgada_pelo_vazio": "Arena da Chaga do Caos",
    "covil_de_nalorakk": "Covil de Nalorakk",
    "piscinas_da_vida_rubi": "Piscinas da Vida Rubi",
    "templo_de_sethraliss": "Templo de Sethraliss",
    "descanso_do_rei": "Descanso do Rei",
}
SECAO_ARMADURA = {"tecido": "armadura_tecido_mplus", "couro": "armadura_couro_mplus"}

@dataclass(frozen=True)
class ItemDeMasmorra:
    item_id: int
    nome_pt: str | None
    slot: str
    masmorra: str
    secao: str
    usavel_conjurador: bool | None

def itens_por_masmorra() -> list[ItemDeMasmorra]:
    saida, vistos = [], set()
    for secao, sub, item in catalog._flatten_mplus():
        masmorra = item.get("dungeon_pt") or MASMORRA_DA_SUBSECAO.get(sub)
        if not masmorra:
            continue  # sem masmorra conhecida (ex.: Delve): fora deste ranking
        slot = catalog.normalizar_slot(item.get("slot") or sub)
        if secao == "trinkets_mplus":
            slot = "trinket"
        chave = (int(item["item_id"]), masmorra)
        if chave in vistos or not slot:
            continue
        vistos.add(chave)
        saida.append(ItemDeMasmorra(int(item["item_id"]), item.get("nome_pt"), slot,
                                    masmorra, secao, item.get("usavel_por_conjurador")))
    return saida

def elegivel(item: ItemDeMasmorra, *, tipo_armadura: str, atributo: str) -> bool:
    """O jogo filtra o loot pela spec; desconhecido = mantem (decide o simc)."""
    if item.secao.startswith("armadura_") and item.secao != SECAO_ARMADURA.get(tipo_armadura):
        return False
    if item.slot == "trinket":
        return item.usavel_conjurador is not False if atributo == "Intelecto" else True
    primario = catalog.atributo_primario(item.item_id)
    return primario is None or primario == atributo

@dataclass
class Avaliacao:
    item: ItemDeMasmorra
    delta_cru: float
    limiar_cru: float
    delta_cat: float | None = None
    limiar_cat: float | None = None
    @property
    def etiqueta(self) -> str:
        cru = self.delta_cru > self.limiar_cru
        cat = self.delta_cat is not None and self.delta_cat > (self.limiar_cat or 0)
        if cru and cat and self.delta_cat > self.delta_cru + (self.limiar_cat or 0):
            return "ambos"
        if cru: return "direto"
        if cat: return "catalisar"
        return "nao_serve"
    @property
    def ganho(self) -> float:
        return max(self.delta_cru, self.delta_cat if self.delta_cat is not None else self.delta_cru)

def agrupar(avaliacoes: list[Avaliacao], elegiveis: dict[str, int]) -> list[dict]:
    por = defaultdict(list)
    for a in avaliacoes:
        por[a.item.masmorra].append(a)
    linhas = []
    for nome, lista in por.items():
        servem = [a for a in lista if a.etiqueta != "nao_serve"]
        linhas.append({"masmorra": nome, "servem": len(servem), "elegiveis": elegiveis.get(nome, len(lista)),
                       "maior": max((a.ganho for a in servem), default=0.0),
                       "catalisar": sum(a.etiqueta == "catalisar" for a in servem),
                       "direto": sum(a.etiqueta in ("direto", "ambos") for a in servem),
                       "itens": sorted(lista, key=lambda a: -a.ganho)})
    return linhas

def ordenar(linhas: list[dict], por: str = "quantidade") -> list[dict]:
    if por == "maior":
        return sorted(linhas, key=lambda l: (-l["maior"], -l["servem"], l["masmorra"]))
    return sorted(linhas, key=lambda l: (-l["servem"], -l["maior"], l["masmorra"]))
