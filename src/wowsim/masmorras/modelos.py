"""Contratos de saída do ranking de masmorras (API e tela).

Nenhum número de dano nasce aqui: os percentuais vêm de ``avaliar`` (medição do
simc). A "chance" é uma suposição explícita em ``PREMISSA_CHANCE`` (P1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..topgear.models import Cenario

Etiqueta = Literal["direto", "catalisar", "ambos", "nao_serve"]
PREMISSA_CHANCE = (
    "Chance = itens que servem ÷ itens que sua classe pode receber nesta masmorra. "
    "Supõe que cada item elegível tem a mesma chance de cair; o ganho de cada item é medido."
)


class ItemRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    nome_pt: str | None = None
    nome_en: str | None = None
    slot: str
    ilvl: int
    etiqueta: Etiqueta
    delta_cru_pct: float
    delta_catalisado_pct: float | None = None
    limiar_pct: float
    icone: str | None = None
    stats: dict[str, int] | None = None
    aviso: str | None = None


class MasmorraRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    masmorra: str
    servem: int
    elegiveis: int
    chance_pct: float
    maior_pct: float
    direto: int
    catalisar: int
    explicacao: str
    itens: list[ItemRanking] = Field(default_factory=list)


class RankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addon: str = Field(max_length=20_000)
    amr: str | None = Field(default=None, max_length=20_000)
    primario: Literal["simc", "amr"] = "simc"
    scenario: Cenario = "dungeon_slice"
    ilvl: Literal[321, 328, 334, 341] = 341
    iteracoes_triagem: int = Field(300, ge=50, le=5_000)
    iteracoes_refino: int = Field(3000, ge=200, le=50_000)
    orcamento_segundos: int = Field(900, ge=30, le=86_400)
    loadouts: list[str] = Field(default_factory=list)          # T9
    pesos_loadouts: dict[str, float] = Field(default_factory=dict)  # T9


class RankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_dps: float
    cenario: str
    ilvl: int
    iteracoes: int
    ordem_padrao: Literal["quantidade"] = "quantidade"
    masmorras: list[MasmorraRanking] = Field(default_factory=list)
    premissa_chance: str = PREMISSA_CHANCE
    avisos: list[str] = Field(default_factory=list)
