"""Profileset generation and SimulationCraft execution for Top Gear.

The search engine never talks to ``simc`` directly: it receives a
``SimuladorTopGear`` callable. That keeps the algorithm unit-testable with a
fake simulator while the real runner reuses ``simc_runner`` (cache included).
"""

from __future__ import annotations

import hashlib
import itertools
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .. import simc_runner as sr
from ..data import catalog
from .. import calibracao
from ..gen.profilesets import estimar_segundos
from ..models import Personagem
from ..parser.addon import serializar_texto
from .models import Candidato, Conjunto


@dataclass(frozen=True)
class LeituraSim:
    """DPS read from one simc run. All values are measured.

    ``base_erro``/``erros`` carry the measured simulation error so the search
    can use the real noise floor instead of a fixed 0.15%.
    """

    base_dps: float | None
    resultados: dict[str, float]
    avisos: tuple[str, ...] = ()
    base_erro: float | None = None
    erros: dict[str, float] = field(default_factory=dict)


SimuladorTopGear = Callable[[Mapping[str, Conjunto], int], LeituraSim]


def estilo_de_luta(scenario: str) -> str:
    """Map the request scenario name to the simc fight style.

    Cobre os Fight Styles do Raidbots que o SimulationCraft suporta. Estilos
    desconhecidos caem em ``Patchwerk`` (alvo único, sem movimento).
    """
    mapa = {
        "patchwerk": "Patchwerk",
        "dungeon_slice": "DungeonSlice",
        "raid": "DungeonSlice",
        "mplus": "DungeonSlice",
        "cleave_aoe": "DungeonSlice",
        "delve_rooms": "DungeonSlice",
        "delve_boss": "Patchwerk",
        # Fight Styles extras (validados no binário local do SimC).
        "hectic_add_cleave": "HecticAddCleave",
        "light_movement": "LightMovement",
        "heavy_movement": "HeavyMovement",
        "casting_patchwerk": "CastingPatchwerk",
        "cleave_add": "CleaveAdd",
        "helter_skelter": "HelterSkelter",
    }
    return mapa.get((scenario or "").strip().lower(), "Patchwerk")


def _linha_item(candidato: Candidato) -> str:
    partes = [f"{candidato.slot}="]
    if candidato.item_id is not None:
        partes.append(f"id={candidato.item_id}")
    if candidato.enchant_id is not None:
        partes.append(f"enchant_id={candidato.enchant_id}")
    if candidato.gem_ids:
        partes.append("gem_id=" + "/".join(str(gema) for gema in candidato.gem_ids))
    bonus = candidato.bonus_ids or (
        [candidato.bonus_id] if candidato.bonus_id is not None else []
    )
    if bonus:
        partes.append("bonus_id=" + "/".join(str(b) for b in bonus))
    if candidato.redirected_base_stats:
        partes.append(f"redirected_base_stats={candidato.redirected_base_stats}")
    if candidato.ilevel:
        partes.append(f"ilevel={candidato.ilevel}")
    if candidato.crafted_stats:
        partes.append("crafted_stats=" + "/".join(str(s) for s in candidato.crafted_stats))
    if candidato.embelezamento_simc:
        partes.append(f"embellishment={candidato.embelezamento_simc}")
    return ",".join(partes)


def _entradas_folio() -> dict[str, int]:
    return {
        runa.escolha: runa.id_entrada
        for runa in catalog.runas_folio()
        if runa.id_entrada is not None
    }


def _chave_conjunto_texto(conjunto: Conjunto) -> str:
    """Content-stable key for a set, independent of dict insertion order."""
    linhas = sorted(linhas_override(conjunto))
    return hashlib.sha1("\n".join(linhas).encode("utf-8")).hexdigest()[:16]


def conjuntos_estaveis(
    candidatos: Mapping[str, Conjunto],
) -> dict[str, Conjunto]:
    """Rename candidates by content hash so identical sets reuse the simc cache.

    Two batches with the same loadouts (even in a different order or under
    different round labels) now produce byte-identical profileset files, which
    makes ``chave_cache`` stable and avoids re-running simc for repeat sets.
    """
    estaveis: dict[str, Conjunto] = {}
    for conjunto in candidatos.values():
        estaveis.setdefault(_chave_conjunto_texto(conjunto), conjunto)
    return estaveis


