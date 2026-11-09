"""Tactical advisor (Gemini) with a deterministic local fallback.

This is a Python port of the ``/api/advisor`` behaviour from Simulator-WoW's
``server.ts``: same system instructions, same "no numbers invented" rule and the
same local fallback used when there is no API key or the model is unavailable.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_INSTRUCTIONS = """
Você é o Consultor Tático e Motor de Decisão Mestre de World of Warcraft: Midnight — Patch 12.1.5 (A Maldição de Ula'tek), Temporada 2.
Regras inquebráveis do projeto:
1. Resposta SEMPRE em português do Brasil (PT-BR). Nomes de itens, encantamentos, gemas e runas SEMPRE com o nome oficial PT-BR seguido do nome em inglês e o ID. Exemplo: "Braceletes do Mártir (Martyr's Bindings) [239648]".
2. NUNCA invente números de dano, procs ou atributos. Use apenas os dados auditados da base.
3. NUNCA prometa ganhos numéricos de DPS falsos. Simulação real é SimC; descreva o ganho mecânico.
4. Respeite os 5 tetos: craft no máximo 331 (Centelha de Marés + 80 cristas míticas); embelezamentos limitados a 2 efeitos ativos (Único-equipado: Embelezado (2)); 1 gema prismática (diamante de Eversong); runas do Folio com 5 linhas, 13 runas e 72 combinações. Dois berloques de uso são permitidos (o ideal costuma ser 1 de uso + 1 passivo, mas o SimC decide).
5. Explique com tabelas, marcadores e justificativas táticas, com foco em ROI e densidade de drops úteis por masmorra M+.
""".strip()

_SPEC_NAMES = {
    "balance": "Druida do Equilíbrio",
    "shadow": "Sacerdote das Sombras",
    "affliction": "Bruxo Suplício",
    "destruction": "Bruxo Destruição",
    "demonology": "Bruxo Demonologia",
}


def nome_spec(spec_id: str | None) -> str:
    return _SPEC_NAMES.get((spec_id or "demonology").lower(), "Bruxo Demonologia")


def extrair_texto(resposta: dict[str, Any]) -> str | None:
    """Pull the generated text out of a Gemini generateContent response."""
    try:
        partes = resposta["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    textos = [p.get("text", "") for p in partes if isinstance(p, dict)]
    texto = "".join(textos).strip()
    return texto or None


def fallback_local(spec_id: str | None = None, scenario: str | None = None) -> str:
    """Deterministic, audited answer used without an API key or on failure."""
    spec = nome_spec(spec_id)
    cenario = scenario or "Masmorras M+ / Delves"
    return (
        f"[Consultor Local - Base Auditada S2] — {spec} · {cenario}\n\n"
        "| Posição | Masmorra M+ | Drops úteis | Destaques | Veredito |\n"
        "| :---: | :--- | :---: | :--- | :--- |\n"
        "| 🥇 1º | Altar das Presas | 8 a 9 | Ampola Torpe de Peçonha Volátil [273796] e Nó de Serpentes "
        "Contorcidas [273794]; 3 slots de Catalisador de tecido | Prioridade máxima (ROI 10/10) |\n"
        "| 🥈 2º | Repouso do Rei | 5 a 6 | Emblema Tempestuoso de Dazar [273649] e Dragonas da Ascensão "
        "Cerimonial [239045] | Essencial (ROI 8.5/10) |\n"
        "| 🥉 3º | Travessa dos Assassinos | 4 a 5 | Mortalha do Inferninho [251132] (costas) | Forte (ROI 7.5/10) |\n"
        "| 4º | Arena da Chaga do Caos | 4 | Atadura do Éter Etérea [251222] (cinto) | Recomendado (7.0/10) |\n"
        "| 5º | Templo de Sethraliss | 3 | Anel Elo de Arenito Carregado [158366] | Cuidado: berloques de Força/Agilidade |\n"
        "| 6º | Poços da Vida Rubi | 3 | Casca de Dragonete Rubi [193757] | Neutro |\n"
        "| 7º | O Vale Ofuscante | 3 | Núcleo Altaluz [250214] (Int passivo) | Neutro |\n"
        "| ❌ 8º | Covil de Nalorakk | <2 | Ídolo do Loa da Guerra [250229] dá Força (loot morto) | Evitar |\n\n"
        "Lembretes: DPS real só pela simulação (SimC). Respeite os 5 tetos da Temporada 2; "
        "dois berloques de uso são permitidos."
    )


def montar_mensagem(
    prompt: str,
    spec_id: str | None,
    scenario: str | None,
    gear_summary: str | None,
) -> str:
    spec = nome_spec(spec_id)
    contexto = gear_summary or (
        f"{spec}, foco em Imersões e M+, sem raide. Prioridade: Aceleração > Crítico/Maestria > Versatilidade."
    )
    return (
        f"Personagem: {spec}\n"
        f"Contexto do Personagem:\n{contexto}\n"
        f"Cenário Ativo: {scenario or 'Masmorras M+ / Delves'}\n\n"
        f"Pergunta/Solicitação do Jogador:\n{prompt}"
    )


async def chamar_gemini(
    prompt: str,
    *,
    spec_id: str | None,
    scenario: str | None,
    gear_summary: str | None,
    api_key: str,
    model: str,
    timeout: float = 7.0,
) -> str | None:
    """Call Gemini's generateContent. Returns None on any failure."""
    url = f"{GEMINI_ENDPOINT}/{model}:generateContent"
    corpo = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_INSTRUCTIONS}\n\n{montar_mensagem(prompt, spec_id, scenario, gear_summary)}"}],
            }
        ],
        "tools": [{"googleSearch": {}}],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as cliente:
            resposta = await cliente.post(url, params={"key": api_key}, json=corpo)
            resposta.raise_for_status()
            return extrair_texto(resposta.json())
    except Exception:  # noqa: BLE001 - any failure falls back to local intelligence
        return None


async def consultar(
    prompt: str,
    *,
    spec_id: str | None = None,
    scenario: str | None = None,
    gear_summary: str | None = None,
) -> str:
    """Answer a query, preferring Gemini and falling back to the local engine."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        modelo = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        texto = await chamar_gemini(
            prompt,
            spec_id=spec_id,
            scenario=scenario,
            gear_summary=gear_summary,
            api_key=api_key,
            model=modelo,
        )
        if texto:
            return texto
    return fallback_local(spec_id, scenario)
