"""Measured secondary-stat weights derived from SimulationCraft scale factors.

This is the "evolution" of the curated pruner. When a cached measurement exists
for the character, the heuristic uses it instead of the static table. Deriving
is explicit and never in the hot path: it runs one small simc, normalises the
scale factors to relative weights (max = 1.0) and caches by a gear+talents key.

Golden rule preserved: these weights only *rank* candidates. They never produce
DPS; the measured number continues to come from SimulationCraft.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import simc_runner as sr
from ..models import Personagem
from ..parser.addon import serializar_texto
from .pesos import PesosSpec

DIR = sr.CACHE_DIR / "pesos"
SECUNDARIOS = ("haste", "crit", "mastery", "versatility")
FONTE = "simc:scale_factors"

# Nomes que o simc usa em scale_factors -> nomes do projeto (o simc diz "Vers").
_ALIAS_SIMC = {
    "crit": "crit",
    "haste": "haste",
    "mastery": "mastery",
    "vers": "versatility",
    "versatility": "versatility",
}


def chave_pesos(personagem: Personagem) -> str:
    """Stable key from spec, talents and equipped item ids (gear-dependent)."""
    partes = [
        personagem.classe or "",
        personagem.spec or "",
        personagem.talents_atual or "",
    ]
    for slot in sorted(personagem.equipado):
        item = personagem.equipado[slot]
        partes.append(f"{slot}:{item.item_id}")
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:16]


def _arquivo(personagem: Personagem) -> Path:
    return DIR / f"{chave_pesos(personagem)}.json"


def normalizar_scale_factors(bruto: dict) -> dict[str, float]:
    """Extract the four secondary scale factors and normalise to max = 1.0."""
    sim = bruto.get("sim", bruto)
    if not isinstance(sim, dict):
        return {}
    players = sim.get("players")
    if not isinstance(players, list) or not players:
        return {}
    jogador = players[0] if isinstance(players[0], dict) else {}
    coletado = jogador.get("collected_data", jogador)
    sf = coletado.get("scale_factors", jogador.get("scale_factors")) if isinstance(coletado, dict) else None
    if not isinstance(sf, dict):
        return {}

    saida: dict[str, float] = {}
    for chave, valor in sf.items():
        nome = _ALIAS_SIMC.get(str(chave).strip().lower())
        if nome in SECUNDARIOS and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            saida[nome] = float(valor)
    if not saida:
        return {}
    maior = max(saida.values())
    if maior <= 0:
        return {}
    return {chave: valor / maior for chave, valor in saida.items()}


def salvar_pesos_medidos(
    personagem: Personagem,
    valores: dict[str, float],
    *,
    fonte: str = FONTE,
    metadados: dict | None = None,
) -> PesosSpec:
    DIR.mkdir(parents=True, exist_ok=True)
    dados: dict = {
        "valores": valores,
        "fonte": fonte,
        "classe": personagem.classe,
        "spec": personagem.spec,
    }
    if metadados:
        dados.update(metadados)
    _arquivo(personagem).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return PesosSpec(
        dict(valores), fonte, personagem.classe, personagem.spec, conhecido=True
    )


def carregar_pesos_medidos(personagem: Personagem) -> PesosSpec | None:
    """Cached measured weights, or ``None`` when absent/invalid."""
    try:
        dados = json.loads(_arquivo(personagem).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    valores = dados.get("valores")
    if not isinstance(valores, dict) or not valores:
        return None
    limpos = {
        str(k): float(v)
        for k, v in valores.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    if not limpos:
        return None
    return PesosSpec(
        limpos,
        str(dados.get("fonte") or FONTE),
        personagem.classe,
        personagem.spec,
        conhecido=True,
    )


def derivar_pesos_medidos(
    personagem: Personagem,
    *,
    simc_path: str | Path | None = None,
    iterations: int = 200,
    fight_style: str = "Patchwerk",
    timeout: float = 120.0,
    talentos: str | None = None,
) -> PesosSpec | None:
    """Run one small simc with ``calculate_scale_factors=1`` and cache weights.

    Returns ``None`` (never raises) when the binary is missing, the run fails or
    the JSON has no scale factors — the caller then falls back to the curated
    table.
    """
    DIR.mkdir(parents=True, exist_ok=True)
    perfil = DIR / f"{chave_pesos(personagem)}.simc"
    perfil.write_text(
        serializar_texto(personagem, incluir_checksum=False), encoding="utf-8"
    )
    try:
        extra = ("calculate_scale_factors=1", *([f"talents={talentos}"] if talentos else []))
        execucao = sr.run_simc(
            perfil,
            simc_path=simc_path,
            iterations=iterations,
            fight_style=fight_style,
            timeout=timeout,
            extra_args=extra,
            usar_cache=True,
        )
        resultado = sr.read_results(execucao.json_path)
        valores = normalizar_scale_factors(resultado.bruto)
    except Exception:  # noqa: BLE001 - any simc failure falls back to curated
        return None
    if not valores:
        return None
    base_dps = resultado.base.dps if resultado.base is not None else None
    return salvar_pesos_medidos(
        personagem,
        valores,
        metadados={
            "iteracoes": iterations,
            "fight_style": fight_style,
            "talentos": talentos,
            "base_dps": base_dps,
        },
    )
