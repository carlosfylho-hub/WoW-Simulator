# REFERÊNCIA VALIDADA — docs/WORKFLOW-IMPLEMENTACAO.md explica onde e como usar.
# Não é importado pelo pacote. Foi rodado contra fixtures/ reais em 2026-11-08.
"""Prototipo: string de escala do Pawn a partir dos scale factors do simc."""
from __future__ import annotations
import re

# Chave do scale factor no JSON do simc -> nome da estatistica no Pawn.
SIMC_PARA_PAWN = {"Int": "Intellect", "Crit": "CritRating", "Haste": "HasteRating",
                  "Mastery": "MasteryRating", "Vers": "Versatility"}
_PROIBIDO = re.compile(r'["()]')  # o parser do Pawn nao aceita aspas nem parenteses no nome

def pesos_relativos(scale_factors: dict[str, float], dps: float) -> dict[str, float]:
    """DPS por ponto -> % do DPS por ponto. Torna specs de DPS diferente comparaveis."""
    if dps <= 0:
        raise ValueError("DPS da base precisa ser positivo para normalizar.")
    return {SIMC_PARA_PAWN[k]: 100.0 * v / dps for k, v in scale_factors.items() if k in SIMC_PARA_PAWN}

def misturar(perfis: list[tuple[dict[str, float], float]]) -> dict[str, float]:
    """Media ponderada de pesos ja relativos. Pesos de mistura somam 1."""
    total = sum(peso for _, peso in perfis)
    if total <= 0:
        raise ValueError("A soma dos pesos da mistura deve ser positiva.")
    chaves = set().union(*(p.keys() for p, _ in perfis))
    return {k: sum(p.get(k, 0.0) * w for p, w in perfis) / total for k in chaves}

def string_pawn(nome: str, pesos: dict[str, float], *, classe: str | None = None,
                spec: str | None = None, escala_max: float = 10.0) -> str:
    """Formata ( Pawn: v1: "nome": Class=..., Spec=..., Stat=valor, ... ).

    Os valores sao reescalados para o maior virar ``escala_max`` (o Pawn so usa a
    proporcao entre eles) e arredondados a 2 casas.
    """
    if _PROIBIDO.search(nome):
        raise ValueError('O nome da escala nao pode conter aspas nem parenteses.')
    maior = max(pesos.values())
    partes = []
    if classe: partes.append(f"Class={classe}")
    if classe and spec: partes.append(f"Spec={spec}")
    for stat in ("Intellect", "CritRating", "HasteRating", "MasteryRating", "Versatility"):
        if stat in pesos:
            partes.append(f"{stat}={round(pesos[stat] / maior * escala_max, 2)}")
    return f'( Pawn: v1: "{nome}": ' + ", ".join(partes) + " )"

# Port do regex de PawnParseScaleTag (AddOns/Pawn/Pawn.lua:3071) para validar a saida.
_PAWN_TAG = re.compile(r'^\s*\(\s*Pawn\s*:\s*v(\d+)\s*:\s*"([^"]+)"\s*:\s*(.+)\s*\)\s*$')
_PAR = re.compile(r'^\s*([A-Za-z\d]+)\s*=\s*(-?[\d.a-zA-Z]+)\s*$')
def validar_como_pawn(tag: str) -> tuple[str, dict[str, str]]:
    m = _PAWN_TAG.match(tag)
    if not m: raise ValueError("Formato rejeitado pelo Pawn.")
    valores = {}
    for par in m.group(3).split(","):
        mp = _PAR.match(par)
        if not mp: raise ValueError(f"Par invalido: {par!r}")
        valores[mp.group(1)] = mp.group(2)
    return m.group(2), valores
