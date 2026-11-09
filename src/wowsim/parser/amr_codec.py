"""Prototipo do codec AMR (decodificar e codificar), espelho de Import.lua/Serializer.lua."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# Tags cujo valor e DIFERENCA para o anterior (AskMrRobot-Serializer.lua:751-870,
# Import.lua:127-272). Gemas x/y/z compartilham um unico contador.
_CONTADOR_DA_TAG = {"i": "i", "u": "u", "v": "v", "n": "n", "b": "b",
                    "o": "o", "x": "gema", "y": "gema", "z": "gema", "e": "e"}
_PARTE = re.compile(r"([a-z]?)(-?\d+)")

@dataclass
class ItemAmr:
    item_id: int
    slot: int | None = None            # s  (absoluto)
    upgrade_id: int = 0                # u  (diferenca)
    level: int = 0                     # v  (diferenca)
    tuning: int = 0                    # n  (diferenca)
    bonus_ids: list[int] = field(default_factory=list)   # b (diferenca, encadeada)
    stat1: int = 0                     # j  (absoluto)
    stat2: int = 0                     # k  (absoluto)
    craft_quality: int = 0             # l  (absoluto, escala do AMR)
    vinculo: int = 0                   # d  (absoluto: 1 = soulbound, 5 = warbound)
    catalisado: bool = False           # c1
    disc_spell_id: int = 0             # h  (absoluto)
    catalyst_source: int = 0           # o  (diferenca)
    gem_ids: list[int] = field(default_factory=lambda: [0, 0, 0])  # x y z
    enchant_id: int = 0                # e  (diferenca)
    inventory_id: int = 0              # t  (absoluto; so nas strings de importacao)
    guid: str | None = None            # depois de "!"

def decodificar_itens(tokens: list[str]) -> list[ItemAmr]:
    """Decodifica uma lista de itens de UMA secao. Os contadores zeram por secao."""
    prev = {k: 0 for k in ("i", "u", "v", "n", "b", "o", "gema", "e")}
    saida: list[ItemAmr] = []
    for bruto in tokens:
        token = bruto.strip()
        if not token or token == "_":
            continue
        guid = None
        if "!" in token:
            token, guid = token.split("!", 1)
        item = ItemAmr(item_id=0, guid=guid)
        primeiro = True
        for tag, valor_txt in _PARTE.findall(token):
            valor = int(valor_txt)
            tag = tag or ("i" if primeiro else "")
            primeiro = False
            contador = _CONTADOR_DA_TAG.get(tag)
            if contador is not None:
                valor += prev[contador]
                prev[contador] = valor
            if tag == "i": item.item_id = valor
            elif tag == "s": item.slot = valor
            elif tag == "u": item.upgrade_id = valor
            elif tag == "v": item.level = valor
            elif tag == "n": item.tuning = valor
            elif tag == "b": item.bonus_ids.append(valor)
            elif tag == "j": item.stat1 = valor
            elif tag == "k": item.stat2 = valor
            elif tag == "l": item.craft_quality = valor
            elif tag == "d": item.vinculo = valor
            elif tag == "c": item.catalisado = valor == 1
            elif tag == "h": item.disc_spell_id = valor
            elif tag == "o": item.catalyst_source = valor
            elif tag == "x": item.gem_ids[0] = valor
            elif tag == "y": item.gem_ids[1] = valor
            elif tag == "z": item.gem_ids[2] = valor
            elif tag == "e": item.enchant_id = valor
            elif tag == "t": item.inventory_id = valor
        saida.append(item)
    return saida

def codificar_itens(itens: list[ItemAmr]) -> list[str]:
    """Inverso exato de decodificar_itens. Ordena por id, como o addon faz."""
    prev = {k: 0 for k in ("i", "u", "v", "n", "b", "o", "gema", "e")}
    saida: list[str] = []
    for item in sorted(itens, key=lambda it: it.item_id):
        p: list[str] = [str(item.item_id - prev["i"])]; prev["i"] = item.item_id
        if item.slot is not None: p.append(f"s{item.slot}")
        if item.upgrade_id: p.append(f"u{item.upgrade_id - prev['u']}"); prev["u"] = item.upgrade_id
        if item.level: p.append(f"v{item.level - prev['v']}"); prev["v"] = item.level
        if item.tuning: p.append(f"n{item.tuning - prev['n']}"); prev["n"] = item.tuning
        for b in item.bonus_ids:
            p.append(f"b{b - prev['b']}"); prev["b"] = b
        if item.stat1: p.append(f"j{item.stat1}")
        if item.stat2: p.append(f"k{item.stat2}")
        if item.craft_quality: p.append(f"l{item.craft_quality}")
        if item.vinculo: p.append(f"d{item.vinculo}")
        if item.catalisado: p.append("c1")
        if item.disc_spell_id: p.append(f"h{item.disc_spell_id}")
        if item.catalyst_source: p.append(f"o{item.catalyst_source - prev['o']}"); prev["o"] = item.catalyst_source
        for tag, gema in zip("xyz", item.gem_ids):
            if gema: p.append(f"{tag}{gema - prev['gema']}"); prev["gema"] = gema
        if item.enchant_id: p.append(f"e{item.enchant_id - prev['e']}"); prev["e"] = item.enchant_id
        if item.inventory_id: p.append(f"t{item.inventory_id}")
        if item.guid: p.append("!" + item.guid)
        saida.append("".join(p))
    return saida


# ---------------------------------------------------------------------------
# Linha de importacao (o que se cola no addon com /amr import).
# Formato lido por Import.lua:305-460. O cabecalho (posicoes 0..14) e copiado
# de uma string que o proprio AMR gerou para o personagem; so os itens e o
# bloco de extras sao do sistema.
# ---------------------------------------------------------------------------
_PROIBIDOS = set("$;@\\#\n\r")
INICIO_ITENS = 15  # indice 0-based: parts[16] do Lua (1-based)

def _limpo(texto: str, campo: str) -> str:
    if not texto or any(c in _PROIBIDOS for c in texto):
        raise ValueError(f"{campo} vazio ou com caractere reservado ($ ; @ \\ # quebra de linha).")
    return texto

def cabecalho_do_modelo(linha_modelo: str) -> list[str]:
    """Extrai as 15 primeiras partes (identidade, spec, talentos, arvore, .qN)."""
    partes_dolar = linha_modelo.strip().split("$")
    partes = partes_dolar[1].split(";") if len(partes_dolar) >= 2 else []
    sN = [p for p in partes if p.startswith(".s") and p[2:].isdigit()]
    if len(sN) > 1 or ";.inv" in linha_modelo:
        # V-6: o export do PERSONAGEM tem blocos .sN (specs) antes do .q.
        raise ValueError(
            "Isso parece o export do personagem (addon AMR → Exportar). Cole a string de "
            "Best in Bags que o site do AMR gera (Best in Bags → exportar para o addon)."
        )
    if len(partes_dolar) != 3:
        raise ValueError(
            "String do AMR inválida: a string de Best in Bags tem exatamente dois '$'. "
            "Copie de novo do site do AMR (Best in Bags → exportar para o addon)."
        )
    if len(partes) <= INICIO_ITENS or not partes[INICIO_ITENS - 1].startswith(".q"):
        raise ValueError(
            "String do AMR inválida: não é uma string de Best in Bags (falta o bloco '.qN'). "
            "Copie de novo do site do AMR."
        )
    return partes[:INICIO_ITENS]

def linha_importacao(linha_modelo: str, itens: list[ItemAmr], *, setup_id: str,
                     rotulo: str, encantos: list[str] = ()) -> str:
    """Monta uma linha que o addon do AMR aceita. ``encantos`` ja formatados
    como 'e\\id\\item\\spell\\texto\\materiais' (6 campos, materiais pode ser '')."""
    _limpo(setup_id, "setup_id"); _limpo(rotulo, "rotulo")
    if setup_id.upper().startswith("AMR"):
        raise ValueError("setup_id nao pode comecar com 'AMR': o addon o trataria como "
                         "setup proprio e sobrescreveria um do usuario (Import.lua: IsBib).")
    for e in encantos:
        if not e.startswith("e\\") or e.count("\\") != 5:
            raise ValueError(f"Encanto mal formado (precisa de 6 campos): {e!r}")
    corpo = ";".join(cabecalho_do_modelo(linha_modelo) + codificar_itens(itens))
    extra = "@" + f"{setup_id}#_" + "@" + rotulo + "".join("@" + e for e in encantos)
    return "$" + corpo + "$" + extra

def itens_da_linha(linha: str) -> list[ItemAmr]:
    partes = linha.strip().split("$")[1].split(";")
    return decodificar_itens(partes[INICIO_ITENS:])


def encantos_da_linha(linha: str) -> dict[int, dict]:
    """Extrai o bloco ``@e\\id\\itemId\\spellId\\texto\\materiais`` de uma linha
    de Best in Bags do AMR. Cada entrada tem 6 campos; ``materiais`` pode ser
    vazio, mas a barra final é obrigatória (Import.lua faz ``gsub`` no texto).
    """
    saida: dict[int, dict] = {}
    for parte in linha.split("@"):
        if not parte.startswith("e\\"):
            continue
        campos = parte.split("\\")
        if len(campos) < 6:
            continue
        try:
            enchant_id = int(campos[1])
            item_id = int(campos[2])
            spell_id = int(campos[3])
        except ValueError:
            continue
        saida[enchant_id] = {
            "item_id": item_id,
            "spell_id": spell_id,
            "nome": campos[4],
            "materiais": campos[5],
        }
    return saida
