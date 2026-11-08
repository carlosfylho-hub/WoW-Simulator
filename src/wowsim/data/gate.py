"""Validation gate for the data snapshot.

The gate blocks any update that fails a hard check (counts, upgrade bonus
item levels, PT/EN names, patch, manifest hashes). A failure must never be
worked around with estimates; it becomes a pendency instead.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import simc_runner
from ..paths import DERIVADOS_DIR

ARQUIVOS_OBRIGATORIOS = (
    "MANIFEST.json",
    "season2_context.json",
    "stats_oficiais_itens.json",
    "encantamentos_e_gemas_s2.json",
    "enchant_ids_s2.json",
    "rune_ids_s2.json",
    "bonus_ids_s2.json",
    "monitor_upgrades_s2.json",
    "mplus_loot_database.json",
)

CONTAGENS_ESPERADAS = {
    "gemas": 72,
    "encantamentos": 76,
    "enchant_ids": 97,
    "runas": 13,
    "combinacoes_folio": 72,
}

BONUS_ILVL_ESPERADO = {12846: 321, 12848: 328, 12854: 334, 12856: 341}

ITEM_REFERENCIA = 251156


def _ler(caminho: Path) -> dict | None:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _verificar_manifest(pasta: Path) -> list[str]:
    motivos: list[str] = []
    manifest = _ler(pasta / "MANIFEST.json")
    if manifest is None:
        return ["MANIFEST.json ausente ou inválido."]

    meta = manifest.get("_meta", {})
    if meta.get("total_arquivos") != meta.get("arquivos_esperados"):
        motivos.append(
            "MANIFEST: total_arquivos difere de arquivos_esperados "
            f"({meta.get('total_arquivos')} != {meta.get('arquivos_esperados')})."
        )
    for chave in ("ausentes", "divergentes"):
        if meta.get(chave):
            motivos.append(f"MANIFEST: campo {chave} não está vazio.")

    for nome, registro in (manifest.get("arquivos") or {}).items():
        arquivo = pasta / nome
        if not arquivo.is_file():
            motivos.append(f"MANIFEST: arquivo listado não existe: {nome}.")
            continue
        esperado = registro.get("sha256")
        if esperado and _sha256(arquivo) != esperado:
            motivos.append(f"MANIFEST: hash divergente para {nome}.")
        tamanho = registro.get("tamanho")
        if isinstance(tamanho, int) and arquivo.stat().st_size != tamanho:
            motivos.append(f"MANIFEST: tamanho divergente para {nome}.")

    return motivos


def _verificar_contagens(pasta: Path) -> list[str]:
    motivos: list[str] = []

    encantamentos = _ler(pasta / "encantamentos_e_gemas_s2.json") or {}
    gemas = encantamentos.get("gemas") or {}
    encantos = encantamentos.get("encantamentos") or {}
    if len(gemas) != CONTAGENS_ESPERADAS["gemas"]:
        motivos.append(
            f"gemas: esperado {CONTAGENS_ESPERADAS['gemas']}, encontrado {len(gemas)}."
        )
    if len(encantos) != CONTAGENS_ESPERADAS["encantamentos"]:
        motivos.append(
            "encantamentos: esperado "
            f"{CONTAGENS_ESPERADAS['encantamentos']}, encontrado {len(encantos)}."
        )

    enchant_ids = (_ler(pasta / "enchant_ids_s2.json") or {}).get("enchants") or {}
    if len(enchant_ids) != CONTAGENS_ESPERADAS["enchant_ids"]:
        motivos.append(
            "enchant_ids: esperado "
            f"{CONTAGENS_ESPERADAS['enchant_ids']}, encontrado {len(enchant_ids)}."
        )

    runas = _ler(pasta / "rune_ids_s2.json") or {}
    lista_runas = runas.get("runas") or []
    if len(lista_runas) != CONTAGENS_ESPERADAS["runas"]:
        motivos.append(
            f"runas: esperado {CONTAGENS_ESPERADAS['runas']}, encontrado {len(lista_runas)}."
        )
    combinacoes = (runas.get("estrutura") or {}).get("combinacoes_possiveis")
    if combinacoes != CONTAGENS_ESPERADAS["combinacoes_folio"]:
        motivos.append(
            "combinações do Folio: esperado "
            f"{CONTAGENS_ESPERADAS['combinacoes_folio']}, encontrado {combinacoes}."
        )

    return motivos


def _verificar_bonus(pasta: Path) -> list[str]:
    derivado = pasta / "derivados" / "bonus_ilvl.json"
    if not derivado.is_file():
        derivado = DERIVADOS_DIR / "bonus_ilvl.json"
    dados = _ler(derivado)
    if dados is None:
        return ["derivados/bonus_ilvl.json ausente ou inválido."]

    bonus = dados.get("bonus") or {}
    motivos: list[str] = []
    for bonus_id, ilvl in BONUS_ILVL_ESPERADO.items():
        registro = bonus.get(str(bonus_id)) or {}
        if registro.get("ilvl") != ilvl:
            motivos.append(
                f"bonus {bonus_id}: ilvl esperado {ilvl}, encontrado "
                f"{registro.get('ilvl')}."
            )
    return motivos


def _verificar_nomes_e_build(pasta: Path) -> list[str]:
    motivos: list[str] = []
    stats = (_ler(pasta / "stats_oficiais_itens.json") or {}).get("itens") or {}
    if len(stats) < 100:
        motivos.append(f"stats_oficiais_itens: apenas {len(stats)} itens (mínimo 100).")

    referencia = stats.get(str(ITEM_REFERENCIA)) or {}
    if not referencia.get("nome_pt") or not referencia.get("nome_en"):
        motivos.append(
            f"item {ITEM_REFERENCIA}: nome PT/EN ausente no snapshot."
        )

    contexto = pasta / "season2_context.json"
    try:
        texto = contexto.read_text(encoding="utf-8")
    except OSError:
        return motivos + ["season2_context.json ilegível."]

    patch = ".".join(simc_runner.BUILD_ESPERADO.split(".")[:2])
    if patch not in texto:
        motivos.append(f"season2_context: patch {patch} não encontrado.")
    return motivos


def _verificar_monitor(pasta: Path) -> list[str]:
    monitor = _ler(pasta / "monitor_upgrades_s2.json") or {}
    teto = monitor.get("teto_341") or []
    if len(teto) < 50:
        return [f"monitor_upgrades_s2: apenas {len(teto)} itens em teto_341."]
    sem_peconha = [item for item in teto if isinstance(item, dict) and not item.get("peconha")]
    if sem_peconha:
        return ["monitor_upgrades_s2: itens sem campo peconha."]
    return []


def verificar(caminho_dados: str | Path) -> list[str]:
    """Validate a snapshot directory. Empty list means the gate passed."""
    pasta = Path(caminho_dados)
    if not pasta.is_dir():
        return [f"diretório de dados inexistente: {pasta}"]

    motivos: list[str] = []
    for nome in ARQUIVOS_OBRIGATORIOS:
        if not (pasta / nome).is_file():
            motivos.append(f"arquivo obrigatório ausente: {nome}.")
    if motivos:
        return motivos

    motivos.extend(_verificar_manifest(pasta))
    motivos.extend(_verificar_contagens(pasta))
    motivos.extend(_verificar_bonus(pasta))
    motivos.extend(_verificar_nomes_e_build(pasta))
    motivos.extend(_verificar_monitor(pasta))
    return motivos
