"""Generate SimC profilesets for equipment variations.

Every generator returns Variacao objects with the override lines. The base
profile is always included and never carries a profileset line.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence

from ..data import catalog
from ..data.enchants import resolver as resolver_encantamento
from ..models import ItemEquipado, Personagem, Variacao
from ..parser.addon import serializar_texto
from . import omnium

CATEGORIAS = (
    "upgrade",
    "item",
    "encanto",
    "gema",
    "talento",
    "folio",
    "berloque",
)

ENCANTAVEIS = ("head", "shoulder", "chest", "feet", "main_hand")
ANEL = ("finger1", "finger2")
SLOT_PT = {
    "head": "cabeça",
    "shoulder": "ombros",
    "chest": "peitoral",
    "feet": "pés",
    "main_hand": "arma",
}
NIVEL_PARA_BONUS = {341: 12856, 334: 12854, 328: 12848, 321: 12846}


def _slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(char for char in decomposto if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def _substituir_campo(linha: str, campo: str, valor: str) -> str:
    padrao = re.compile(rf"({campo}=)([^,]*)")
    if padrao.search(linha):
        return padrao.sub(rf"\g<1>{valor}", linha, count=1)
    return linha.rstrip(",") + f",{campo}={valor}"


def _trocar_bonus(linha: str, de: int, para: int) -> str | None:
    casamento = re.search(r"bonus_id=([^,]*)", linha)
    if not casamento:
        return None
    ids = casamento.group(1).split("/")
    if str(de) not in ids:
        return None
    trocados = [str(para) if item == str(de) else item for item in ids]
    return linha[: casamento.start(1)] + "/".join(trocados) + linha[casamento.end(1) :]


def _linha_novo_item(
    slot: str,
    item_id: int,
    *,
    bonus_id: int | None,
    base: ItemEquipado | None,
) -> str:
    partes = [f"{slot}=", f"id={item_id}"]
    if base is not None and base.enchant_id is not None:
        partes.append(f"enchant_id={base.enchant_id}")
    if base is not None and base.gem_ids:
        partes.append(f"gem_id={base.gem_ids[0]}")
    if bonus_id is not None:
        partes.append(f"bonus_id={bonus_id}")
    return ",".join(partes)


def _base(personagem: Personagem) -> Variacao:
    return Variacao(
        nome="base",
        categoria="base",
        linhas_override=[],
        fonte="fixtures/pyrogalth.simc",
    )


def upgrade_por_slot(personagem: Personagem, de: int, para: int) -> list[Variacao]:
    saida: list[Variacao] = []
    for slot, item in personagem.equipado.items():
        linha = _trocar_bonus(item.linha_original, de, para)
        if linha is None:
            continue
        saida.append(
            Variacao(
                nome=f"up_{_slug(slot)}",
                categoria="upgrade",
                linhas_override=[linha],
                item_ids=[item.item_id] if item.item_id else [],
                bonus_ids_envolvidos=[de, para],
                fonte="bonus_ids_s2.json",
            )
        )
    return saida


def troca_item(personagem: Personagem, *, bonus_alvo: int | None = None) -> list[Variacao]:
    saida: list[Variacao] = []
    for slot, candidatos in personagem.mochila.items():
        base = personagem.equipado.get(slot)
        for candidato in candidatos:
            if base is not None and candidato.item_id == base.item_id:
                continue
            if candidato.item_id is None:
                continue
            if catalog.ilvl_do_item(candidato) not in catalog.ILVLS_ALVO:
                continue
            linha = _linha_novo_item(slot, candidato.item_id, bonus_id=None, base=base)
            if bonus_alvo is not None:
                linha += f",bonus_id={bonus_alvo}"
                bonus_ids = [bonus_alvo]
            elif candidato.bonus_ids:
                linha += ",bonus_id=" + "/".join(str(b) for b in candidato.bonus_ids)
                bonus_ids = list(candidato.bonus_ids)
            else:
                bonus_ids = []
            saida.append(
                Variacao(
                    nome=f"item_{_slug(slot)}_{candidato.item_id}",
                    categoria="item",
                    linhas_override=[linha],
                    item_ids=[candidato.item_id],
                    bonus_ids_envolvidos=bonus_ids,
                    fonte="fixture: Gear from Bags",
                )
            )
    return saida


def encantamentos(personagem: Personagem) -> list[Variacao]:
    saida: list[Variacao] = []

    for slot in ENCANTAVEIS:
        item = personagem.equipado.get(slot)
        if item is None:
            continue
        for candidato in catalog.encantamentos_por_slot(SLOT_PT.get(slot, item.slot)):
            if candidato.camada != "encantamento":
                continue
            if candidato.tier not in (None, 2):
                continue
            if candidato.enchant_id == item.enchant_id:
                continue
            linha = _substituir_campo(
                item.linha_original, "enchant_id", str(candidato.enchant_id)
            )
            saida.append(
                Variacao(
                    nome=f"ench_{_slug(slot)}_{candidato.enchant_id}",
                    categoria="encanto",
                    linhas_override=[linha],
                    item_ids=[item.item_id] if item.item_id else [],
                    fonte=candidato.fonte,
                )
            )

    aneis = [personagem.equipado[slot] for slot in ANEL if slot in personagem.equipado]
    if len(aneis) == 2:
        for candidato in catalog.encantamentos_por_slot("anel"):
            if candidato.camada != "encantamento" or candidato.tier not in (None, 2):
                continue
            if all(item.enchant_id == candidato.enchant_id for item in aneis):
                continue
            linhas = [
                _substituir_campo(item.linha_original, "enchant_id", str(candidato.enchant_id))
                for item in aneis
            ]
            saida.append(
                Variacao(
                    nome=f"ench_rings_{candidato.enchant_id}",
                    categoria="encanto",
                    linhas_override=linhas,
                    item_ids=[item.item_id for item in aneis if item.item_id],
                    fonte=candidato.fonte,
                )
            )
    return saida


def _familia_gema(tipo: str | None) -> str:
    if not tipo:
        return "?"
    minusculo = tipo.lower()
    if "diamante" in minusculo:
        return "diamante"
    if "garnet" in minusculo:
        return "garnet"
    return minusculo.split("(")[0].strip()


def gemas(personagem: Personagem) -> list[Variacao]:
    saida: list[Variacao] = []
    todas = {gema.item_id: gema for gema in catalog.gemas()}
    for slot, item in personagem.equipado.items():
        if not item.gem_ids:
            continue
        atual = todas.get(item.gem_ids[0])
        if atual is None:
            continue
        familia = _familia_gema(atual.tipo)
        for candidato in catalog.gemas():
            if candidato.item_id == atual.item_id:
                continue
            if _familia_gema(candidato.tipo) != familia:
                continue
            linha = _substituir_campo(item.linha_original, "gem_id", str(candidato.item_id))
            saida.append(
                Variacao(
                    nome=f"gem_{_slug(slot)}_{candidato.item_id}",
                    categoria="gema",
                    linhas_override=[linha],
                    item_ids=[item.item_id] if item.item_id else [],
                    fonte=candidato.fonte,
                )
            )
    return saida


def talentos(personagem: Personagem) -> list[Variacao]:
    saida: list[Variacao] = []
    vistos: set[str] = set()
    for nome, codigo in personagem.loadouts.items():
        if codigo in vistos:
            continue
        vistos.add(codigo)
        saida.append(
            Variacao(
                nome=f"tal_{_slug(nome)}",
                categoria="talento",
                linhas_override=[f"talents={codigo}"],
                fonte="fixture: Saved Loadout",
            )
        )
    return saida


def folio(personagem: Personagem, override: str | None = None) -> list[Variacao]:
    selecao = omnium.selecao_atual(personagem, override)
    if not selecao.codigo:
        return []
    saida: list[Variacao] = []
    for nome, codigo, entry_id in omnium.variacoes_de_linha(selecao):
        ids = omnium.codigo_para_ids(codigo)
        linha = "omnium_talents=" + "/".join(f"{entry}:1" for entry in ids)
        saida.append(
            Variacao(
                nome=nome,
                categoria="folio",
                linhas_override=[linha],
                fonte="dados/derivados/omnium_entries.json",
            )
        )
    return saida


def _tipo_berloque(item_id: int | None) -> str | None:
    if item_id is None:
        return None
    for loot in catalog.berloques_conjurador():
        if loot.item_id == item_id:
            return loot.tipo_efeito
    return None


def berloques(personagem: Personagem, *, nivel: int = 341) -> list[Variacao]:
    if nivel not in NIVEL_PARA_BONUS:
        raise ValueError("Nível de berloque deve ser 341, 334, 328 ou 321.")
    saida: list[Variacao] = []
    tipos = {
        loot.item_id: loot.tipo_efeito for loot in catalog.berloques_conjurador()
    }

    candidatos = catalog.berloques_monitor(nivel)
    for slot in ("trinket1", "trinket2"):
        atual = personagem.equipado.get(slot)
        outro = personagem.equipado.get("trinket2" if slot == "trinket1" else "trinket1")
        tipo_outro = (
            tipos.get(outro.item_id)
            if outro is not None and outro.item_id is not None
            else None
        )
        for candidato in candidatos:
            if atual is not None and candidato.item_id == atual.item_id:
                continue
            if outro is not None and candidato.item_id == outro.item_id:
                continue
            tipo_candidato = tipos.get(candidato.item_id) or candidato.tipo_efeito
            aviso = None
            if tipo_candidato == "ativo" and tipo_outro == "ativo":
                aviso = (
                    "Dois berloques de uso: o jogo permite e o SimC mede o par; "
                    "costuma render menos que 1 de uso + 1 passivo."
                )
            linha = _linha_novo_item(
                slot, candidato.item_id, bonus_id=candidato.bonus_id, base=None
            )
            bonus_ids = [candidato.bonus_id] if candidato.bonus_id else []
            saida.append(
                Variacao(
                    nome=f"{slot}_{candidato.item_id}",
                    categoria="berloque",
                    linhas_override=[linha],
                    item_ids=[candidato.item_id],
                    bonus_ids_envolvidos=bonus_ids,
                    aviso=aviso,
                    fonte=candidato.fonte,
                )
            )
    return saida


def gerar(
    personagem: Personagem,
    *,
    categorias: Iterable[str] | None = None,
    de_bonus: int | None = None,
    para_bonus: int | None = None,
    runas: str | None = None,
    nivel_berloque: int = 341,
    max_variacoes: int = 40,
) -> list[Variacao]:
    """Build all requested variations, always with the base first."""
    pedidas = set(CATEGORIAS if categorias is None else categorias)
    variacoes: list[Variacao] = [_base(personagem)]

    if "upgrade" in pedidas:
        if de_bonus is None or para_bonus is None:
            raise ValueError("upgrade exige --de e --para.")
        variacoes.extend(upgrade_por_slot(personagem, de_bonus, para_bonus))
    if "item" in pedidas:
        variacoes.extend(troca_item(personagem, bonus_alvo=para_bonus))
    if "encanto" in pedidas:
        variacoes.extend(encantamentos(personagem))
    if "gema" in pedidas:
        variacoes.extend(gemas(personagem))
    if "talento" in pedidas:
        variacoes.extend(talentos(personagem))
    if "folio" in pedidas:
        variacoes.extend(folio(personagem, runas))
    if "berloque" in pedidas:
        variacoes.extend(berloques(personagem, nivel=nivel_berloque))

    unicas: list[Variacao] = []
    nomes: set[str] = set()
    for variacao in variacoes:
        if variacao.nome in nomes:
            continue
        nomes.add(variacao.nome)
        unicas.append(variacao)

    base = unicas[0]
    corpo = unicas[1 : 1 + max_variacoes]
    return [base] + corpo


def estimar_segundos(n_variacoes: int, iterations: int, fight_style: str | None = None) -> float:
    """Estimativa pela velocidade medida do simc (``calibracao``), por estilo de luta.

    Sem ``fight_style`` usa a taxa genérica antiga (~1,3 s por 1.000 iterações).
    """
    from .. import calibracao

    taxa = calibracao.taxa(fight_style) if fight_style else calibracao.TAXA_GENERICA
    return max(1.0, n_variacoes * iterations * taxa)


def escrever_arquivo(
    personagem: Personagem, variacoes: Sequence[Variacao], destino: str | Path
) -> Path:
    nomes = [variacao.nome for variacao in variacoes]
    if len(nomes) != len(set(nomes)):
        raise ValueError("Nome de variação duplicado.")
    if not nomes or variacoes[0].categoria != "base":
        raise ValueError("A primeira variação precisa ser a base.")

    linhas = [serializar_texto(personagem, incluir_checksum=False).rstrip(), ""]
    for variacao in variacoes[1:]:
        if not variacao.linhas_override:
            raise ValueError(f"{variacao.nome} não tem linha de override.")
        for linha in variacao.linhas_override:
            linhas.append(f'profileset."{variacao.nome}"+={linha}')
    linhas.append("")

    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho
