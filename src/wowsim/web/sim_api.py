"""Bridge the React UI to real SimulationCraft runs.

The React ``simcExporter`` produces a ``.simc`` profile string. These helpers
write it to a temp file, run the real ``simc`` binary and read the DPS back.
Numbers here are always measured, never estimated.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .. import simc_runner
from ..simc_runner import ResultadoDps, SimcExecucao, SimcFalhou

# Scenario name (from the React app) to simc fight parameters.
CENARIOS: dict[str, dict] = {
    "patchwerk": {"fight_style": "Patchwerk", "desired_targets": 1},
    "raid": {"fight_style": "Patchwerk", "desired_targets": 1},
    "dungeon_slice": {"fight_style": "DungeonSlice"},
    "mplus": {"fight_style": "DungeonSlice"},
    "cleave_aoe": {"fight_style": "DungeonSlice"},
    "delve_rooms": {"fight_style": "DungeonSlice"},
    "delve_boss": {"fight_style": "Patchwerk", "desired_targets": 1},
}


def parametros_cenario(scenario: str | None, iterations: int, threads: int | None = None) -> dict:
    chave = (scenario or "patchwerk").lower()
    base = dict(CENARIOS.get(chave, CENARIOS["patchwerk"]))
    base["iterations"] = int(iterations)
    base["threads"] = threads if threads is not None else simc_runner.threads_padrao()
    return base


def _rodar_texto(
    texto: str,
    scenario: str | None,
    iterations: int,
    simc_path: str | Path | None = None,
) -> tuple[ResultadoDps, SimcExecucao]:
    params = parametros_cenario(scenario, iterations)
    with tempfile.TemporaryDirectory() as pasta:
        perfil = Path(pasta) / "perfil.simc"
        perfil.write_text(texto, encoding="utf-8")
        execucao = simc_runner.run_simc(perfil, simc_path=simc_path, **params)
        resultado = simc_runner.read_results(execucao.json_path)
    if resultado.base is None:
        raise SimcFalhou("O simc não retornou o DPS da base.")
    return resultado.base, execucao


def _meta(execucao: SimcExecucao) -> dict:
    return {
        "cache_hit": execucao.cache_hit,
        "duracao_s": round(execucao.duracao_s, 3),
        "build": execucao.info.build,
        "versao": execucao.info.versao,
        "comando": list(execucao.comando),
    }


def rodar_perfil(
    texto: str,
    scenario: str | None = "patchwerk",
    iterations: int = 200,
    simc_path: str | Path | None = None,
) -> dict:
    base, execucao = _rodar_texto(texto, scenario, iterations, simc_path)
    return {
        "dps": round(base.dps, 2),
        "erro_pct": None if base.erro_pct is None else round(base.erro_pct, 3),
        "amostras": base.amostras,
        "cenario": scenario or "patchwerk",
        "meta": _meta(execucao),
    }


def classificar(delta_pct: float, erro_base: float | None, erro_cand: float | None) -> tuple[str, float]:
    """Error-aware verdict. Threshold is the largest error but at least 0.15%."""
    limiar = max(erro_base or 0.0, erro_cand or 0.0, 0.15)
    if delta_pct > limiar:
        return "Vale a troca", limiar
    if delta_pct < -limiar:
        return "Não vale", limiar
    return "Empate técnico — simular", limiar


def comparar(
    base_text: str,
    candidate_text: str,
    scenario: str | None = "patchwerk",
    iterations: int = 200,
    simc_path: str | Path | None = None,
) -> dict:
    base, exec_base = _rodar_texto(base_text, scenario, iterations, simc_path)
    candidato, exec_cand = _rodar_texto(candidate_text, scenario, iterations, simc_path)
    delta = 100.0 * (candidato.dps - base.dps) / base.dps if base.dps else 0.0
    veredito, limiar = classificar(delta, base.erro_pct, candidato.erro_pct)
    return {
        "cenario": scenario or "patchwerk",
        "base_dps": round(base.dps, 2),
        "candidate_dps": round(candidato.dps, 2),
        "delta_pct": round(delta, 3),
        "limiar_pct": round(limiar, 3),
        "veredito": veredito,
        "erro_base_pct": None if base.erro_pct is None else round(base.erro_pct, 3),
        "erro_cand_pct": None if candidato.erro_pct is None else round(candidato.erro_pct, 3),
        "meta": {
            "base": _meta(exec_base),
            "candidate": _meta(exec_cand),
        },
    }
