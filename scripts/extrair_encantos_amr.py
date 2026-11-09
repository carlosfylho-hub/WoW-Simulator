"""Extrai o bloco @e (encantamentos) de uma string de Best in Bags do AMR.

Fecha P-016: grava ``dados/derivados/encantos_amr.json`` com
``enchant_id`` -> ``{item_id, spell_id, nome, materiais}``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from wowsim.parser.amr_codec import encantos_da_linha  # noqa: E402

DESTINO = PROJECT_ROOT / "dados" / "derivados" / "encantos_amr.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", help="Arquivo com a linha de BiB do AMR.")
    parser.add_argument("--saida", type=Path, default=DESTINO)
    args = parser.parse_args()

    texto = Path(args.arquivo).read_text(encoding="utf-8").strip()
    encantos = encantos_da_linha(texto)
    if not encantos:
        print("Nenhum encantamento @e encontrado na string.")
        return 1

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    dados = {
        "fonte": "amr:best-in-bags",
        "gerado_em": date.today().isoformat(),
        "encantos": {str(chave): valor for chave, valor in sorted(encantos.items())},
    }
    args.saida.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(encantos)} encantamento(s) gravados em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
