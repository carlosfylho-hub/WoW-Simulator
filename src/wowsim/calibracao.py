"""Velocidade medida do simc nesta máquina, por estilo de luta (para estimativas).

Cada rodada real (sem cache) grava ``segundos / (perfis × iterações)``; a
estimativa usa a média móvel dessa taxa. Antes de qualquer medição, valem os
padrões medidos no PC do usuário em 2026-11-08 (19 threads): Patchwerk
~0,0014 s e DungeonSlice ~0,0040 s por perfil·iteração — o DungeonSlice é
~2,5–3× mais lento, e a estimativa antiga ignorava isso (dizia 13 min, levou 20+).
"""

from __future__ import annotations

import json
from pathlib import Path

PADRAO = {"Patchwerk": 0.0014, "DungeonSlice": 0.0040}
TAXA_GENERICA = 0.0013  # a estimativa antiga; vale para estilos sem padrão medido
PESO_NOVA = 0.5          # média móvel: metade a medição nova, metade o histórico
MINIMO_TRABALHO = 2_000  # perfis × iterações: abaixo disso o custo fixo distorce


def _arquivo() -> Path:
    from .simc_runner import CACHE_DIR  # import tardio: evita ciclo

    return CACHE_DIR / "calibracao.json"


def _ler() -> dict[str, float]:
    try:
        dados = json.loads(_arquivo().read_text(encoding="utf-8"))
        return {k: float(v) for k, v in dados.items() if isinstance(v, (int, float)) and v > 0}
    except (OSError, ValueError):
        return {}


def taxa(fight_style: str | None) -> float:
    """Segundos por perfil·iteração para o estilo de luta."""
    estilo = fight_style or "Patchwerk"
    return _ler().get(estilo) or PADRAO.get(estilo, TAXA_GENERICA)


def registrar(fight_style: str | None, perfis: int, iteracoes: int, segundos: float) -> None:
    """Atualiza a taxa com uma rodada real. Nunca levanta erro."""
    trabalho = max(0, perfis) * max(0, iteracoes)
    if not fight_style or trabalho < MINIMO_TRABALHO or segundos <= 0:
        return
    nova = segundos / trabalho
    try:
        dados = _ler()
        anterior = dados.get(fight_style)
        dados[fight_style] = nova if anterior is None else anterior * (1 - PESO_NOVA) + nova * PESO_NOVA
        arquivo = _arquivo()
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    except OSError:
        pass
