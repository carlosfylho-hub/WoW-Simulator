"""Audit icon coverage for every item id used by the backend and the React app.

Usage:
    python scripts/varredura_icones.py
    python scripts/varredura_icones.py --falhas

The index is derived only from the local snapshot in ``dados/``. Missing ids are
listed so they can be filled (Wowhead/Crawl4AI) instead of silently showing "?".
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "Simulator-WoW" / "src"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim.data import icons  # noqa: E402
from wowsim.web.catalog_api import itens_catalogo  # noqa: E402

_ID_NO_CODIGO = re.compile(r"\bid:\s*(\d+)")


def ids_do_frontend() -> set[int]:
    """Only real item entries: items.ts and build rows with itemEn + id."""
    ids: set[int] = set()
    itens = FRONTEND / "data" / "items.ts"
    try:
        ids.update(int(v) for v in _ID_NO_CODIGO.findall(itens.read_text(encoding="utf-8")))
    except OSError:
        pass

    builds = FRONTEND / "components" / "BuildsSimulatorTab.tsx"
    try:
        for linha in builds.read_text(encoding="utf-8").splitlines():
            if "itemEn:" not in linha:
                continue
            casamento = _ID_NO_CODIGO.search(linha)
            if casamento:
                ids.add(int(casamento.group(1)))
    except OSError:
        pass
    return ids


def ids_do_catalogo() -> set[int]:
    return {item["id"] for item in itens_catalogo() if isinstance(item.get("id"), int)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--falhas", action="store_true", help="Lista apenas ids sem ícone."
    )
    args = parser.parse_args(argv)

    indice = icons.listar()
    frontend = ids_do_frontend()
    catalogo = ids_do_catalogo()
    todos = frontend | catalogo
    sem_icone = sorted(item_id for item_id in todos if item_id not in indice)

    print(f"Itens com ícone no snapshot: {len(indice)}")
    print(f"Ids usados pelo app: {len(todos)} (frontend {len(frontend)}, catálogo {len(catalogo)})")
    print(f"Sem ícone: {len(sem_icone)}")

    if args.falhas:
        for item_id in sem_icone:
            print(item_id)
    elif sem_icone:
        print("Ids sem ícone:", ", ".join(str(i) for i in sem_icone[:80]))
        if len(sem_icone) > 80:
            print(f"... e mais {len(sem_icone) - 80}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
