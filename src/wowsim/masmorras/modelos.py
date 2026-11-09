"""Contratos de saída do ranking de masmorras (API e tela).

Nenhum número de dano nasce aqui: os percentuais vêm de ``avaliar`` (medição do
simc). A "chance" é uma suposição explícita em ``PREMISSA_CHANCE`` (P1).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..data import trilhas
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
    degrau: str | None = None                 # "Mito 4/6"
    upgrade: dict[str, Any] | None = None     # {moeda, brasoes, etapas, ate}


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


class TrocaBuild(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int | None = None
    nome_pt: str | None = None
    nome_en: str | None = None
    ilvl: int | None = None
    catalisado: bool = False
    ganho_pct: float           # ganho medido do item sozinho (contra ``ref``)
    icone: str | None = None
    stats: dict[str, int] | None = None
    degrau: str | None = None
    upgrade: dict[str, Any] | None = None


class BuildResultado(BaseModel):
    """Uma build (loadout): referência, conjunto montado e confirmação medida."""

    model_config = ConfigDict(extra="forbid")

    nome: str
    cenario: str
    ref_dps: float | None = None
    # Delta medido do conjunto montado contra ``ref`` (execução de confirmação).
    delta_conjunto_pct: float | None = None
    limiar_conjunto_pct: float | None = None
    trocas: list[TrocaBuild] = Field(default_factory=list)
    # Conjunto montado completo (Candidato serializado), para a string do AMR.
    conjunto_itens: list[dict[str, Any]] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    pawn: str | None = None
    pawn_pesos: dict[str, float] | None = None
    # Brasões para levar as trocas ao 6/6, por moeda (custo cheio, sem desconto de slot).
    brasoes: dict[str, int] = Field(default_factory=dict)


class LinhaMatriz(BaseModel):
    """Um item: % medido em cada build, média ponderada e divergência."""

    model_config = ConfigDict(extra="forbid")

    item_id: int
    nome_pt: str | None = None
    nome_en: str | None = None
    masmorra: str
    slot: str
    icone: str | None = None
    stats: dict[str, int] | None = None
    deltas: dict[str, float]
    limiares: dict[str, float]
    etiquetas: dict[str, Etiqueta]
    media_pct: float
    divergente: bool


class RankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    addon: str = Field(max_length=20_000)
    amr: str | None = Field(default=None, max_length=20_000)
    primario: Literal["simc", "amr"] = "simc"
    scenario: Cenario = "dungeon_slice"
    # "masmorras" = ranking de M+; "cofre" = opções do Grande Cofre (.gv do AMR).
    modo: Literal["masmorras", "cofre", "craft"] = "masmorras"
    ilvl: Literal[321, 328, 334, 341] = 341        # atalho antigo; trilha/rank prevalecem
    trilha: Literal["heroi", "mito"] | None = None
    rank: int | None = Field(default=None, ge=1, le=6)
    forja: bool = False
    iteracoes_triagem: int = Field(300, ge=50, le=5_000)
    iteracoes_refino: int = Field(3000, ge=200, le=50_000)
    # Quantos itens da triagem vão para o refino (os melhores).
    max_refino: int = Field(24, ge=1, le=500)
    orcamento_segundos: int = Field(900, ge=30, le=86_400)
    loadouts: list[str] = Field(default_factory=list, max_length=6)   # T9 ("Atual" = talentos do export)
    pesos_loadouts: dict[str, float] = Field(default_factory=dict)   # T9 (normalizados no motor)
    cenarios_loadouts: dict[str, Cenario] = Field(default_factory=dict)  # T9: escolha do usuário prevalece
    medir_pesos: bool = False                                         # T11: escala do Pawn por build
    iteracoes_pesos: int = Field(5_000, ge=5_000, le=100_000)         # T11: mínimo 5.000


    def degrau(self) -> trilhas.Degrau:
        """Nível pedido: trilha + rank (+ forja) ou, sem trilha, o atalho do ilvl."""
        if self.trilha:
            return trilhas.degrau(self.trilha, self.rank or 6, self.forja)
        return trilhas.degrau_do_ilvl(self.ilvl)


class RankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_dps: float
    cenario: str
    ilvl: int
    nivel: str | None = None          # "Mito 6/6 + Forja"
    iteracoes: int
    ordem_padrao: Literal["quantidade"] = "quantidade"
    masmorras: list[MasmorraRanking] = Field(default_factory=list)
    premissa_chance: str = PREMISSA_CHANCE
    avisos: list[str] = Field(default_factory=list)
    # Informações neutras (ex.: ".inv mesclado"), fora dos avisos âmbar (P-053).
    informacoes: list[str] = Field(default_factory=list)
    # T9 (vazios fora do modo builds)
    builds: list[BuildResultado] = Field(default_factory=list)
    matriz: list[LinhaMatriz] = Field(default_factory=list)
    pesos_builds: dict[str, float] = Field(default_factory=dict)
    # T11
    pawn_atual: str | None = None
    pawn_mistura: str | None = None
    pawn_iguais: list[list[str]] = Field(default_factory=list)
    # T22: modo Craft — {pecas, embelezamentos, custo, avisos}
    craft: dict[str, Any] | None = None
