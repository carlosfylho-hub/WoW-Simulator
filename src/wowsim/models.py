"""Pydantic models for the addon export and simulation results.

Field names are English; user-facing text lives in the CLI and report layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrigemLinha = Literal["equipado", "mochila", "catalogo"]
Severidade = Literal["info", "aviso", "bloqueio"]
CategoriaVariacao = Literal[
    "base", "upgrade", "item", "encanto", "gema", "talento", "folio", "berloque", "combo"
]
Veredito = Literal["ganho", "perda", "empate", "nao_simulavel"]


class AlertaParse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    severidade: Severidade = "aviso"
    detalhe: str
    linha: int | None = None


class ItemEquipado(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int | None = None
    enchant_id: int | None = None
    gem_ids: list[int] = Field(default_factory=list)
    bonus_ids: list[int] = Field(default_factory=list)
    crafted_stats: tuple[int, int] | None = None
    crafting_quality: int | None = None
    content_tuning: int | None = None
    drop_level: int | None = None
    redirected_base_stats: int | None = None
    ilvl_comentario: int | None = None
    nome_pt: str | None = None
    nome_en: str | None = None
    origem_linha: OrigemLinha = "equipado"
    indice_linha: int | None = None
    linha_original: str
    campos_extras: dict[str, str] = Field(default_factory=dict)


class MarcaIlvl(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indice: int
    ilvl_atual: int
    ilvl_maximo: int
    mapeado: bool = False


class Personagem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None = None
    classe: str | None = None
    spec: str | None = None
    nivel: int | None = None
    raca: str | None = None
    regiao: str | None = None
    servidor: str | None = None
    role: str | None = None
    profissoes: dict[str, int] = Field(default_factory=dict)
    loot_spec: str | None = None

    talents_atual: str | None = None
    loadouts: dict[str, str] = Field(default_factory=dict)
    omnium_ids_brutos: list[int] = Field(default_factory=list)
    omnium_ranks: dict[int, int] = Field(default_factory=dict)
    runas_declaradas: dict[str, str] | None = None

    equipado: dict[str, ItemEquipado] = Field(default_factory=dict)
    mochila: dict[str, list[ItemEquipado]] = Field(default_factory=dict)

    catalyst_currencies: dict[int, int] = Field(default_factory=dict)
    upgrade_currencies: dict[str, int] = Field(default_factory=dict)
    slot_high_watermarks: list[MarcaIlvl] = Field(default_factory=list)
    bonus_roll_currencies: dict[int, int] = Field(default_factory=dict)
    bonus_roll_items: str | None = None
    upgrade_achievements: list[int] = Field(default_factory=list)

    versao_addon: str | None = None
    build_cliente: str | None = None
    checksum: str | None = None
    texto_original: str = Field(exclude=True, repr=False)
    bloco_equipamento_original: str = Field(default="", exclude=True, repr=False)
    alertas: list[AlertaParse] = Field(default_factory=list)


class NomeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    nome_pt: str | None = None
    nome_en: str | None = None
    fonte: str
    simulavel: bool = True


class IlvlBonus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bonus_id: int
    trilha: str | None = None
    rank: str | None = None
    ilvl: int | None = None
    evidencia: str | None = None
    fonte: str


class RunasFolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = None
    por_linha: dict[str, str] = Field(default_factory=dict)
    ids_por_linha: dict[str, list[int]] = Field(default_factory=dict)
    confianca: Literal["alta", "media", "baixa"] = "baixa"
    fonte: str


class Variacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str
    categoria: CategoriaVariacao
    linhas_override: list[str]
    item_ids: list[int] = Field(default_factory=list)
    bonus_ids_envolvidos: list[int] = Field(default_factory=list)
    fonte: str


class ResultadoVariacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str
    dps: float
    erro_pct: float | None = None
    amostras: int | None = None
    eh_base: bool = False


class LinhaRelatorio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variacao: str
    categoria: str
    dps: float
    delta_pct: float | None = None
    erro_pct: float | None = None
    veredito: Veredito
    nome_pt: str | None = None
    nome_en: str | None = None
    item_id: int | None = None
    fonte: str
