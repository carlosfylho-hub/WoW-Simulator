"""Append-only registry of runtime pendencies.

Every automatic pendency is written to PENDENCIAS.md with a stable code, so a
second run does not duplicate the entry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARQUIVO_PADRAO = PROJECT_ROOT / "PENDENCIAS.md"
SECAO = "## Registros automáticos"
CABECALHO = (
    "| Data | Código | Descrição | Fonte |\n"
    "| :--- | :--- | :--- | :--- |\n"
)


def registrar(
    codigo: str,
    descricao: str,
    fonte: str | None = None,
    arquivo: str | Path | None = None,
) -> bool:
    """Register a pendency once. Returns True when the file was changed."""
    destino = Path(arquivo) if arquivo is not None else ARQUIVO_PADRAO
    if not destino.exists():
        return False

    texto = destino.read_text(encoding="utf-8")
    if f"`{codigo}`" in texto:
        return False

    if SECAO not in texto:
        texto = texto.rstrip() + f"\n\n---\n\n{SECAO}\n\n{CABECALHO}"

    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    linha = f"| {agora} | `{codigo}` | {descricao} | {fonte or '—'} |"
    texto = texto.rstrip() + "\n" + linha + "\n"
    destino.write_text(texto, encoding="utf-8")
    return True