def linhas_override(conjunto: Conjunto) -> list[str]:
    """One simc override line per changed slot, plus talents and folio."""
    linhas: list[str] = []
    for candidato in conjunto.itens.values():
        if candidato.item_id is None and candidato.enchant_id is None:
            continue
        linhas.append(_linha_item(candidato))

    if conjunto.talentos:
        linhas.append(f"talents={conjunto.talentos}")

    if conjunto.runas_folio:
        mapa = _entradas_folio()
        ids = [mapa[runa] for runa in conjunto.runas_folio if runa in mapa]
        if len(ids) == len(conjunto.runas_folio) and ids:
            linhas.append("omnium_talents=" + "/".join(f"{entrada}:1" for entrada in ids))

    for campo in ("flask", "potion", "food", "augmentation"):
        valor = getattr(conjunto, campo)
        if valor:
            linhas.append(f"{campo}={valor}")

    return linhas


def escrever_rodada(
    personagem: Personagem,
    candidatos: Mapping[str, Conjunto],
    destino: str | Path,
) -> Path:
    """Write the character profile plus one profileset block per candidate."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    linhas = [serializar_texto(personagem, incluir_checksum=False).rstrip(), ""]
    for nome, conjunto in candidatos.items():
        overrides = linhas_override(conjunto)
        if not overrides:
            continue
        for linha in overrides:
            linhas.append(f'profileset."{nome}"+={linha}')
    linhas.append("")

    caminho.write_text("\n".join(linhas), encoding="utf-8")
    return caminho


LIMITE_PROFILESETS_TARGET_ERROR = 25


def erro_alvo_efetivo(
    target_error: float | None, n_profilesets: int
) -> float | None:
    """Aplica ``target_error`` só quando há poucos profilesets.

    Com muitos profilesets no mesmo arquivo, o ``target_error`` faz o simc rodar
    iterações extras por profile até atingir o erro, o que explode o tempo e
    estoura o orçamento. Em lotes grandes, limitamos pelas ``iterations``.
    """
    if target_error is None:
        return None
    # n_profilesets == 0 é a medição da base: ``target_error`` ali faz o simc
    # girar até o max_time (variância alta), então rodamos só ``iterations``.
    if n_profilesets <= 0:
        return None
    return target_error if n_profilesets <= LIMITE_PROFILESETS_TARGET_ERROR else None


@dataclass(frozen=True)
class Preflight:
    """Resultado do pré-voo: detecta cedo um simc travado/quebrado."""

    ok: bool
    dps: float | None
    duracao_s: float
    erro: str | None = None
    avisos: tuple[str, ...] = ()


def preflight(
    personagem: Personagem,
    *,
    simc_path: str | Path | None = None,
    fight_style: str = "Patchwerk",
    threads: int | None = None,
    iterations: int = 5,
    timeout: float = 20.0,
    pasta: str | Path | None = None,
) -> Preflight:
    """Roda uma simulação minúscula da base antes do job de verdade.

    Se o ``simc`` travar ou falhar neste perfil, gastamos segundos — não os
    minutos do Top Gear completo. Nunca levanta; devolve ``ok=False``.
    """
    pasta_destino = Path(pasta) if pasta is not None else sr.CACHE_DIR / "topgear"
    texto = serializar_texto(personagem, incluir_checksum=False)
    chave = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]
    destino = pasta_destino / f"preflight_{chave}.simc"
    escrever_rodada(personagem, {}, destino)
    inicio = time.monotonic()
    try:
        execucao = sr.run_simc(
            destino,
            simc_path=simc_path,
            iterations=iterations,
            fight_style=fight_style,
            threads=threads,
            timeout=timeout,
            max_time=max(1, int(timeout) - 2),
            usar_cache=False,
        )
        lido = sr.read_results(execucao.json_path)
        base = lido.base.dps if lido.base is not None else None
        if base is None:
            return Preflight(
                ok=False,
                dps=None,
                duracao_s=execucao.duracao_s,
                erro="O simc não devolveu o DPS da base.",
                avisos=lido.avisos,
            )
        return Preflight(
            ok=True, dps=base, duracao_s=execucao.duracao_s, avisos=lido.avisos
        )
    except sr.SimcError as exc:
        return Preflight(
            ok=False, dps=None, duracao_s=time.monotonic() - inicio, erro=str(exc)
        )


def estimar_custo(
    pools: Mapping[str, list[Candidato]],
    *,
    iterations: int,
    orcamento_segundos: int,
    target_error: float | None = None,
    max_profilesets_rodada: int | None = None,
) -> dict:
    """Estima profilesets e tempo antes do Run (P0 — custo visível).

    A conta é conservadora: uma rodada marginal (todos os candidatos), a
    montagem gulosa por slot e uma folga para beam/refino. Serve para avisar o
    usuário antes de disparar um job que estouraria o orçamento.
    """
    n_candidatos = sum(len(lista) for lista in pools.values())
    n_slots = sum(1 for lista in pools.values() if lista)
    total = n_candidatos + n_slots * 4
    limite = max_profilesets_rodada or total
    por_rodada = min(total, limite) if total else 0
    erro = erro_alvo_efetivo(target_error, por_rodada)
    segundos = estimar_segundos(total, iterations) if total else 0.0
    avisos: list[str] = []
    if target_error is not None and erro is None:
        avisos.append(
            "Erro-alvo ignorado nesta rodada: lote grande demais. "
            "Reduza as pools para o simc parar pelo erro."
        )
    excede = segundos > orcamento_segundos
    if excede:
        avisos.append(
            f"Estimativa de ~{segundos:.0f}s excede o orçamento de "
            f"{orcamento_segundos}s. Aumente o orçamento ou reduza pools/iterações."
        )
    return {
        "profilesets_total_estimado": total,
        "segundos_estimados": round(segundos, 1),
        "excede_orcamento": excede,
        "target_error_aplicado": erro,
        "target_error_ignorado": target_error is not None and erro is None,
        "avisos": avisos,
    }


def criar_simulador(
    personagem: Personagem,
    *,
    fight_style: str = "Patchwerk",
    threads: int | None = None,
    target_error: float | None = None,
    simc_path: str | Path | None = None,
    usar_cache: bool = True,
    pasta: str | Path | None = None,
    cancelar: Callable[[], bool] | None = None,
    orcamento_restante: Callable[[], float | None] | None = None,
) -> SimuladorTopGear:
    """Return a simulator that writes profilesets and calls the real simc.

    ``cancelar`` permite matar o simc no meio de uma rodada; ``orcamento_restante``
    vira o timeout de cada chamada para o orçamento total ser respeitado.
    """
    contador = itertools.count(1)
    destino_pasta = Path(pasta) if pasta is not None else sr.CACHE_DIR / "topgear"

    def executar(candidatos: Mapping[str, Conjunto], iterations: int) -> LeituraSim:
        destino = destino_pasta / f"rodada_{next(contador):04d}.simc"
        # Write content-stable profileset names, then map the readings back to
        # the caller's names so the search keeps its own labels.
        estaveis = conjuntos_estaveis(candidatos)
        escrever_rodada(personagem, estaveis, destino)
        restante = (
            orcamento_restante() if orcamento_restante is not None else None
        )
        timeout = max(1.0, restante) if restante is not None else 3600.0
        erro_efetivo = erro_alvo_efetivo(target_error, len(candidatos))
        sr._log_simc(
            f"rodada: profilesets={len(candidatos)} iterations={iterations} "
            f"timeout={timeout:.0f}s target_error={erro_efetivo}"
        )
        execucao = sr.run_simc(
            destino,
            simc_path=simc_path,
            iterations=iterations,
            fight_style=fight_style,
            threads=threads,
            target_error=erro_efetivo,
            timeout=timeout,
            cancelar=cancelar,
            usar_cache=usar_cache,
        )
        sr._log_simc(
            f"rodada concluida em {execucao.duracao_s:.2f}s "
            f"(cache_hit={execucao.cache_hit})"
        )
        if not execucao.cache_hit:
            # Velocidade real desta máquina, para as próximas estimativas.
            calibracao.registrar(fight_style, len(candidatos) + 1, iterations, execucao.duracao_s)
        lido = sr.read_results(execucao.json_path)
        base = lido.base.dps if lido.base is not None else None
        base_erro = lido.base.erro_pct if lido.base is not None else None

        dps_por_chave = {variacao.nome: variacao.dps for variacao in lido.variacoes}
        erro_por_chave = {
            variacao.nome: variacao.erro_pct
            for variacao in lido.variacoes
            if variacao.erro_pct is not None
        }

        resultados: dict[str, float] = {}
        erros: dict[str, float] = {}
        for nome, conjunto in candidatos.items():
            chave = _chave_conjunto_texto(conjunto)
            if chave in dps_por_chave:
                resultados[nome] = dps_por_chave[chave]
            if chave in erro_por_chave:
                erros[nome] = erro_por_chave[chave]

        return LeituraSim(
            base_dps=base,
            resultados=resultados,
            avisos=lido.avisos,
            base_erro=base_erro,
            erros=erros,
        )

    return executar
