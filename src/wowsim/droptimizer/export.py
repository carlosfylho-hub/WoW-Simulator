"""Exportação do ranking do Droptimizer em CSV.

Separado da API porque é função pura: recebe o resultado e devolve texto, o que
torna o formato testável sem subir servidor.

O arquivo é gravado em disco pelo backend em vez de baixado pelo navegador: a
janela do app desktop (pywebview/WebView2) não tem gerenciador de download, e o
clique em um link `blob:` não produzia nada — nem arquivo, nem erro.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path

from ..paths import PROJECT_ROOT
from .models import DropResult

CABECALHO = (
    "slot",
    "slots_testados",
    "item_id",
    "nome_pt",
    "nome_en",
    "ilvl",
    "dps",
    "delta_pct",
    "limiar_pct",
    "veredito",
)
# ``;`` como separador e vírgula decimal: é o que o Excel em PT-BR abre sem pedir
# importação manual.
SEPARADOR = ";"


def _numero(valor: float, casas: int) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def gerar_csv(resultado: DropResult) -> str:
    """Devolve o ranking como CSV (UTF-8, separado por ``;``)."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=SEPARADOR, lineterminator="\r\n")
    escritor.writerow(CABECALHO)
    for item in resultado.itens:
        escritor.writerow(
            [
                item.slot,
                " ".join(item.slots_testados or [item.slot]),
                item.item_id if item.item_id is not None else "",
                item.nome_pt or "",
                item.nome_en or "",
                item.ilvl if item.ilvl is not None else "",
                _numero(item.dps, 1),
                _numero(item.delta_pct, 3),
                _numero(item.limiar_pct, 3),
                item.veredito,
            ]
        )
    return buffer.getvalue()


def nome_do_arquivo(job_id: str, modo: str) -> str:
    """Nome estável e seguro: sem caractere que o Windows recuse."""
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    limpo = re.sub(r"[^A-Za-z0-9_-]", "", f"{modo}-{job_id[:8]}")
    return f"droptimizer-{limpo}-{carimbo}.csv"


def salvar_csv(resultado: DropResult, job_id: str, destino: Path | None = None) -> Path:
    """Grava o CSV em ``saida/`` e devolve o caminho absoluto."""
    pasta = destino or (PROJECT_ROOT / "saida")
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome_do_arquivo(job_id, resultado.modo)
    # BOM para o Excel reconhecer UTF-8 e não quebrar os acentos.
    caminho.write_text(gerar_csv(resultado), encoding="utf-8-sig")
    return caminho.resolve()
