"""Contratos do Droptimizer (upgrade / best in bags / worst in bags).

Todo DPS vem do SimulationCraft. Estes modelos só descrevem entrada e ranking.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..topgear.models import Cenario, Conjunto

ModoDrop = Literal["upgrade", "best_in_bags", "worst_in_bags"]
VereditoDrop = Literal["ganho", "perda", "empate"]
FontePossuidos = Literal["inv_amr", "bags_simc", "usuario"]


class ItemPossuido(BaseModel):
    """Um item que o jogador possui (bolsas/banco/cofre)."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int
    ilvl: int | None = None
    bonus_ids: list[int] = Field(default_factory=list)
    enchant_id: int | None = None
    gem_ids: list[int] = Field(default_factory=list)
    fonte: FontePossuidos = "usuario"


class DropRequest(BaseModel):
    """Pedido de ranking de itens. Bounds evitam jobs inválidos."""

    model_config = ConfigDict(extra="forbid")

    addon: str = Field(max_length=20_000)
    # Export AMR opcional para complementar o SimC (raça, .inv, .hlv, tuning).
    amr: str | None = Field(default=None, max_length=20_000)
    primario: Literal["simc", "amr"] = "simc"
    modo: ModoDrop = "upgrade"
    scenario: Cenario = "patchwerk"
    iterations: int = Field(200, ge=10, le=100_000)
    max_profilesets_rodada: int = Field(300, ge=1, le=5_000)
    orcamento_segundos: int = Field(600, ge=1, le=86_400)
    classe_hint: str | None = Field(default=None, max_length=40)
    spec_hint: str | None = Field(default=None, max_length=40)
    incluir_inv: bool = True
    # Quantos candidatos de catálogo considerar por slot no modo upgrade.
    pool_por_slot: int = Field(12, ge=1, le=100)
    # Poda heurística: mantém só os top-K candidatos pontuáveis por slot antes
    # do SimC (berloques/armas/efeitos/sem-stats nunca são podados).
    podar: bool = True
    pool_efetiva_por_slot: int = Field(6, ge=1, le=100)
    # Exclusões explícitas de item_id.
    excluir: list[int] = Field(default_factory=list)
    # Erro-alvo em % para o simc parar cedo (ex.: 0.1). None = rodar tudo.
    target_error: float | None = Field(default=None, gt=0, le=10)

    @model_validator(mode="after")
    def _validar_primario_amr(self) -> "DropRequest":
        if self.primario == "amr" and not (
            (self.amr or "").strip() or self.addon.strip().startswith("$")
        ):
            raise ValueError(
                "primario='amr' exige um export AMR em 'amr' "
                "(ou 'addon' começando com '$')."
            )
        return self


class DropRankingItem(BaseModel):
    """Uma troca de slot medida contra o conjunto equipado."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int | None = None
    nome_pt: str | None = None
    ilvl: int | None = None
    dps: float
    delta_pct: float
    limiar_pct: float
    veredito: VereditoDrop


class DropResult(BaseModel):
    """Ranking final. Sempre medido, nunca estimado."""

    model_config = ConfigDict(extra="forbid")

    modo: ModoDrop
    base_dps: float
    iterations: int
    itens: list[DropRankingItem] = Field(default_factory=list)
    # Conjunto final montado (só para best_in_bags); medido pelo SimulationCraft.
    conjunto: Conjunto | None = None
    conjunto_dps: float | None = None
    delta_conjunto_pct: float | None = None
    avisos: list[str] = Field(default_factory=list)
