"""Resumo determinístico do resultado (sem LLM).

A integração com a DeepSeek foi removida em 2026-11-09 (decisão do usuário): o
resumo é montado só com os números já medidos pelo simc. ``validar_numeros``
fica como verificação de que um texto não traz número fora do contexto.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..gen import profilesets
from ..models import Variacao
from ..simc_runner import ResultadoDps, SimcResultado

PISO_ERRO = 0.15
_NUMERO_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _erro(resultado: ResultadoDps | None) -> float:
    if resultado is None or resultado.erro_pct is None:
        return PISO_ERRO
    return max(PISO_ERRO, resultado.erro_pct)


def _veredito(delta: float, erro: float) -> str:
    if abs(delta) < erro:
        return "empate"
    return "ganho" if delta > 0 else "perda"


def montar_contexto(
    resultado: SimcResultado,
    variacoes: Iterable[Variacao],
    *,
    iterations: int,
    fight_style: str,
) -> dict[str, Any]:
    if resultado.base is None:
        raise ValueError("Sem DPS da base não há contexto para o resumo.")
    base = resultado.base.dps
    por_nome = {variacao.nome: variacao for variacao in variacoes}
    itens = []
    for entrada in resultado.variacoes:
        variacao = por_nome.get(entrada.nome)
        delta = 100.0 * (entrada.dps - base) / base
        erro = max(_erro(resultado.base), _erro(entrada))
        itens.append(
            {
                "nome": entrada.nome,
                "categoria": variacao.categoria if variacao else "desconhecida",
                "dps": round(entrada.dps, 2),
                "delta_pct": round(delta, 2),
                "erro_pct": round(erro, 2),
                "veredito": _veredito(delta, erro),
            }
        )
    itens.sort(key=lambda item: item["delta_pct"], reverse=True)
    return {
        "base_dps": round(base, 2),
        "iteracoes": int(iterations),
        "cenario": fight_style,
        "variacoes": itens,
        "melhor": itens[0] if itens else None,
        "pior": itens[-1] if itens else None,
    }


def _formatos_numero(valor: float) -> set[float]:
    saida = {round(float(valor), 6)}
    for casas in (0, 1, 2):
        saida.add(round(float(valor), casas))
    return saida


def _interpretacoes(bruto: str) -> set[float]:
    """Read a number as decimal and as PT-BR thousands separator."""
    candidatos: set[float] = set()
    try:
        candidatos.add(float(bruto.replace(",", ".")))
    except ValueError:
        pass
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", bruto):
        try:
            candidatos.add(float(bruto.replace(".", "")))
        except ValueError:
            pass
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+", bruto):
        try:
            candidatos.add(float(bruto.replace(",", "")))
        except ValueError:
            pass
    return candidatos


def _numeros_permitidos(contexto: dict[str, Any]) -> set[float]:
    permitidos: set[float] = set()

    def visitar(valor: Any) -> None:
        if isinstance(valor, bool):
            return
        if isinstance(valor, (int, float)):
            permitidos.update(_formatos_numero(float(valor)))
        elif isinstance(valor, str):
            for pedaco in _NUMERO_RE.findall(valor):
                permitidos.update(_interpretacoes(pedaco))
        elif isinstance(valor, dict):
            for item in valor.values():
                visitar(item)
        elif isinstance(valor, list):
            for item in valor:
                visitar(item)

    visitar(contexto)
    permitidos.update({0.15, 0.0})
    return permitidos


def validar_numeros(texto: str, contexto: dict[str, Any]) -> list[str]:
    """Return the numbers found in the text that are absent from the context."""
    permitidos = _numeros_permitidos(contexto)
    invalidos: list[str] = []
    for bruto in _NUMERO_RE.findall(texto):
        interpretacoes = _interpretacoes(bruto)
        if not interpretacoes:
            invalidos.append(bruto)
            continue
        if not any(
            abs(valor - candidato) <= 1e-6
            for valor in interpretacoes
            for candidato in permitidos
        ):
            invalidos.append(bruto)
    return invalidos


def resumo_deterministico(contexto: dict[str, Any]) -> str:
    linhas = [
        f"Base simulada: {contexto['base_dps']:,.0f} DPS em {contexto['cenario']} "
        f"com {contexto['iteracoes']} iterações.".replace(",", "."),
    ]
    melhor = contexto.get("melhor")
    if melhor:
        linhas.append(
            f"Maior delta: {melhor['nome']} ({melhor['delta_pct']:+.2f}%, "
            f"{melhor['veredito']})."
        )
    pior = contexto.get("pior")
    if pior and pior is not melhor:
        linhas.append(
            f"Menor delta: {pior['nome']} ({pior['delta_pct']:+.2f}%, "
            f"{pior['veredito']})."
        )
    empatados = [item["nome"] for item in contexto["variacoes"] if item["veredito"] == "empate"]
    if empatados:
        linhas.append(f"Empates por erro: {', '.join(empatados[:6])}.")
    linhas.append("Números medidos pelo SimulationCraft; nenhum valor foi estimado.")
    return "\n".join(linhas)


def estimativa_do_resumo(n_variacoes: int) -> float:
    """Kept for symmetry with the generator estimate."""
    return profilesets.estimar_segundos(n_variacoes, 1)
