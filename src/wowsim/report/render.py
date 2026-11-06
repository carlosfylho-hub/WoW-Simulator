"""Render the PT-BR report as Markdown and HTML.

The report never estimates: every DPS comes from the simc JSON, every name and
origin comes from the catalog with its source file.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..data import catalog
from ..data.enchants import resolver as resolver_encantamento
from ..models import Personagem, Variacao
from ..simc_runner import ResultadoDps, SimcResultado

TEMPLATES = Path(__file__).resolve().parent / "templates"
PISO_ERRO = 0.15

LIMITES = [
    "Códice Corrosivo não é simulado pelo SimC; os poderes P01–P39 ficam fora do número.",
    "Sobrevivência, dano recebido, escudos e efeitos defensivos não entram no DPS.",
    "Dois berloques on-use dividem recarga no jogo; o SimC pode não reproduzir esse limite.",
    "Comparação de talentos é por loadout salvo, não por nó da árvore.",
    "Diferenças abaixo de 0,15% são ruído e nunca viram recomendação.",
    "Itens fora do banco do SimC não entram na simulação.",
]

_SLOT_RE = re.compile(r"^([a-z_0-9]+)=")
_ENCHANT_RE = re.compile(r"enchant_id=(\d+)")
_GEM_RE = re.compile(r"gem_id=(\d+)")


def _erro(resultado: ResultadoDps | None) -> float:
    if resultado is None or resultado.erro_pct is None:
        return PISO_ERRO
    return max(PISO_ERRO, resultado.erro_pct)


def _veredito(delta: float, erro: float) -> str:
    if abs(delta) < erro:
        return "empate"
    return "ganho" if delta > 0 else "perda"


def _nome_de_encantamento(linha: str) -> tuple[str | None, str | None]:
    casamento = _ENCHANT_RE.search(linha)
    if not casamento:
        return None, None
    resolvido = resolver_encantamento(int(casamento.group(1)))
    if resolvido is None:
        return None, None
    return resolvido.nome_pt, resolvido.nome_en


def _nome_de_gema(linha: str, indice: dict[int, str | None]) -> str | None:
    casamento = _GEM_RE.search(linha)
    if not casamento:
        return None
    return indice.get(int(casamento.group(1)))


def _origem_de_item(
    item_id: int,
    slot: str | None,
    *,
    cache_mplus: dict[str, dict[int, str]],
    cache_berloques: dict[int, str] | None,
    variacao: Variacao,
) -> tuple[str | None, str]:
    if variacao.fonte.startswith("fixture"):
        return "mochila do personagem", "fixture"
    if cache_berloques is not None and item_id in cache_berloques:
        return cache_berloques[item_id], "mplus_loot_database.json"
    if slot:
        if slot not in cache_mplus:
            cache_mplus[slot] = {
                loot.item_id: loot.origem or "origem não informada"
                for loot in catalog.itens_mplus(slot)
            }
        if item_id in cache_mplus[slot]:
            return cache_mplus[slot][item_id], "mplus_loot_database.json"
    return None, "não catalogado"


def _linha_relatorio(
    variacao: Variacao,
    resultado: ResultadoDps,
    base: ResultadoDps,
    *,
    cache_mplus: dict[str, dict[int, str]],
    cache_berloques: dict[int, str] | None,
    gemas: dict[int, str | None],
) -> dict:
    dps_base = base.dps
    delta = 100.0 * (resultado.dps - dps_base) / dps_base
    erro = max(_erro(base), _erro(resultado))
    veredito = _veredito(delta, erro)

    linha = variacao.linhas_override[0] if variacao.linhas_override else ""
    slot_match = _SLOT_RE.match(linha)
    slot = catalog.normalizar_slot(slot_match.group(1)) if slot_match else None

    nome_pt = None
    nome_en = None
    item_id = variacao.item_ids[0] if variacao.item_ids else None

    if variacao.categoria == "encanto":
        nome_pt, nome_en = _nome_de_encantamento(linha)
    elif variacao.categoria == "gema":
        nome_pt = _nome_de_gema(linha, gemas)
        nome_en = None
    elif item_id is not None:
        nome = catalog.nome_item(item_id)
        nome_pt, nome_en = nome.nome_pt, nome.nome_en

    origem = None
    fonte_origem = "não catalogado"
    if item_id is not None:
        origem, fonte_origem = _origem_de_item(
            item_id,
            slot,
            cache_mplus=cache_mplus,
            cache_berloques=cache_berloques,
            variacao=variacao,
        )

    return {
        "variacao": variacao.nome,
        "categoria": variacao.categoria,
        "dps": resultado.dps,
        "dps_txt": f"{resultado.dps:,.0f}",
        "delta": delta,
        "delta_txt": f"{delta:+.2f}%",
        "erro": erro,
        "erro_txt": f"±{erro:.2f}%",
        "veredito": veredito,
        "item_pt": nome_pt,
        "item_en": nome_en,
        "item_id": item_id,
        "origem": origem,
        "fonte_origem": fonte_origem,
        "fonte": variacao.fonte,
        "aviso": variacao.aviso,
    }


def _contexto(
    personagem: Personagem,
    resultado: SimcResultado,
    variacoes: Iterable[Variacao],
    *,
    iterations: int,
    fight_style: str,
    avisos_extras: Iterable[str] = (),
) -> dict:
    if resultado.base is None:
        raise ValueError("O resultado não tem DPS da base; não há como montar o relatório.")

    por_nome = {variacao.nome: variacao for variacao in variacoes}
    gemas = {gema.item_id: gema.nome_pt for gema in catalog.gemas()}
    cache_mplus: dict[str, dict[int, str]] = {}
    cache_berloques = {
        loot.item_id: loot.origem or "origem não informada"
        for loot in catalog.berloques_conjurador()
    }

    linhas = []
    for entrada in resultado.variacoes:
        variacao = por_nome.get(entrada.nome)
        if variacao is None:
            continue
        linhas.append(
            _linha_relatorio(
                variacao,
                entrada,
                resultado.base,
                cache_mplus=cache_mplus,
                cache_berloques=cache_berloques,
                gemas=gemas,
            )
        )

    nomes_categoria = {
        "upgrade": "Upgrade de trilha",
        "item": "Troca de item",
        "encanto": "Encantamentos",
        "gema": "Gemas",
        "talento": "Talentos",
        "folio": "Folio Ômnico",
        "berloque": "Berloques",
        "combo": "Combos",
    }
    agrupado: dict[str, list[dict]] = {}
    for linha in linhas:
        agrupado.setdefault(linha["categoria"], []).append(linha)

    categorias = []
    for chave in ("upgrade", "item", "encanto", "gema", "talento", "folio", "berloque", "combo"):
        if chave not in agrupado:
            continue
        categorias.append(
            {
                "chave": chave,
                "nome": nomes_categoria.get(chave, chave),
                "linhas": sorted(agrupado[chave], key=lambda item: item["delta"], reverse=True),
            }
        )

    avisos = list(dict.fromkeys(list(avisos_extras)))
    for linha in linhas:
        if linha["aviso"]:
            avisos.append(f"{linha['variacao']}: {linha['aviso']}")
    for variacao in variacoes:
        if variacao.categoria == "talento" and any(
            termo in variacao.nome for termo in ("ceifador", "soul", "harvester")
        ):
            avisos.append(
                f"{variacao.nome}: o APL padrão do SimC pode subestimar Ceifador de Almas."
            )

    return {
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "iteracoes": iterations,
        "fight_style": fight_style,
        "personagem": {
            "nome": personagem.nome or "não informado",
            "classe": personagem.classe or "?",
            "spec": personagem.spec or "?",
            "nivel": personagem.nivel or "?",
            "regiao": personagem.regiao or "?",
            "servidor": personagem.servidor or "?",
            "build": personagem.build_cliente or "?",
            "checksum": personagem.checksum or "ausente",
        },
        "base": {
            "dps": resultado.base.dps,
            "dps_txt": f"{resultado.base.dps:,.0f}",
            "erro": _erro(resultado.base),
            "erro_txt": f"±{_erro(resultado.base):.2f}%",
        },
        "categorias": categorias,
        "avisos": avisos,
        "limites": LIMITES,
        "fontes": sorted({linha["fonte"] for linha in linhas}),
        "total_variacoes": len(linhas),
    }


def render(
    personagem: Personagem,
    resultado: SimcResultado,
    variacoes: Iterable[Variacao],
    *,
    destino: str | Path,
    iterations: int,
    fight_style: str,
    avisos: Iterable[str] = (),
) -> tuple[Path, Path]:
    """Write relatorio.md and relatorio.html and return both paths."""
    contexto = _contexto(
        personagem,
        resultado,
        variacoes,
        iterations=iterations,
        fight_style=fight_style,
        avisos_extras=avisos,
    )

    ambiente = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)

    md = ambiente.get_template("relatorio.md.j2").render(**contexto)
    html = ambiente.get_template("relatorio.html.j2").render(**contexto)

    caminho_md = pasta / "relatorio.md"
    caminho_html = pasta / "relatorio.html"
    caminho_md.write_text(md, encoding="utf-8")
    caminho_html.write_text(html, encoding="utf-8")
    return caminho_md, caminho_html
