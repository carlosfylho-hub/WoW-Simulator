"""Print the shape of a JSON file without loading it in the chat.

Shows the top-level type, size and a truncated preview. Useful for large
Raidbots or SimC data files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--limite", type=int, default=800)
    args = parser.parse_args()

    dados = json.loads(args.arquivo.read_text(encoding="utf-8"))
    tipo = type(dados).__name__
    tamanho = len(dados) if isinstance(dados, (dict, list)) else "n/a"
    print(f"tipo={tipo} tamanho={tamanho} bytes={args.arquivo.stat().st_size}")
    print(json.dumps(dados, ensure_ascii=False, indent=None)[: args.limite])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
