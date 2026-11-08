"""Fill missing item icons from the Wowhead tooltip endpoint.

Source: ``https://nether.wowhead.com/tooltip/item/<id>?locale=0`` returns the
texture slug in ``icon``. Results are written to ``dados/derivados/icones.json``
and merged by ``wowsim.data.icons`` (derived file wins).

Usage:
    python scripts/raspar_icones.py
    python scripts/raspar_icones.py --ids 271549 271092 --delay 0.3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim.data import icons  # noqa: E402
from wowsim.paths import DERIVADOS_DIR  # noqa: E402
from wowsim.web.catalog_api import itens_catalogo  # noqa: E402

FRONTEND = ROOT.parent / "Simulator-WoW" / "src"
DESTINO = DERIVADOS_DIR / "icones.json"
URL = "https://nether.wowhead.com/tooltip/item/{item_id}?locale=0"
AGENTE = "wowsim/0.1 (+local icon audit)"
_ID_NO_CODIGO = re.compile(r"\bid:\s*(\d+)")


def _ids_do_frontend() -> set[int]:
    ids: set[int] = set()
    itens = FRONTEND / "data" / "items.ts"
    try:
        ids.update(int(v) for v in _ID_NO_CODIGO.findall(itens.read_text(encoding="utf-8")))
    except OSError:
        pass
    builds = FRONTEND / "components" / "BuildsSimulatorTab.tsx"
    try:
        for linha in builds.read_text(encoding="utf-8").splitlines():
            if "itemEn:" in linha:
                casamento = _ID_NO_CODIGO.search(linha)
                if casamento:
                    ids.add(int(casamento.group(1)))
    except OSError:
        pass
    return ids


def _carregar_existente() -> dict[str, str]:
    try:
        dados = json.loads(DESTINO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    icones = dados.get("icones")
    return icones if isinstance(icones, dict) else {}


def _buscar(item_id: int, timeout: float = 15.0) -> str | None:
    requisicao = urllib.request.Request(
        URL.format(item_id=item_id),
        headers={"User-Agent": AGENTE, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError):
        return None
    slug = dados.get("icon")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return None


def _ids_faltantes(incluir_frontend: bool = False) -> list[int]:
    catalogo = {item["id"] for item in itens_catalogo() if isinstance(item.get("id"), int)}
    alvos = catalogo | _ids_do_frontend() if incluir_frontend else catalogo
    existentes = icons.listar()
    return sorted(item_id for item_id in alvos if item_id not in existentes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument(
        "--incluir-frontend",
        action="store_true",
        help="Também raspa ids usados apenas pelo React (ex.: peças de tier).",
    )
    args = parser.parse_args(argv)

    alvos = (
        sorted(set(args.ids))
        if args.ids
        else _ids_faltantes(incluir_frontend=args.incluir_frontend)
    )
    if not alvos:
        print("Nenhum id sem ícone; nada a fazer.")
        return 0

    atuais = _carregar_existente()
    novos: dict[str, str] = {}
    falhas: list[int] = []

    for posicao, item_id in enumerate(alvos, start=1):
        slug = _buscar(item_id)
        if slug:
            atuais[str(item_id)] = slug
            novos[str(item_id)] = slug
            print(f"[{posicao}/{len(alvos)}] {item_id} -> {slug}")
        else:
            falhas.append(item_id)
            print(f"[{posicao}/{len(alvos)}] {item_id} -> sem ícone (ignorado)")
        time.sleep(max(0.0, args.delay))

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(
            {
                "_meta": {
                    "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "fonte": "nether.wowhead.com tooltip locale=0",
                    "total": len(atuais),
                },
                "icones": dict(sorted(atuais.items(), key=lambda par: int(par[0]))),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    icons.limpar_cache()

    print(f"\nNovos ícones: {len(novos)} | falhas: {len(falhas)} | arquivo: {DESTINO}")
    if falhas:
        print("Falhas:", ", ".join(str(i) for i in falhas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
