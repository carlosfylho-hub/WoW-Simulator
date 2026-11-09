"""Sonda curta no simc para descobrir os atributos reais de peças craftadas.

A peça craftada não existe em ``stats_oficiais_itens.json`` (que só cobre drops);
os secundários vêm da missiva e o valor, do ilvl. O simc, porém, já calcula esse
item e escreve ``players[i].gear.<slot>`` com ``ilevel``/``crafted_stats``
aplicados (``report_json.cpp::gear_to_json``). Rodamos uma cópia do personagem
por candidato (``copy=``), ``iterations=1`` e ``max_time=1``, e lemos o bloco.

Nada é estimado: os números são os que o simc escreveu. É só para a tooltip; o
ganho de dano continua vindo das leituras normais (P1).
"""

from __future__ import annotations

import hashlib
import json

from .. import simc_runner as sr
from ..parser.addon import serializar_texto
from ..topgear.models import Candidato
from ..topgear.runner import _linha_item

# Chaves do simc (stat_type_string) -> chaves do projeto.
MAPA_STATS = {
    "crit_rating": "crit",
    "haste_rating": "haste",
    "mastery_rating": "mastery",
    "versatility_rating": "versatility",
    "intellect": "intellect",
    "strength": "strength",
    "agility": "agility",
    "stamina": "stamina",
}


def stats_do_gear(gear: dict) -> dict[str, int]:
    """Atributos de um item do bloco ``gear`` do simc, nas chaves do projeto."""
    fonte = gear.get("stats") if isinstance(gear.get("stats"), dict) else gear
    saida: dict[str, int] = {}
    for chave, valor in fonte.items():
        projeto = MAPA_STATS.get(str(chave))
        if projeto and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            saida[projeto] = int(valor)
    return saida


def stats_das_players(
    players: list, candidatos: dict[str, Candidato]
) -> dict[str, dict[str, int]]:
    """Mapeia cada candidato (``sonda_i``) ao seu ``gear[slot]`` em ``players``.

    ``players[0]`` é o personagem original; ``players[i+1]`` é a sonda ``i``.
    """
    saida: dict[str, dict[str, int]] = {}
    for i, nome in enumerate(candidatos):
        indice = i + 1
        if indice >= len(players):
            continue
        jogador = players[indice]
        if not isinstance(jogador, dict):
            continue
        gear = jogador.get("gear")
        if not isinstance(gear, dict):
            continue
        entrada = gear.get(candidatos[nome].slot)
        if isinstance(entrada, dict):
            saida[nome] = stats_do_gear(entrada)
    return saida


def _linhas_sonda(
    personagem, candidatos: dict[str, Candidato]
) -> list[str]:
    linhas = [serializar_texto(personagem, incluir_checksum=False).rstrip()]
    for i, nome in enumerate(candidatos):
        linhas.append(f"copy=sonda_{i}")
        linhas.append(_linha_item(candidatos[nome]))
    return linhas


def sondar_atributos(
    personagem,
    candidatos: dict[str, Candidato],
    *,
    fight_style: str = "Patchwerk",
    simc_path=None,
) -> dict[str, dict[str, int]]:
    """nome -> {"crit": 812, "haste": 640, "intellect": 1404, ...}."""
    if not candidatos:
        return {}
    linhas = _linhas_sonda(personagem, candidatos)
    chave = hashlib.sha1("\n".join(linhas).encode("utf-8")).hexdigest()[:16]
    arquivo = sr.CACHE_DIR / "sonda" / f"{chave}.simc"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    execucao = sr.run_simc(
        arquivo,
        simc_path=simc_path,
        iterations=1,
        fight_style=fight_style,
        extra_args=["max_time=1"],
    )
    bruto = sr.read_results(execucao.json_path).bruto
    sim = bruto.get("sim", bruto) if isinstance(bruto, dict) else {}
    players = sim.get("players") if isinstance(sim, dict) else None
    if not isinstance(players, list):
        return {}
    return stats_das_players(players, candidatos)
