"""Copy the audited data files into the project snapshot and hash them.

The source repository keeps changing and contains duplicated bases. The
snapshot is the only data the simulator reads by default, and MANIFEST.json
records origin, hash and copy date for every file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESTINO_PADRAO = PROJECT_ROOT / "dados"


def origem_padrao() -> Path:
    """Find the data repository. It may be a sibling of the workspace or of wow-sim."""
    candidatos = [
        PROJECT_ROOT.parent.parent / "WoW Calculator",
        PROJECT_ROOT.parent / "WoW Calculator",
    ]
    for candidato in candidatos:
        if candidato.is_dir():
            return candidato
    return candidatos[0]

ARQUIVOS = [
    "00-INSTRUCOES-IA.md",
    "00_INDICE_ARQUIVOS.md",
    "season2_context.json",
    "season2_context.md",
    "bonus_ids_s2.json",
    "bonus_ids_s2.md",
    "encantamentos_e_gemas_s2.json",
    "encantamentos_e_gemas_s2.md",
    "enchant_ids_s2.json",
    "enchant_ids_s2.md",
    "rune_ids_s2.json",
    "rune_ids_s2.md",
    "talent_builds_season2.json",
    "talent_builds_season2.md",
    "mplus_loot_database.json",
    "mplus_loot_database.md",
    "delve_loot_kindojan.json",
    "delve_loot_kindojan.md",
    "craft_sistemas_s2.json",
    "craft_sistemas_s2.md",
    "craft_armas_s2.json",
    "craft_armas_s2.md",
    "craft_receitas_s2.json",
    "craft_receitas_s2.md",
    "consumiveis_e_sistemas_s2.md",
    "import_e_interpretacao_s2.md",
    "pendencias.md",
    "auditoria_ptbr.md",
    "stats_oficiais_itens.json",
    "stats_oficiais_itens.md",
    "monitor_upgrades_s2.json",
    "monitor_upgrades_s2.md",
    "guia_economia_brasoes_e_upgrades_s2.md",
    "guia_masmorras_e_delves_s2.md",
    "demonology_warlock.json",
    "demonology_warlock.md",
    "affliction_warlock.json",
    "affliction_warlock.md",
    "destruction_warlock.json",
    "destruction_warlock.md",
    "shadow_priest.json",
    "shadow_priest.md",
    "balance_druid.json",
    "balance_druid.md",
]


def sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _manifesto(destino: Path) -> dict:
    caminho = destino / "MANIFEST.json"
    if not caminho.is_file():
        return {"_meta": {}, "arquivos": {}}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_meta": {}, "arquivos": {}}
    if not isinstance(dados, dict):
        return {"_meta": {}, "arquivos": {}}
    dados.setdefault("_meta", {})
    dados.setdefault("arquivos", {})
    return dados


def sincronizar(origem: Path, destino: Path, aceitar: bool, check: bool) -> int:
    if not origem.is_dir():
        print(f"Origem não encontrada: {origem}", file=sys.stderr)
        return 2

    destino.mkdir(parents=True, exist_ok=True)
    derivados = destino / "derivados"
    derivados.mkdir(exist_ok=True)

    manifesto = _manifesto(destino)
    arquivos_manifesto = manifesto["arquivos"]
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    copiados: list[str] = []
    iguais: list[str] = []
    divergentes: list[str] = []
    ausentes: list[str] = []

    for nome in ARQUIVOS:
        fonte = origem / nome
        alvo = destino / nome
        if not fonte.is_file():
            ausentes.append(nome)
            print(f"[ausente na origem] {nome}")
            continue

        hash_origem = sha256(fonte)
        if alvo.is_file():
            hash_alvo = sha256(alvo)
            if hash_alvo == hash_origem:
                iguais.append(nome)
                arquivos_manifesto[nome] = {
                    "sha256": hash_alvo,
                    "tamanho": alvo.stat().st_size,
                    "origem": str(fonte),
                    "copiado_em": arquivos_manifesto.get(nome, {}).get("copiado_em", agora),
                }
                continue

            divergentes.append(nome)
            print(f"[divergente] {nome}")
            if check:
                continue
            if not aceitar:
                print(
                    f"  mantido o snapshot. Use --aceitar para atualizar {nome}.",
                )
                continue

        if check:
            continue

        shutil.copy2(fonte, alvo)
        hash_alvo = sha256(alvo)
        arquivos_manifesto[nome] = {
            "sha256": hash_alvo,
            "tamanho": alvo.stat().st_size,
            "origem": str(fonte),
            "copiado_em": agora,
        }
        copiados.append(nome)
        print(f"[copiado] {nome}")

    manifesto["_meta"] = {
        "gerado_em": agora,
        "origem": str(origem),
        "destino": str(destino),
        "total_arquivos": len(manifesto["arquivos"]),
        "arquivos_esperados": len(ARQUIVOS),
        "ausentes": ausentes,
        "divergentes": divergentes,
    }
    (destino / "MANIFEST.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(
        f"Resumo: {len(copiados)} copiados, {len(iguais)} iguais, "
        f"{len(divergentes)} divergentes, {len(ausentes)} ausentes."
    )
    if ausentes:
        print("Arquivos ausentes precisam entrar em PENDENCIAS.md.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origem", type=Path, default=origem_padrao())
    parser.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    parser.add_argument(
        "--aceitar",
        action="store_true",
        help="Sobrescreve arquivos divergentes no snapshot.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Só compara; não copia nada.",
    )
    args = parser.parse_args()
    return sincronizar(args.origem, args.destino, args.aceitar, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
