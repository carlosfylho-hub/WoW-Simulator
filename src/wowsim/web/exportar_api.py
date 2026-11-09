"""String de importação do AMR com o conjunto medido (T12).

O cabeçalho (identidade, spec, talentos, árvore, ``.qN``) vem da última string de
Best in Bags que o próprio AMR gerou; só os itens e o bloco de extras mudam.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..exportar.amr import itens_de_conjunto, linha_importacao
from ..parser.amr_codec import encantos_da_linha
from ..topgear.models import Candidato, Conjunto

router = APIRouter(prefix="/api/exportar", tags=["exportar"])

AVISO_BIB = (
    "Importar com várias linhas apaga os Best in Bags importados antes, inclusive "
    "os do site do AMR."
)
# Caracteres que quebram o formato do AMR ($ ; @ \\ # e quebras de linha).
_PROIBIDOS_ID = re.compile(r"[$;@\\#\r\n]+")


def setup_id_da_build(build: str) -> str:
    """``WSIM-<build>`` sem caracteres proibidos; nunca começa com ``AMR``."""
    limpo = _PROIBIDOS_ID.sub(" ", build or "").strip()
    limpo = re.sub(r"\s+", "-", limpo)[:40] or "build"
    return f"WSIM-{limpo}"


class PedidoAmr(BaseModel):
    modelo: str = Field(min_length=20, max_length=20_000)
    build: str = Field(min_length=1, max_length=80)
    itens: list[Candidato] = Field(min_length=1, max_length=40)


@router.post("/amr")
def string_amr(pedido: PedidoAmr) -> dict:
    conjunto = Conjunto(itens={c.slot: c for c in pedido.itens})
    setup_id = setup_id_da_build(pedido.build)
    rotulo = _PROIBIDOS_ID.sub(" ", f"WSIM {pedido.build}").strip()
    modelo = pedido.modelo.strip().splitlines()
    # Aceita o texto colado com a linha "_bib_" na frente: o modelo é a linha "$...".
    linha = next((l.strip() for l in modelo if l.strip().startswith("$")), "")
    if not linha:
        raise HTTPException(
            status_code=400,
            detail="Cole a string de Best in Bags do AMR (a linha que começa com $).",
        )
    # Bloco de encantamentos (6 campos) copiado do modelo para os encantos usados.
    usados = {c.enchant_id for c in pedido.itens if c.enchant_id}
    encantos = [
        f"e\\{eid}\\{d['item_id']}\\{d['spell_id']}\\{d['nome']}\\{d['materiais']}"
        for eid, d in encantos_da_linha(linha).items()
        if eid in usados and "\\" not in d["nome"] + d["materiais"]
    ]
    try:
        texto = linha_importacao(
            linha, itens_de_conjunto(conjunto), setup_id=setup_id, rotulo=rotulo,
            encantos=encantos,
        )
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=f"Modelo do AMR inválido: {exc}") from exc
    return {"string": texto, "setup_id": setup_id, "aviso": AVISO_BIB}
