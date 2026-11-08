# REFERÊNCIA VALIDADA — docs/WORKFLOW-IMPLEMENTACAO.md explica onde e como usar.
# Não é importado pelo pacote. Foi rodado contra fixtures/ reais em 2026-11-08.
# Como rodar (na raiz de wow-sim):
#   PYTHONPATH="src:docs/referencia" python docs/referencia/ranking_t6_check.py
# Usa simulador FALSO: valida o encadeamento (2 execuções, base por leitura,
# etiquetas, ordens), não números de dano.
from __future__ import annotations
import re, sys, os
from dataclasses import dataclass
from pathlib import Path
from wowsim.parser.addon import parse_texto
from wowsim.topgear.catalisador import gemeo_catalisado
from wowsim.topgear.models import Candidato, Conjunto
from wowsim.topgear.pools import NIVEL_PARA_BONUS
from wowsim.topgear.runner import LeituraSim
from wowsim.topgear.search import _limiar_por_erro, conjunto_do_personagem
import masmorras as M
from masmorras import ItemDeMasmorra

# Avaliacao com o campo slot ao final, como o documento manda
@dataclass
class Avaliacao(M.Avaliacao):
    slot: str = ""
M.Avaliacao = Avaliacao

SLOTS_DUPLOS = {"finger": ("finger1", "finger2"), "trinket": ("trinket1", "trinket2")}
@dataclass(frozen=True)
class Opcao:
    nome: str; item: ItemDeMasmorra; slot: str; catalisado: bool

def montar_opcoes(base, itens, *, ilvl, classe):
    if ilvl not in NIVEL_PARA_BONUS:
        raise ValueError(f"ilvl {ilvl} sem bonus_id conhecido; use {sorted(NIVEL_PARA_BONUS)}.")
    bonus = NIVEL_PARA_BONUS[ilvl]; conjuntos = {}; opcoes = {}
    for item in itens:
        for slot in SLOTS_DUPLOS.get(item.slot, (item.slot,)):
            if base.item_id(slot) == item.item_id: continue
            cru = Candidato(slot=slot, item_id=item.item_id, bonus_id=bonus, bonus_ids=[bonus], ilvl=ilvl, fonte=f"mplus:{item.masmorra}", nome_pt=item.nome_pt)
            variantes = [(cru, False)]
            g = gemeo_catalisado(cru, classe)
            if g is not None: variantes.append((g, True))
            for cand, cat in variantes:
                nome = f"{'k' if cat else 'c'}_{item.item_id}_{slot}"
                conjuntos[nome] = base.com_troca(slot, cand); opcoes[nome] = Opcao(nome, item, slot, cat)
    return conjuntos, opcoes

LIMIAR_PCT = 0.15
def avaliar(leitura, opcoes, *, referencia=None):
    if referencia is None: base, base_erro = leitura.base_dps, leitura.base_erro
    else: base, base_erro = leitura.resultados.get(referencia), leitura.erros.get(referencia)
    if not base or base <= 0: raise ValueError("A leitura não trouxe o DPS de referência.")
    melhor = {}
    for nome, op in opcoes.items():
        dps = leitura.resultados.get(nome)
        if dps is None: continue
        delta = 100.0 * (dps - base) / base
        limiar = _limiar_por_erro(LIMIAR_PCT, base_erro, leitura.erros.get(nome))
        reg = melhor.setdefault(op.item.item_id, {"item": op.item})
        campo = "cat" if op.catalisado else "cru"
        if campo not in reg or delta > reg[campo][0]: reg[campo] = (delta, limiar, op.slot)
    saida = []
    for reg in melhor.values():
        if "cru" not in reg: continue
        d_cru, l_cru, slot = reg["cru"]; d_cat, l_cat, _ = reg.get("cat", (None, None, None))
        saida.append(Avaliacao(reg["item"], d_cru, l_cru, d_cat, l_cat, slot))
    return saida

def rodar_ranking(simular, base, itens, classe, it_triagem=300, it_refino=3000):
    conjuntos, opcoes = montar_opcoes(base, itens, ilvl=341, classe=classe)
    triagem = avaliar(simular(conjuntos, it_triagem), opcoes)
    vivos = {a.item.item_id for a in triagem if a.ganho > -a.limiar_cru}
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    refino = avaliar(simular({n: conjuntos[n] for n in nomes}, it_refino), {n: opcoes[n] for n in nomes})
    refinados = {a.item.item_id for a in refino}
    return refino + [a for a in triagem if a.item.item_id not in refinados], conjuntos, opcoes

# ---- execucao com simulador falso e personagem real ----
p = parse_texto(Path("fixtures/pyrogalth.simc").read_text(encoding="utf-8"))
base = conjunto_do_personagem(p)
itens = [i for i in M.itens_por_masmorra() if M.elegivel(i, tipo_armadura="tecido", atributo="Intelecto")]
import hashlib
chamadas = []
def simular(conjuntos, iterations):
    chamadas.append((len(conjuntos), iterations))
    base_dps = 100000.0 + len(chamadas) * 500  # base DIFERENTE a cada execucao (testa P4)
    res = {}
    for n, c in conjuntos.items():
        h = int(hashlib.md5(n.encode()).hexdigest(), 16) % 700 - 200  # -2,0% .. +5,0%
        bonus_cat = 150 if n.startswith("k_") else 0
        res[n] = base_dps * (1 + (h + bonus_cat) / 10000)
    return LeituraSim(base_dps=base_dps, resultados=res, base_erro=0.3, erros={n: 0.5 for n in res})
av, conjuntos, opcoes = rodar_ranking(simular, base, itens, p.classe)
print("execucoes do simc:", chamadas)
print("profilesets:", len(conjuntos), "| catalisados:", sum(o.catalisado for o in opcoes.values()), "| itens avaliados:", len(av))
from collections import Counter
print("etiquetas:", Counter(a.etiqueta for a in av))
linhas = M.ordenar(M.agrupar(av, Counter(i.masmorra for i in itens)), "quantidade")
for l in linhas[:5]: print(f"  {l['masmorra']:<24} servem {l['servem']}/{l['elegiveis']}  maior {l['maior']:+.2f}%  direto {l['direto']}  catalisar {l['catalisar']}")
print("1o por maior item:", M.ordenar(linhas, "maior")[0]["masmorra"])
try: montar_opcoes(base, itens, ilvl=999, classe=p.classe)
except ValueError as e: print("ilvl invalido recusado:", e)
