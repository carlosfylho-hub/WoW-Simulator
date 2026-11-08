"""Gera/atualiza ``dados/amr_mapa.json`` a partir do fórum do AskMrRobot.

O cabeçalho do export AMR não traz a classe; ela é derivada dos ids de spec em
``.sN;<id>``. Esses ids são **versionados**, então mineramos exports rotulados
com classe no fórum (Discourse JSON público) e votamos por versão/spec.

Uso:
    python scripts/raspar_mapa_amr.py
    python scripts/raspar_mapa_amr.py --max-topicos 3 --termos "mage export" "warlock export"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from wowsim.paths import DADOS_DIR  # noqa: E402

BASE = "https://forums.askmrrobot.com"
DESTINO = DADOS_DIR / "amr_mapa.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

CABECALHO = re.compile(
    r"((?:\$)?(\d{1,4});[A-Z]{2};[^;\n]*;[^;\n]*;[^;\n]*;[^;\n]*;[^;\n]*;(\d{1,3});)"
)
SPEC = re.compile(r"\.s\d+;(\d{1,3})(?:;|$)")

CLASSES = {
    "deathknight": "deathknight",
    "death knight": "deathknight",
    "demonhunter": "demonhunter",
    "demon hunter": "demonhunter",
    "druid": "druid",
    "hunter": "hunter",
    "mage": "mage",
    "monk": "monk",
    "paladin": "paladin",
    "priest": "priest",
    "rogue": "rogue",
    "shaman": "shaman",
    "warlock": "warlock",
    "warrior": "warrior",
    "evoker": "evoker",
    # PT-BR
    "cavaleiro da morte": "deathknight",
    "caçador de demônios": "demonhunter",
    "druida": "druid",
    "caçador": "hunter",
    "mago": "mage",
    "monge": "monk",
    "paladino": "paladin",
    "sacerdote": "priest",
    "ladino": "rogue",
    "xamã": "shaman",
    "xama": "shaman",
    "bruxo": "warlock",
    "guerreiro": "warrior",
    "evocador": "evoker",
}

# Semente validada (v181 + fixture Pyrogalth: specs 35/36/37 = bruxo).
SEMENTES = {
    "181": {35: "warlock", 36: "warlock", 37: "warlock"},
}


def _get_json(url: str, tentativas: int = 2):
    for tentativa in range(tentativas):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            if tentativa + 1 == tentativas:
                return None
            time.sleep(0.8)
    return None


def _classe_proxima(texto: str) -> str | None:
    janela = texto[-200:].casefold()
    for rotulo, token in sorted(CLASSES.items(), key=lambda par: -len(par[0])):
        if rotulo in janela:
            return token
    return None


def _carregar() -> dict:
    try:
        return json.loads(DESTINO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"versoes": {}}


def coletar(termos: list[str], max_topicos: int, delay: float) -> dict:
    votos: dict[tuple[str, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    vistos: set[str] = set()
    for termo in termos:
        dados = _get_json(f"{BASE}/search.json?q={urllib.parse.quote(termo)}") or {}
        for topico in (dados.get("topics") or [])[:max_topicos]:
            tid = topico.get("id")
            if not tid or tid in vistos:
                continue
            vistos.add(str(tid))
            thread = _get_json(f"{BASE}/t/{tid}.json") or {}
            for post in (thread.get("post_stream") or {}).get("posts", []):
                texto = re.sub("<[^>]+>", " ", post.get("cooked") or "")
                cab = CABECALHO.search(texto)
                if not cab:
                    continue
                versao = cab.group(2)
                classe = _classe_proxima(texto[: cab.start()])
                if not classe:
                    continue
                trecho = texto[cab.start(): cab.start() + 2500]
                for spec_id in SPEC.findall(trecho):
                    votos[(versao, int(spec_id))][classe] += 1
                time.sleep(max(0.0, delay))
    return votos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--termos",
        nargs="*",
        default=[
            "mage export",
            "priest export",
            "druid export",
            "monk export",
            "hunter export",
            "warlock export",
            "paladin export",
            "warrior export",
            "shaman export",
            "evoker export",
            "death knight export",
            "demon hunter export",
            "rogue export",
        ],
    )
    parser.add_argument("--max-topicos", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args(argv)

    mapa = _carregar()
    versoes = mapa.setdefault("versoes", {})

    # sementes validadas
    for versao, specs in SEMENTES.items():
        alvo = versoes.setdefault(versao, {}).setdefault("specs", {})
        for spec_id, classe in specs.items():
            alvo.setdefault(str(spec_id), classe)

    votos = coletar(args.termos, args.max_topicos, args.delay)
    novos = 0
    for (versao, spec_id), contagem in votos.items():
        if len(contagem) != 1:  # empate/ambíguo: não grava
            continue
        classe = max(contagem, key=contagem.get)
        alvo = versoes.setdefault(versao, {}).setdefault("specs", {})
        if alvo.setdefault(str(spec_id), classe) == classe:
            novos += 1

    mapa["_meta"] = {
        "fonte": "forums.askmrrobot.com (Discourse JSON)",
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "versoes": sorted(versoes),
        "total_specs": sum(len(v.get("specs", {})) for v in versoes.values()),
    }
    DESTINO.write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Gravado {DESTINO} | versões={len(versoes)} | specs={mapa['_meta']['total_specs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
