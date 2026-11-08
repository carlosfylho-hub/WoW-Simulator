"""Contracts for the Top Gear search (Raidbots style).

These models are intentionally data-only. All DPS numbers come from
SimulationCraft; nothing here estimates damage. Missing data becomes ``None``
and is reported as a pending item upstream.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Estagio = Literal[
    "pools",
    "poda",
    "verificacao",
    "marginal",
    "gulosa",
    "beam",
    "encantos",
    "gemas",
    "talentos",
    "folio",
    "consumiveis",
    "refino",
    "concluido",
]
TipoArma = Literal["1h", "2h", "desconhecido"]
# Kept in sync with ``runner.estilo_de_luta`` and ``sim_api.CENARIOS``.
# Inclui os Fight Styles validados no binário local do SimulationCraft.
Cenario = Literal[
    "patchwerk",
    "dungeon_slice",
    "raid",
    "mplus",
    "cleave_aoe",
    "delve_rooms",
    "delve_boss",
    "hectic_add_cleave",
    "light_movement",
    "heavy_movement",
    "casting_patchwerk",
    "cleave_add",
    "helter_skelter",
]


class Candidato(BaseModel):
    """One selectable option for a slot (item, enchant, gem, talent, folio)."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int | None = None
    enchant_id: int | None = None
    gem_ids: list[int] = Field(default_factory=list)
    bonus_id: int | None = None
    bonus_ids: list[int] = Field(default_factory=list)
    ilvl: int | None = None
    fonte: str
    nome_pt: str | None = None
    nome_en: str | None = None

    # Eligibility and constraint helpers, filled by the pool builder.
    tipo: str | None = None
    tipo_arma: TipoArma = "desconhecido"
    tipo_armadura: str | None = None
    tipo_efeito: str | None = None
    embelezamento: bool = False
    craftado: bool = False

    # Opaque payload used by talents (import string) and other pools.
    valor: str | None = None

    # Visual data for the UI comparison (icon + attributes from the catalog).
    stats: dict[str, int] | None = None
    icone: str | None = None

    @property
    def rotulo(self) -> str:
        """Human label in PT-BR plus identifier, for reports and the UI."""
        nome = self.nome_pt or self.nome_en or "item desconhecido"
        partes = [nome]
        if self.item_id is not None:
            partes.append(str(self.item_id))
        if self.ilvl is not None:
            partes.append(f"ilvl {self.ilvl}")
        return " · ".join(partes)


class Conjunto(BaseModel):
    """A complete loadout proposal: one candidate per slot."""

    model_config = ConfigDict(extra="forbid")

    itens: dict[str, Candidato] = Field(default_factory=dict)
    talentos: str | None = None
    runas_folio: list[str] = Field(default_factory=list)
    flask: str | None = None
    potion: str | None = None
    food: str | None = None
    augmentation: str | None = None

    def com_troca(self, slot: str, candidato: Candidato) -> "Conjunto":
        """Return a copy with a single slot replaced."""
        itens = dict(self.itens)
        itens[slot] = candidato
        return self.model_copy(update={"itens": itens})

    def item_id(self, slot: str) -> int | None:
        candidato = self.itens.get(slot)
        return candidato.item_id if candidato is not None else None


