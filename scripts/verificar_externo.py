"""Cross-check project names, item levels and runes against Wowhead.

Fetches tooltips for a closed list of ids used by the fixture and by the
catalog, compares with the project files and writes the evidence to
dados/verificacao/wowhead.json. No Firecrawl credits are used.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DADOS = PROJECT_ROOT / "dados"
SAIDA = DADOS / "verificacao" / "wowhead.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

ILVL_PT = re.compile(r"N[ií]vel do Item:\s*<!--ilvl-->(\d+)")
ILVL_EN = re.compile(r"Item Level:\s*<!--ilvl-->(\d+)")

ITENS_FIXTURE = [
    271546,
    273781,
    271544,
    239656,
    271549,
    233290,
    239648,
    271547,
    271543,
    271545,
    271548,
    275527,
    272147,
    273649,
    273796,
    251156,
]
ITENS_MOCHILA = [158075, 272226, 272230, 144392, 241291]
ITENS_CANDIDATOS = [270167, 270170, 270164, 250214, 250224]
GEMAS = [240908, 240983, 240909, 240984]


def _get_json(url: str, tentativas: int = 3) -> dict | None:
    for tentativa in range(tentativas):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(requisicao, timeout=25) as resposta:
                return json.loads(resposta.read().decode("utf-8"))
        except Exception:
            if tentativa + 1 == tentativas:
                return None
            time.sleep(0.8)
    return None


def _get_texto(url: str, tentativas: int = 2) -> str | None:
    for tentativa in range(tentativas):
        try:
            requisicao = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(requisicao, timeout=25) as resposta:
                return resposta.read().decode("utf-8", errors="replace")
        except Exception:
            if tentativa + 1 == tentativas:
                return None
            time.sleep(0.8)
    return None


def _item_wowhead(item_id: int) -> dict:
    pt = _get_json(
        f"https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale=8"
    )
    en = _get_json(
        f"https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale=0"
    )
    tooltip = (pt or {}).get("tooltip") or ""
    ilvl = None
    for padrao in (ILVL_PT, ILVL_EN):
        casamento = padrao.search(tooltip)
        if casamento:
            ilvl = int(casamento.group(1))
            break
    return {
        "item_id": item_id,
        "nome_pt": (pt or {}).get("name"),
        "nome_en": (en or {}).get("name"),
        "ilvl_tooltip": ilvl,
        "qualidade": (pt or {}).get("quality"),
        "fonte": "nether.wowhead.com/tooltip/item",
    }


def _spell_wowhead(spell_id: int) -> dict:
    pt = _get_json(
        f"https://nether.wowhead.com/tooltip/spell/{spell_id}?dataEnv=1&locale=8"
    )
    en = _get_json(
        f"https://nether.wowhead.com/tooltip/spell/{spell_id}?dataEnv=1&locale=0"
    )
    return {
        "spell_id": spell_id,
        "nome_pt": (pt or {}).get("name"),
        "nome_en": (en or {}).get("name"),
        "fonte": "nether.wowhead.com/tooltip/spell",
    }


def _normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    return re.sub(r"\s+", " ", texto).strip().casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pausa", type=float, default=0.15)
    args = parser.parse_args()

    stats = json.loads((DADOS / "stats_oficiais_itens.json").read_text(encoding="utf-8"))[
        "itens"
    ]
    encantos = json.loads(
        (DADOS / "encantamentos_e_gemas_s2.json").read_text(encoding="utf-8")
    )
    enchant_map = json.loads(
        (DADOS / "enchant_ids_s2.json").read_text(encoding="utf-8")
    )["enchants"]
    runas = json.loads((DADOS / "rune_ids_s2.json").read_text(encoding="utf-8"))["runas"]

    itens_encantamento = sorted(
        {int(entrada["item_id"]) for entrada in enchant_map.values() if entrada.get("item_id")}
    )[:12]

    itens = list(dict.fromkeys(ITENS_FIXTURE + ITENS_MOCHILA + ITENS_CANDIDATOS + GEMAS + itens_encantamento))

    resultados_itens = []
    for indice, item_id in enumerate(itens, start=1):
        dados = _item_wowhead(item_id)
        esperado_pt = None
        esperado_ilvl = None
        fonte_esperada = None
        if str(item_id) in stats:
            esperado_pt = stats[str(item_id)].get("nome_pt")
            esperado_ilvl = stats[str(item_id)].get("ilvl_referencia")
            fonte_esperada = "stats_oficiais_itens.json"
        elif str(item_id) in encantos.get("encantamentos", {}):
            esperado_pt = encantos["encantamentos"][str(item_id)].get("nome_pt")
            fonte_esperada = "encantamentos_e_gemas_s2.json"
        elif str(item_id) in encantos.get("gemas", {}):
            esperado_pt = encantos["gemas"][str(item_id)].get("nome_pt")
            fonte_esperada = "encantamentos_e_gemas_s2.json"
        elif str(item_id) in encantos.get("pernas", {}):
            esperado_pt = encantos["pernas"][str(item_id)].get("nome_pt")
            fonte_esperada = "encantamentos_e_gemas_s2.json"
        else:
            for entrada in enchant_map.values():
                if entrada.get("item_id") == item_id:
                    esperado_pt = entrada.get("nome_pt")
                    fonte_esperada = "enchant_ids_s2.json"
                    break

        dados.update(
            {
                "esperado_pt": esperado_pt,
                "esperado_ilvl": esperado_ilvl,
                "fonte_esperada": fonte_esperada,
                "nome_igual": _normalizar(esperado_pt) == _normalizar(dados["nome_pt"])
                if esperado_pt
                else None,
                "ilvl_igual": (esperado_ilvl == dados["ilvl_tooltip"])
                if esperado_ilvl is not None
                else None,
            }
        )
        resultados_itens.append(dados)
        print(
            f"[{indice}/{len(itens)}] {item_id} {dados['nome_pt']!r} "
            f"ilvl={dados['ilvl_tooltip']} "
            f"nome_igual={dados['nome_igual']} ilvl_igual={dados['ilvl_igual']}"
        )
        time.sleep(args.pausa)

    resultados_runas = []
    for runa in runas:
        spell_id = runa["id_base"]
        dados = _spell_wowhead(spell_id)
        dados.update(
            {
                "escolha": runa["escolha"],
                "esperado_pt": runa["nome_pt"],
                "fonte_esperada": "rune_ids_s2.json",
                "nome_igual": _normalizar(runa["nome_pt"]) == _normalizar(dados["nome_pt"]),
            }
        )
        resultados_runas.append(dados)
        print(
            f"[runa {runa['escolha']}] {spell_id} {dados['nome_pt']!r} "
            f"nome_igual={dados['nome_igual']}"
        )
        time.sleep(args.pausa)

    evidencia = {
        "blizzard": _get_texto("http://us.patch.battle.net:1119/wow/versions"),
        "simc_branch": _get_texto(
            "https://api.github.com/repos/simulationcraft/simc/branches/midnight"
        ),
        "simc_version_file": _get_texto(
            "https://raw.githubusercontent.com/simulationcraft/simc/midnight/"
            "engine/dbc/generated/client_data_version.inc"
        ),
        "raidbots_metadata": _get_texto(
            "https://www.raidbots.com/static/data/live/metadata.json"
        ),
    }

    nomes_diferentes = [
        item for item in resultados_itens if item["nome_igual"] is False
    ]
    ilvl_diferentes = [
        item for item in resultados_itens if item["ilvl_igual"] is False
    ]
    runas_diferentes = [runa for runa in resultados_runas if not runa["nome_igual"]]

    saida = {
        "_meta": {
            "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "itens_verificados": len(resultados_itens),
            "runas_verificadas": len(resultados_runas),
            "nomes_diferentes": len(nomes_diferentes),
            "ilvl_diferentes": len(ilvl_diferentes),
            "runas_diferentes": len(runas_diferentes),
        },
        "itens": resultados_itens,
        "runas": resultados_runas,
        "evidencia": evidencia,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"Gravado {SAIDA}")
    print(f"itens={len(resultados_itens)} nomes_diferentes={len(nomes_diferentes)}")
    print(f"ilvl_diferentes={len(ilvl_diferentes)} runas_diferentes={len(runas_diferentes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
