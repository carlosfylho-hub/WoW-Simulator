"""T10/A7: valida no simc real que ``embellishment=<token>`` é aceito.

Monta o perfil do fixture + um profileset de peça craftada com o embelezamento e
roda o simc. Serve para confirmar, no Windows, que o token não gera
"unknown embellishment" (o ganho de dano é o que o simc medir).

Uso:
    python scripts/validar_embellishment.py
    python scripts/validar_embellishment.py --fixture fixtures/pyrogalth.simc --token arcanoweave_lining
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim import simc_runner as sr  # noqa: E402
from wowsim.data.classes import tipo_armadura_da_classe  # noqa: E402
from wowsim.masmorras.craft import itens_craftaveis  # noqa: E402
from wowsim.parser.addon import parse_texto, serializar_texto  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "fixtures" / "pyrogalth.simc")
    parser.add_argument("--token", default="arcanoweave_lining")
    parser.add_argument("--slot", default="shoulder")
    parser.add_argument("--simc", type=Path, default=None)
    args = parser.parse_args()

    personagem = parse_texto(args.fixture.read_text(encoding="utf-8"))
    tipo = tipo_armadura_da_classe(personagem.classe)
    item = next(
        (i for i in itens_craftaveis(tipo) if i.slot == args.slot and not i.embutido),
        None,
    )
    if item is None:
        print(f"Sem peça craftável não embutida no slot {args.slot} para {tipo}.")
        return 2
    print(f"classe={personagem.classe} {personagem.spec} tipo={tipo} item={item.item_id} {item.nome_en}")

    linhas = [
        serializar_texto(personagem, incluir_checksum=False).rstrip(),
        "",
        f'profileset."emb_"+=slot={args.slot},id={item.item_id},ilevel=331,'
        f"crafted_stats=32/36,embellishment={args.token}",
    ]
    arquivo = sr.CACHE_DIR / "valida_embellishment.simc"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    execucao = sr.run_simc(
        arquivo,
        simc_path=args.simc,
        iterations=2,
        fight_style="Patchwerk",
        usar_cache=False,
        timeout=180,
    )
    print("=== SIMC STDOUT (tail) ===")
    print(execucao.stdout_tail[-3000:])
    print("=== SIMC STDERR (tail) ===")
    print(execucao.stderr_tail[-3000:])
    lido = sr.read_results(execucao.json_path)
    print("=== RESULTADO ===")
    print("base_dps:", lido.base.dps if lido.base is not None else None)
    for variacao in lido.variacoes:
        print("variacao:", variacao.nome, variacao.dps)
    print("avisos:", lido.avisos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
