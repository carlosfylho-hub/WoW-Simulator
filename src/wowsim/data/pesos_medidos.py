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


# --------------------------------------------------------------------------
# Escala do Pawn por build (T11 / P-044).
#
# Diferente de ``derivar_pesos_medidos`` (que alimenta só a poda e normaliza os
# secundários para máximo = 1), aqui guardamos os scale factors CRUS — DPS por
# ponto, Intelecto incluso —, o DPS da base e o erro, por build (talentos na
# chave). Sem isso não dá para converter em % do DPS por ponto e misturar builds.
# A poda continua usando só os pesos curados (A-12).

import math
from dataclasses import dataclass

STATS_ESCALA = ("Int", "Crit", "Haste", "Mastery", "Vers")
MIN_ITERACOES_ESCALA = 5_000


@dataclass(frozen=True)
class EscalaMedida:
    talentos: str | None
    fight_style: str
    iteracoes: int
    dps: float
    dps_erro: float                 # mean_std_dev da base (DPS absoluto)
    fatores: dict[str, float]       # "Int"/"Crit"/... -> DPS por ponto
    erros: dict[str, float]         # mesma chave -> erro do fator (DPS por ponto)


def ler_escala(bruto: dict) -> tuple[float, float, dict[str, float], dict[str, float]]:
    """DPS, erro do DPS, scale factors e erro de cada fator a partir do JSON do simc.

    O erro do fator vem de ``scale_factor_control.cpp``: com ``center_scale_delta``
    desligado (padrão) o fator é (DPS_com_delta − DPS_base) / delta, então o erro é
    √2 · erro_do_DPS / delta.
    """
    sim = bruto.get("sim", bruto)
    jogadores = sim.get("players") if isinstance(sim, dict) else None
    if not isinstance(jogadores, list) or not jogadores or not isinstance(jogadores[0], dict):
        raise ValueError("JSON do simc sem jogador.")
    jogador = jogadores[0]
    sf = jogador.get("scale_factors")
    if not isinstance(sf, dict) or not sf:
        raise ValueError("JSON do simc sem scale_factors (rode com calculate_scale_factors=1).")
    deltas = jogador.get("scale_deltas") if isinstance(jogador.get("scale_deltas"), dict) else {}
    dps_no = (jogador.get("collected_data") or {}).get("dps") or {}
    dps = float(dps_no.get("mean") or 0.0)
    dps_erro = float(dps_no.get("mean_std_dev") or 0.0)
    if dps <= 0:
        raise ValueError("JSON do simc sem DPS da base.")
    fatores = {
        k: float(v)
        for k, v in sf.items()
        if k in STATS_ESCALA and isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    erros = {
        k: math.sqrt(2.0) * dps_erro / abs(float(deltas[k]))
        for k in fatores
        if isinstance(deltas.get(k), (int, float)) and float(deltas[k]) != 0.0
    }
    return dps, dps_erro, fatores, erros


def chave_escala(
    personagem: Personagem, talentos: str | None, fight_style: str, iteracoes: int
) -> str:
    """Uma medição por equipamento + build + cenário + iterações."""
    partes = [chave_pesos(personagem), talentos or "", fight_style, str(int(iteracoes))]
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:16]


def medir_escala(
    personagem: Personagem,
    *,
    talentos: str | None,
    fight_style: str,
    iterations: int = MIN_ITERACOES_ESCALA,
    threads: int | None = None,
    timeout: float | None = None,
    cancelar=None,
    simc_path: str | Path | None = None,
) -> EscalaMedida:
    """Roda o simc com ``calculate_scale_factors=1`` para UMA build e grava o resultado.

    Levanta erro em vez de cair num valor padrão: uma escala inventada no Pawn é
    pior que nenhuma.
    """
    if iterations < MIN_ITERACOES_ESCALA:
        raise ValueError(
            f"Escala do Pawn exige pelo menos {MIN_ITERACOES_ESCALA} iterações "
            f"(pedido: {iterations})."
        )
    DIR.mkdir(parents=True, exist_ok=True)
    chave = chave_escala(personagem, talentos, fight_style, iterations)
    perfil = DIR / f"escala_{chave}.simc"
    perfil.write_text(serializar_texto(personagem, incluir_checksum=False), encoding="utf-8")
    extra = [
        "calculate_scale_factors=1",
        "scale_only=" + ",".join(STATS_ESCALA),
        *([f"talents={talentos}"] if talentos else []),
    ]
    execucao = sr.run_simc(
        perfil,
        simc_path=simc_path,
        iterations=iterations,
        fight_style=fight_style,
        threads=threads,
        extra_args=extra,
        timeout=timeout if timeout is not None else 3600.0,
        cancelar=cancelar,
        usar_cache=True,
    )
    resultado = sr.read_results(execucao.json_path)
    dps, dps_erro, fatores, erros = ler_escala(resultado.bruto)
    medida = EscalaMedida(talentos, fight_style, iterations, dps, dps_erro, fatores, erros)
    (DIR / f"escala_{chave}.json").write_text(
        json.dumps(
            {
                "iteracoes": iterations,
                "fight_style": fight_style,
                "talentos": talentos,
                "base_dps": dps,
                "base_dps_erro": dps_erro,
                "fatores": fatores,
                "erros": erros,
                "fonte": FONTE,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return medida