class TopGearRequest(BaseModel):
    """Job request. Bounds are validated so the worker never starts a bad job."""

    model_config = ConfigDict(extra="forbid")

    addon: str = Field(max_length=20_000)
    # Export AMR opcional para complementar o SimC (raça, .inv, .hlv, tuning).
    amr: str | None = Field(default=None, max_length=20_000)
    primario: Literal["simc", "amr"] = "simc"
    # Dicas usadas quando ``addon`` é um export AskMrRobot (cabeçalho ambíguo).
    classe_hint: str | None = Field(default=None, max_length=40)
    spec_hint: str | None = Field(default=None, max_length=40)
    scenario: Cenario = "patchwerk"
    iterations_triagem: int = Field(200, ge=10, le=100_000)
    iterations_refino: int = Field(2000, ge=10, le=100_000)
    max_profilesets_rodada: int = Field(300, ge=1, le=5_000)
    orcamento_segundos: int = Field(600, ge=1, le=86_400)
    slots_travados: dict[str, int] = Field(default_factory=dict)
    # Item ids the user explicitly excludes from the candidate pools.
    excluir: list[int] = Field(default_factory=list)
    # Extra talent import strings to test besides the saved loadouts.
    talentos_extra: list[str] = Field(default_factory=list, max_length=20)
    incluir: list[str] = Field(
        default_factory=lambda: [
            "item",
            "encanto",
            "gema",
            "talento",
            "folio",
            "berloque",
            "flask",
            "potion",
            "food",
            "augmentation",
        ]
    )
    pool_por_slot: int = Field(12, ge=1, le=100)
    # Poda heurística: mantém só os top-K candidatos pontuáveis por slot antes
    # do SimC (berloques/armas/efeitos/sem-stats nunca são podados).
    podar: bool = True
    pool_efetiva_por_slot: int = Field(6, ge=1, le=100)
    # Re-mede os candidatos podados ao final e recupera ganho que a heurística
    # possa ter descartado (custo extra; desligado por padrão).
    verificar_podados: bool = False
    thread: int | None = Field(default=None, ge=1, le=512)
    # Erro-alvo em % para o simc parar cedo (ex.: 0.1). None = rodar tudo.
    target_error: float | None = Field(default=None, gt=0, le=10)

    @model_validator(mode="after")
    def _validar_primario_amr(self) -> "TopGearRequest":
        if self.primario == "amr" and not (
            (self.amr or "").strip() or self.addon.strip().startswith("$")
        ):
            raise ValueError(
                "primario='amr' exige um export AMR em 'amr' "
                "(ou 'addon' começando com '$')."
            )
        return self


class Troca(BaseModel):
    """A single slot change from the base or previous best set."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    de: str | None = None
    para: str | None = None
    delta_pct: float | None = None
    de_item_id: int | None = None
    para_item_id: int | None = None


class Rodada(BaseModel):
    """History entry used for convergence and progress reporting."""

    model_config = ConfigDict(extra="forbid")

    numero: int
    estagio: Estagio
    dps: float | None = None
    delta_pct: float | None = None
    candidatos: int = 0
    trocas: int = 0
    duracao_s: float | None = None


class TopGearResult(BaseModel):
    """Final, measured result. Every DPS value came from SimulationCraft."""

    model_config = ConfigDict(extra="forbid")

    melhor: Conjunto
    # Conjunto atualmente equipado (para a comparação lado a lado na UI).
    base: Conjunto | None = None
    base_dps: float
    melhor_dps: float
    delta_pct: float
    limiar_pct: float
    trocas: list[Troca] = Field(default_factory=list)
    rodadas: list[Rodada] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


class ContextoSpec(BaseModel):
    """Spec-level facts and catalog indexes used by the constraint validator.

    The sets are built by the pool layer from the catalog so that
    ``constraints.validar`` stays pure and cheap to test.
    """

    model_config = ConfigDict(extra="forbid")

    classe: str | None = None
    spec: str | None = None
    tipo_arma: TipoArma = "desconhecido"
    tipo_armadura: str | None = None

    max_embelezamentos: int = 2
    max_diamantes: int = 1
    max_on_use: int = 1
    craft_ilvl_teto: int = 331
    exige_offhand_com_1h: bool = True

    embelezamentos: set[int] = Field(default_factory=set)
    diamantes: set[int] = Field(default_factory=set)
    trinkets_on_use: set[int] = Field(default_factory=set)
    tier_ids: set[int] = Field(default_factory=set)
    offs_validos: set[int] = Field(default_factory=set)
