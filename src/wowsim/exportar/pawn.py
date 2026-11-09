"""String de escala do Pawn a partir dos scale factors do simc."""
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


# --------------------------------------------------------------------------
# Escalas por build e "Mistura" (T11). Funções puras: recebem o que o simc mediu
# (fatores em DPS por ponto, erro de cada fator, DPS da base) e nada estimam.

import math


def nome_pawn(texto: str) -> str:
    """Nome de classe/spec como o Pawn aceita: 'death_knight' -> 'DeathKnight'."""
    return "".join(parte.capitalize() for parte in str(texto).replace("-", "_").split("_") if parte)


def nome_escala(texto: str, limite: int = 60) -> str:
    """Nome da escala sem aspas nem parênteses (o parser do Pawn não aceita)."""
    limpo = " ".join(_PROIBIDO.sub("", texto or "").split())
    return (limpo or "WSIM")[:limite]


def erros_relativos(erros: dict[str, float], dps: float) -> dict[str, float]:
    """Erro do fator (DPS por ponto) -> erro em % do DPS por ponto, nomes do Pawn."""
    if dps <= 0:
        raise ValueError("DPS da base precisa ser positivo para normalizar.")
    return {SIMC_PARA_PAWN[k]: 100.0 * v / dps for k, v in erros.items() if k in SIMC_PARA_PAWN}


def quase_iguais(
    a: dict[str, float], erro_a: dict[str, float], b: dict[str, float], erro_b: dict[str, float]
) -> bool:
    """Duas escalas (já relativas) iguais dentro do erro somado (~95%).

    Sem erro medido para algum atributo, não dá para afirmar: devolve False.
    """
    if set(a) != set(b) or not a:
        return False
    for k in a:
        if k not in erro_a or k not in erro_b:
            return False
        if abs(a[k] - b[k]) > 2.0 * math.sqrt(erro_a[k] ** 2 + erro_b[k] ** 2):
            return False
    return True


def escalas_das_builds(
    medicoes: dict[str, object],
    pesos: dict[str, float],
    *,
    personagem: str,
    classe: str | None,
    spec: str | None,
) -> dict:
    """Uma string do Pawn por build + a "Mistura" ponderada.

    ``medicoes``: build -> objeto com ``dps``, ``fatores`` e ``erros`` (ex.:
    ``EscalaMedida``). ``pesos``: build -> peso (normalizados aqui).
    """
    classe_pawn = nome_pawn(classe) if classe else None
    spec_pawn = nome_pawn(spec) if spec else None
    relativos: dict[str, dict[str, float]] = {}
    erros: dict[str, dict[str, float]] = {}
    saida_builds: dict[str, dict] = {}
    for build, m in medicoes.items():
        rel = pesos_relativos(m.fatores, m.dps)  # type: ignore[attr-defined]
        relativos[build] = rel
        erros[build] = erros_relativos(m.erros, m.dps)  # type: ignore[attr-defined]
        saida_builds[build] = {
            "string": string_pawn(
                nome_escala(f"{personagem} - {build}"), rel, classe=classe_pawn, spec=spec_pawn
            ),
            "pesos_pct_por_ponto": rel,
            "erros_pct_por_ponto": erros[build],
        }

    iguais: list[list[str]] = []
    nomes = list(medicoes)
    for i, x in enumerate(nomes):
        for y in nomes[i + 1:]:
            if quase_iguais(relativos[x], erros[x], relativos[y], erros[y]):
                iguais.append([x, y])

    mistura = None
    if len(medicoes) >= 2:
        total = sum(max(0.0, pesos.get(b, 0.0)) for b in nomes)
        w = {b: (max(0.0, pesos.get(b, 0.0)) / total if total > 0 else 1.0 / len(nomes)) for b in nomes}
        misturado = misturar([(relativos[b], w[b]) for b in nomes])
        # Sem Spec: a Mistura vale para qualquer build da classe (Pawn.lua:3071).
        mistura = string_pawn(nome_escala(f"{personagem} - Mistura"), misturado, classe=classe_pawn)

    return {"builds": saida_builds, "mistura": mistura, "iguais": iguais}
