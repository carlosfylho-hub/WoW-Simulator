"""Gera dados/derivados/embelezamentos.json cruzando o jogo (PT-BR) com o simc.

Fontes:
- ``dados/craft_sistemas_s2.json`` (itens ``tipo == "embelezamento"``): reagente,
  nome PT/EN, para que serve (``usavel_com``) e o efeito em PT (``fornece_propriedade``).
- ``simc-midnight/engine/dbc/generated/embellishment_data.inc``: nome EN e bônus
  que o simc aplica com ``embellishment=<nome tokenizado>`` no item.

Uso: python scripts/derivar_embelezamentos.py [--simc CAMINHO_DO_SIMC]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PADRAO_SIMC = RAIZ.parent / "simc-midnight"
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from wowsim.data.embellishments import mesclar_wowhead  # noqa: E402


def tokenizar(nome: str) -> str:
    """Igual a ``util::tokenize`` do simc (engine/util/util.cpp).

    Letras viram minúsculas, espaço vira '_', dígitos e ``_ + . %`` ficam, e todo o
    resto (hífen, vírgula, apóstrofo, acento) é REMOVIDO — não vira '_'. Ex.:
    "M3DDY, Travel-Sized" -> ``m3ddy_travelsized``. A versão anterior trocava o
    hífen por '_' e o simc ignorava o embelezamento em silêncio (achado pelo V-2).
    """
    saida = []
    for c in nome.lstrip("_+"):
        if ord(c) >= 0x80:
            continue
        if c.isalpha():
            saida.append(c.lower())
        elif c == " ":
            saida.append("_")
        elif c.isdigit() or c in "_+.%":
            saida.append(c)
    return "".join(saida)


_VARIAVEIS = {"primaryStat": "atributo primário", "secondaryStat": "atributo secundário"}


def _limpar_variaveis(texto: str) -> str:
    """O Wowhead deixa variáveis cruas (ex.: "5 de primaryStat"); troca pelo nome."""
    for crua, nome in _VARIAVEIS.items():
        texto = texto.replace(crua, nome)
    return texto


def efeito_do_tooltip(texto: str | None) -> str | None:
    """Efeito completo do reagente a partir do tooltip PT-BR (várias linhas, juntas)."""
    if not texto:
        return None
    m = re.search(r"Fornece as seguintes propriedades:\s*(.+?)\s*(?:Usável com:|$)", texto, re.S)
    if not m:
        return None
    linhas = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    efeito = " ".join(linhas)
    efeito = re.sub(r"\s*Único-equipado:.*$", "", efeito)          # já dito no limite de 2
    efeito = re.sub(r"\(\s*1\s*\*\s*(\d+)\s*\)", r"\1", efeito)   # fórmula crua do Wowhead
    efeito = re.sub(r"\s+([,.])", r"\1", efeito)
    return efeito or None


def alvo(usavel_com: str, nome_en: str) -> str | None:
    """Onde o reagente pode ir. None = de profissão específica (fora do modo Craft)."""
    u = (usavel_com or "").lower()
    if "engenharia" in u or "ferraria" in u:
        return None
    if "acessórios" in u:
        return "acessorio"
    if "armas e itens de mão secundária" in u:
        return "arma"
    if "armas e armaduras" in u:
        return "arma_ou_armadura"
    if "armaduras" in u:
        return "armadura"
    if "equipamentos" in u:
        return "qualquer"
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--simc", type=Path, default=PADRAO_SIMC)
    args = p.parse_args()

    inc = (args.simc / "engine/dbc/generated/embellishment_data.inc").read_text(encoding="utf-8")
    simc = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*\d+\s*,\s*\d+\s*\}', inc)
    }
    build = re.search(r"wow build ([\d.]+)", inc)

    jogo = json.loads((RAIZ / "dados/craft_sistemas_s2.json").read_text(encoding="utf-8"))["itens"]
    saida, vistos, sem_simc = [], set(), []
    for reagente, v in sorted(jogo.items()):
        if v.get("tipo") != "embelezamento":
            continue
        nome_en = v.get("nome_en") or ""
        if nome_en in vistos:  # o jogo lista duas qualidades do mesmo reagente
            continue
        if nome_en not in simc:
            sem_simc.append(nome_en)
            continue
        vistos.add(nome_en)
        saida.append(
            {
                "reagente_id": int(reagente),
                "nome_pt": v.get("nome_pt"),
                "nome_en": nome_en,
                "token_simc": tokenizar(nome_en),
                "bonus_id": simc[nome_en],
                "alvo": alvo(v.get("usavel_com") or "", nome_en),
                "usavel_com": v.get("usavel_com"),
                "descricao": v.get("fornece_propriedade") or v.get("efeito_pt"),
            }
        )

    # A8/P-055: mescla ícone/texto/materiais raspados do Wowhead, se existirem.
    # Só para a tela; o ganho de dano continua vindo do simc (P1).
    wowhead_path = RAIZ / "dados/derivados/embelezamentos_wowhead.json"
    wowhead_meta = None
    if wowhead_path.is_file():
        try:
            wowhead = json.loads(wowhead_path.read_text(encoding="utf-8"))
            mesclar_wowhead(saida, wowhead)
            wowhead_meta = wowhead.get("_meta")
        except (OSError, json.JSONDecodeError):
            wowhead_meta = {"erro": "embelezamentos_wowhead.json inválido"}

    # Descrição = o efeito inteiro, lido do tooltip PT-BR do Wowhead: tudo entre
    # "Fornece as seguintes propriedades:" e "Usável com:" (o efeito pode começar
    # na linha seguinte e ter várias linhas). Sem tooltip, fica a do jogo.
    for item in saida:
        efeito = efeito_do_tooltip(item.get("texto_completo"))
        if efeito:
            item["descricao"] = efeito
        if item.get("descricao"):
            item["descricao"] = _limpar_variaveis(item["descricao"])

    destino = RAIZ / "dados/derivados/embelezamentos.json"
    destino.write_text(
        json.dumps(
            {
                "_meta": {
                    "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "gerado_por": "scripts/derivar_embelezamentos.py",
                    "fontes": ["dados/craft_sistemas_s2.json", "simc engine/dbc/generated/embellishment_data.inc"],
                    "simc_build": build.group(1) if build else None,
                    "sem_correspondencia_no_simc": sem_simc,
                    "limite": "Único-equipado: Embelezado (2) — no máximo 2 efeitos ativos",
                    "wowhead": wowhead_meta,
                },
                "embelezamentos": saida,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(saida)} embelezamentos -> {destino} (sem simc: {sem_simc})")


if __name__ == "__main__":
    main()
