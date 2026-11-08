"""Raidbots-style Top Gear search built on top of SimulationCraft."""

from .constraints import avisos, validar
from .models import (
    Candidato,
    Conjunto,
    ContextoSpec,
    Rodada,
    TopGearRequest,
    TopGearResult,
    Troca,
)
from .pools import (
    combinacoes_folio,
    construir_contexto,
    construir_pools,
    diamantes,
    encantos_por_slot,
    gemas_catalogo,
    resumo,
    talentos_disponiveis,
)
from .runner import LeituraSim, criar_simulador, estilo_de_luta, escrever_rodada
from .search import conjunto_do_personagem, executar_topgear

__all__ = [
    "Candidato",
    "Conjunto",
    "ContextoSpec",
    "LeituraSim",
    "Rodada",
    "TopGearRequest",
    "TopGearResult",
    "Troca",
    "avisos",
    "combinacoes_folio",
    "conjunto_do_personagem",
    "construir_contexto",
    "construir_pools",
    "criar_simulador",
    "diamantes",
    "encantos_por_slot",
    "escrever_rodada",
    "estilo_de_luta",
    "executar_topgear",
    "gemas_catalogo",
    "resumo",
    "talentos_disponiveis",
    "validar",
]
