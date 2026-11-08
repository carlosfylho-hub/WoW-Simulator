"""Apply a candidate data snapshot only after the validation gate passes.

Usage:
    python scripts/atualizar_dados.py                 # validate current data
    python scripts/atualizar_dados.py --candidato DIR # validate a candidate dir
    python scripts/atualizar_dados.py --candidato DIR --aplicar

The gate is strict: a single failure blocks the update, prints the reasons and
registers a pendency. Nothing is ever estimated to fill a gap.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wowsim import pendencias  # noqa: E402
from wowsim.data.gate import verificar  # noqa: E402

DADOS = ROOT / "dados"
SUFIXOS = {".json", ".md"}


def _registrar_falha(origem: Path, motivos: list[str]) -> None:
    descricao = "; ".join(motivos)[:500]
    pendencias.registrar(
        "gate_atualizacao_dados",
        f"Atualização de dados bloqueada pelo gate: {descricao}",
        fonte=str(origem),
    )


def _copiar(origem: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for item in origem.iterdir():
        if item.is_file() and item.suffix in SUFIXOS:
            shutil.copy2(item, destino / item.name)
    derivados = origem / "derivados"
    if derivados.is_dir():
        shutil.copytree(derivados, destino / "derivados", dirs_exist_ok=True)


def _regenerar_derivados() -> None:
    for script in ("derivar_bonus_ilvl.py", "derivar_omnium.py"):
        caminho = ROOT / "scripts" / script
        if caminho.is_file():
            subprocess.run([sys.executable, str(caminho)], check=True, cwd=str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidato",
        type=Path,
        default=None,
        help="Diretório com o novo snapshot (default: dados atual).",
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Copia o candidato para dados/ após o gate e regenera derivados.",
    )
    args = parser.parse_args(argv)

    origem = args.candidato.resolve() if args.candidato else DADOS
    motivos = verificar(origem)
    if motivos:
        print("GATE REPROVADO — atualização bloqueada:")
        for motivo in motivos:
            print(f"  - {motivo}")
        _registrar_falha(origem, motivos)
        return 1

    print(f"Gate aprovado para {origem}.")

    if not args.aplicar or origem == DADOS:
        return 0

    print(f"Copiando snapshot de {origem} para {DADOS}...")
    _copiar(origem, DADOS)
    print("Regenerando dados derivados...")
    _regenerar_derivados()

    pos = verificar(DADOS)
    if pos:
        print("GATE REPROVADO após a aplicação:")
        for motivo in pos:
            print(f"  - {motivo}")
        _registrar_falha(DADOS, pos)
        return 1

    print("Atualização aplicada e validada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
