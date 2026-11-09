"""Motor do ranking de masmorras M+: monta candidatos, avalia deltas e agrupa.

P4: cada avaliação usa a base da MESMA leitura do simc. P1: a "chance" é uma
suposição rotulada (ver ``modelos.PREMISSA_CHANCE``). Nenhum número de dano sai
daqui além do que o simc mediu.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..topgear.catalisador import gemeo_catalisado
from ..topgear.models import Candidato, Conjunto
from ..topgear.pools import NIVEL_PARA_BONUS
from ..topgear.runner import LeituraSim, criar_simulador, estilo_de_luta
from ..topgear.search import _limiar_por_erro, conjunto_do_personagem
from .catalogo import ItemDeMasmorra

SLOTS_DUPLOS = {"finger": ("finger1", "finger2"), "trinket": ("trinket1", "trinket2")}
LIMIAR_PCT = 0.15


@dataclass(frozen=True)
class Opcao:
    nome: str            # nome do profileset, único no arquivo
    item: ItemDeMasmorra
    slot: str            # slot interno onde foi testado
    catalisado: bool
    ilvl: int | None = None  # ilvl próprio do item (cofre); masmorras usam o do pedido


def montar_opcoes(
    base: Conjunto, itens: list[ItemDeMasmorra], *, ilvl: int, classe: str | None
) -> tuple[dict[str, Conjunto], dict[str, Opcao]]:
    if ilvl not in NIVEL_PARA_BONUS:
        raise ValueError(f"ilvl {ilvl} sem bonus_id conhecido; use {sorted(NIVEL_PARA_BONUS)}.")
    bonus = NIVEL_PARA_BONUS[ilvl]
    conjuntos: dict[str, Conjunto] = {}
    opcoes: dict[str, Opcao] = {}
    for item in itens:
        for slot in SLOTS_DUPLOS.get(item.slot, (item.slot,)):
            if base.item_id(slot) == item.item_id:
                continue
            cru = Candidato(
                slot=slot, item_id=item.item_id, bonus_id=bonus, bonus_ids=[bonus],
                ilvl=ilvl, fonte=f"mplus:{item.masmorra}", nome_pt=item.nome_pt,
            )
            variantes = [(cru, False)]
            gemeo = gemeo_catalisado(cru, classe)
            if gemeo is not None:
                variantes.append((gemeo, True))
            for candidato, catalisado in variantes:
                nome = f"{'k' if catalisado else 'c'}_{item.item_id}_{slot}"
                conjuntos[nome] = base.com_troca(slot, candidato)
                opcoes[nome] = Opcao(nome, item, slot, catalisado)
    return conjuntos, opcoes


@dataclass
class Avaliacao:
    item: ItemDeMasmorra
    delta_cru: float
    limiar_cru: float
    delta_cat: float | None = None
    limiar_cat: float | None = None
    slot: str = ""
    ilvl: int | None = None
    # Profileset vencedor de cada versão (P-041): a montagem usa a versão certa.
    nome_cru: str = ""
    nome_cat: str | None = None

    @property
    def etiqueta(self) -> str:
        cru = self.delta_cru > self.limiar_cru
        cat = self.delta_cat is not None and self.delta_cat > (self.limiar_cat or 0)
        if cru and cat and self.delta_cat > self.delta_cru + (self.limiar_cat or 0):
            return "ambos"
        if cru:
            return "direto"
        if cat:
            return "catalisar"
        return "nao_serve"

    @property
    def usa_catalisado(self) -> bool:
        """A versão a usar é a catalisada só quando ela é o motivo de servir."""
        return self.delta_cat is not None and self.etiqueta in ("catalisar", "ambos")

    @property
    def ganho_escolhido(self) -> float:
        """Ganho da versão que a montagem vai usar."""
        return self.delta_cat if self.usa_catalisado else self.delta_cru  # type: ignore[return-value]

    @property
    def ganho(self) -> float:
        return max(
            self.delta_cru,
            self.delta_cat if self.delta_cat is not None else self.delta_cru,
        )


def avaliar(
    leitura: LeituraSim, opcoes: dict[str, Opcao], *, referencia: str | None = None
) -> list[Avaliacao]:
    if referencia is None:
        base, base_erro = leitura.base_dps, leitura.base_erro
    else:
        base, base_erro = leitura.resultados.get(referencia), leitura.erros.get(referencia)
    if not base or base <= 0:
        raise ValueError("A leitura não trouxe o DPS de referência.")

    melhor: dict[int, dict] = {}  # por item: melhor cru e melhor catalisado entre os slots
    for nome, op in opcoes.items():
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        delta = 100.0 * (dps - base) / base
        limiar = _limiar_por_erro(LIMIAR_PCT, base_erro, leitura.erros.get(nome))
        registro = melhor.setdefault(op.item.item_id, {"item": op.item})
        campo = "cat" if op.catalisado else "cru"
        if campo not in registro or delta > registro[campo][0]:
            registro[campo] = (delta, limiar, op.slot, op.ilvl, nome)

    saida: list[Avaliacao] = []
    for registro in melhor.values():
        if "cru" not in registro:
            continue
        d_cru, l_cru, slot, ilvl, n_cru = registro["cru"]
        d_cat, l_cat, _, _, n_cat = registro.get("cat", (None, None, "", None, None))
        saida.append(
            Avaliacao(
                registro["item"], d_cru, l_cru, d_cat, l_cat, slot, ilvl,
                nome_cru=n_cru, nome_cat=n_cat,
            )
        )
    return saida


def rodar_ranking(
    personagem,
    itens: list[ItemDeMasmorra],
    *,
    cenario: str = "dungeon_slice",
    ilvl: int,
    it_triagem: int = 300,
    it_refino: int = 3000,
    threads: int | None = None,
    cancelar=None,
    orcamento_restante=None,
    base_out: dict | None = None,
) -> list[Avaliacao]:
    base = conjunto_do_personagem(personagem)
    conjuntos, opcoes = montar_opcoes(base, itens, ilvl=ilvl, classe=personagem.classe)
    simular = criar_simulador(
        personagem, fight_style=estilo_de_luta(cenario), threads=threads,
        cancelar=cancelar, orcamento_restante=orcamento_restante,
    )
    leitura_triagem = simular(conjuntos, it_triagem)                 # execução 1
    if base_out is not None:
        base_out["base_dps"] = leitura_triagem.base_dps
    triagem = avaliar(leitura_triagem, opcoes)
    # Refina tudo que não perdeu claramente; o resto fica como "não serve".
    vivos = {a.item.item_id for a in triagem if a.ganho > -a.limiar_cru}
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    refino = avaliar(
        simular({n: conjuntos[n] for n in nomes}, it_refino),
        {n: opcoes[n] for n in nomes},
    )                                                                 # execução 2
    refinados = {a.item.item_id for a in refino}
    return refino + [a for a in triagem if a.item.item_id not in refinados]


def agrupar(avaliacoes: list[Avaliacao], elegiveis: dict[str, int]) -> list[dict]:
    por: dict[str, list[Avaliacao]] = defaultdict(list)
    for a in avaliacoes:
        por[a.item.masmorra].append(a)
    linhas: list[dict] = []
    for nome, lista in por.items():
        servem = [a for a in lista if a.etiqueta != "nao_serve"]
        linhas.append(
            {
                "masmorra": nome,
                "servem": len(servem),
                "elegiveis": elegiveis.get(nome, len(lista)),
                "maior": max((a.ganho for a in servem), default=0.0),
                "catalisar": sum(a.etiqueta == "catalisar" for a in servem),
                "direto": sum(a.etiqueta in ("direto", "ambos") for a in servem),
                "itens": sorted(lista, key=lambda a: -a.ganho),
            }
        )
    return linhas


def ordenar(linhas: list[dict], por: str = "quantidade") -> list[dict]:
    if por == "maior":
        return sorted(linhas, key=lambda l: (-l["maior"], -l["servem"], l["masmorra"]))
    return sorted(linhas, key=lambda l: (-l["servem"], -l["maior"], l["masmorra"]))
