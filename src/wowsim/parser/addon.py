"""Parse the SimulationCraft AddOn export.

The parser is a section-aware state machine: the same key means different
things in the main block and in "Gear from Bags". The original text is kept so
the equipment block can be serialized back byte for byte.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import AlertaParse, ItemEquipado, MarcaIlvl, Personagem

SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "tabard",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
)

CLASS_KEYS = {
    "warlock",
    "druid",
    "priest",
    "mage",
    "hunter",
    "rogue",
    "paladin",
    "warrior",
    "deathknight",
    "shaman",
    "monk",
    "demonhunter",
    "evoker",
}

KNOWN_FIELDS = {
    "id",
    "enchant_id",
    "gem_id",
    "gem_id2",
    "gem_id3",
    "bonus_id",
    "content_tuning",
    "crafted_stats",
    "crafting_quality",
    "drop_level",
    "redirected_base_stats",
}

SLOT_RE = re.compile(r"^([a-z_0-9]+)=,(.*)$")
BAG_SLOT_RE = re.compile(r"^#\s*([a-z_0-9]+)=,(.*)$")
COMMENT_ILVL_RE = re.compile(r"^#\s+(.+?)\s+\((\d+)\)\s*$")
LOADOUT_RE = re.compile(r"^#\s*Saved Loadout:\s*(.+?)\s*$")
CHECKSUM_RE = re.compile(r"^#\s*Checksum:\s*([0-9a-fA-F]{8})\s*$")
ADDON_RE = re.compile(r"SimC AddOn\s+([0-9][0-9.\-]*)", re.IGNORECASE)
BUILD_RE = re.compile(r"WoW\s+([0-9][0-9.]*),")
HEADER_DATE_RE = re.compile(r"^#\s+.+\s+-\s+.+\s+-\s+\d{4}-\d{2}-\d{2}")
KEY_VALUE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


class ErroParseAddon(ValueError):
    """Base parser error."""


class FormatoAmrRejeitado(ErroParseAddon):
    """The text looks like an AskMrRobot export."""


class FormatoDesconhecido(ErroParseAddon):
    """The text is neither a SimC addon export nor a recognizable format."""


class ErroRoundTrip(ErroParseAddon):
    """The original equipment block is unavailable."""


def _int(valor: str, campo: str, indice: int, alertas: list[AlertaParse]) -> int | None:
    try:
        return int(valor.strip())
    except (TypeError, ValueError):
        alertas.append(
            AlertaParse(
                codigo="campo_nao_numerico",
                detalhe=f"{campo}={valor!r}",
                linha=indice + 1,
            )
        )
        return None


def _parse_item(
    slot: str,
    resto: str,
    *,
    origem: str,
    indice: int,
    linha_original: str,
    nome: str | None,
    ilvl: int | None,
    alertas: list[AlertaParse],
) -> ItemEquipado:
    campos: dict[str, str] = {}
    ordem: list[str] = []
    for bruto in resto.split(","):
        token = bruto.strip()
        if not token:
            continue
        if "=" not in token:
            alertas.append(
                AlertaParse(
                    codigo="campo_sem_igual",
                    detalhe=f"{slot}: {token}",
                    linha=indice + 1,
                )
            )
            continue
        chave, valor = token.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        if not chave:
            alertas.append(
                AlertaParse(
                    codigo="campo_sem_nome",
                    detalhe=token,
                    linha=indice + 1,
                )
            )
            continue
        campos[chave] = valor
        ordem.append(chave)

    extras = {k: v for k, v in campos.items() if k not in KNOWN_FIELDS}

    bonus_ids: list[int] = []
    if "bonus_id" in campos:
        for parte in campos["bonus_id"].split("/"):
            numero = _int(parte, "bonus_id", indice, alertas)
            if numero is not None:
                bonus_ids.append(numero)

    gem_ids: list[int] = []
    for chave in ordem:
        if chave == "gem_id" or chave.startswith("gem_id"):
            numero = _int(campos[chave], chave, indice, alertas)
            if numero is not None:
                gem_ids.append(numero)

    crafted_stats: tuple[int, int] | None = None
    if "crafted_stats" in campos:
        partes = campos["crafted_stats"].split("/")
        if len(partes) == 2:
            a = _int(partes[0], "crafted_stats", indice, alertas)
            b = _int(partes[1], "crafted_stats", indice, alertas)
            if a is not None and b is not None:
                crafted_stats = (a, b)
        else:
            alertas.append(
                AlertaParse(
                    codigo="crafted_stats_invalido",
                    detalhe=campos["crafted_stats"],
                    linha=indice + 1,
                )
            )

    item = ItemEquipado(
        slot=slot,
        item_id=_int(campos["id"], "id", indice, alertas) if "id" in campos else None,
        enchant_id=(
            _int(campos["enchant_id"], "enchant_id", indice, alertas)
            if "enchant_id" in campos
            else None
        ),
        gem_ids=gem_ids,
        bonus_ids=bonus_ids,
        crafted_stats=crafted_stats,
        crafting_quality=(
            _int(campos["crafting_quality"], "crafting_quality", indice, alertas)
            if "crafting_quality" in campos
            else None
        ),
        content_tuning=(
            _int(campos["content_tuning"], "content_tuning", indice, alertas)
            if "content_tuning" in campos
            else None
        ),
        drop_level=(
            _int(campos["drop_level"], "drop_level", indice, alertas)
            if "drop_level" in campos
            else None
        ),
        redirected_base_stats=(
            _int(campos["redirected_base_stats"], "redirected_base_stats", indice, alertas)
            if "redirected_base_stats" in campos
            else None
        ),
        ilvl_comentario=ilvl,
        nome_pt=nome,
        origem_linha=origem,  # type: ignore[arg-type]
        indice_linha=indice if origem == "equipado" else None,
        linha_original=linha_original,
        campos_extras=extras,
    )
    return item


def _parse_pares(texto: str, campo: str, indice: int, alertas: list[AlertaParse]) -> dict[int, int]:
    pares: dict[int, int] = {}
    for parte in texto.split("/"):
        if not parte.strip():
            continue
        pedacos = parte.split(":")
        if len(pedacos) != 2:
            alertas.append(
                AlertaParse(
                    codigo="par_invalido",
                    detalhe=f"{campo}: {parte}",
                    linha=indice + 1,
                )
            )
            continue
        chave = _int(pedacos[0], campo, indice, alertas)
        valor = _int(pedacos[1], campo, indice, alertas)
        if chave is not None and valor is not None:
            pares[chave] = valor
    return pares


def parse_texto(
    texto: str,
    *,
    classe_hint: str | None = None,
    spec_hint: str | None = None,
    incluir_inv: bool = False,
) -> Personagem:
    """Parse the addon text (SimC or AMR v181) into a Personagem.

    Text starting with ``$`` is decoded as an AskMrRobot export via
    :mod:`wowsim.parser.amr` (ADR-002). ``classe_hint``/``spec_hint`` são
    necessários para o AMR, cujo cabeçalho de classe é ambíguo.
    """
    linhas = texto.splitlines(keepends=True)
    uteis = [linha.strip() for linha in linhas if linha.strip()]

    if not uteis:
        raise FormatoDesconhecido("Texto vazio; cole a saída de /simc.")

    primeira = uteis[0]
    if primeira.startswith("$"):
        from .amr import ErroAmr, para_personagem, parse_amr

        try:
            importacao = parse_amr(texto)
        except ErroAmr as exc:
            raise FormatoDesconhecido(str(exc)) from exc
        return para_personagem(
            importacao,
            classe_hint=classe_hint,
            spec_hint=spec_hint,
            incluir_inv=incluir_inv,
        )
    if not (
        primeira.startswith("#")
        and (ADDON_RE.search(texto) or HEADER_DATE_RE.match(primeira))
    ):
        raise FormatoDesconhecido(
            "Formato desconhecido. A primeira linha deve ser um comentário do "
            "export do SimC AddOn, como '# Nome - Spec - data - Região/Servidor'."
        )

    alertas: list[AlertaParse] = []
    personagem = Personagem(texto_original=texto, versao_addon=None)

    secao = "principal"
    pendente_nome: str | None = None
    pendente_ilvl: int | None = None
    pendente_loadout: str | None = None
    bloco_inicio: int | None = None
    bloco_fim: int | None = None

    inicios: list[int] = []
    posicao = 0
    for linha in linhas:
        inicios.append(posicao)
        posicao += len(linha)

    for indice, linha in enumerate(linhas):
        bruta = linha.rstrip("\r\n")
        s = bruta.strip()
        if not s:
            continue

        if s.startswith("### "):
            if "Gear from Bags" in s:
                secao = "mochila"
            elif "Additional Character Info" in s:
                secao = "info"
            else:
                secao = "outra"
                alertas.append(
                    AlertaParse(
                        codigo="secao_desconhecida",
                        detalhe=s,
                        linha=indice + 1,
                    )
                )
            pendente_nome = None
            pendente_ilvl = None
            continue

        casamento_checksum = CHECKSUM_RE.match(s)
        if casamento_checksum:
            personagem.checksum = casamento_checksum.group(1)
            continue

        if secao == "info":
            if not s.startswith("#"):
                continue
            corpo = s[1:].strip()
            if "=" not in corpo:
                continue
            chave, valor = corpo.split("=", 1)
            chave = chave.strip()
            valor = valor.strip()

            if chave == "catalyst_currencies":
                personagem.catalyst_currencies = _parse_pares(valor, chave, indice, alertas)
            elif chave == "upgrade_currencies":
                moedas: dict[str, int] = {}
                for parte in valor.split("/"):
                    if not parte.strip():
                        continue
                    pedacos = parte.split(":")
                    if len(pedacos) != 3 or pedacos[0] not in {"c", "i"}:
                        alertas.append(
                            AlertaParse(
                                codigo="moeda_upgrade_invalida",
                                detalhe=parte,
                                linha=indice + 1,
                            )
                        )
                        continue
                    numero = _int(pedacos[2], chave, indice, alertas)
                    if numero is not None:
                        moedas[f"{pedacos[0]}:{pedacos[1]}"] = numero
                personagem.upgrade_currencies = moedas
            elif chave == "slot_high_watermarks":
                marcas: list[MarcaIlvl] = []
                for parte in valor.split("/"):
                    if not parte.strip():
                        continue
                    pedacos = parte.split(":")
                    if len(pedacos) != 3:
                        alertas.append(
                            AlertaParse(
                                codigo="watermark_invalida",
                                detalhe=parte,
                                linha=indice + 1,
                            )
                        )
                        continue
                    numeros = [
                        _int(pedaco, chave, indice, alertas) for pedaco in pedacos
                    ]
                    if any(numero is None for numero in numeros):
                        continue
                    indice_slot, atual, maximo = (int(numero) for numero in numeros)  # type: ignore[arg-type]
                    if atual > maximo:
                        alertas.append(
                            AlertaParse(
                                codigo="watermark_invertida",
                                detalhe=f"índice {indice_slot}: {atual} > {maximo}",
                                linha=indice + 1,
                                severidade="bloqueio",
                            )
                        )
                    marcas.append(
                        MarcaIlvl(
                            indice=indice_slot,
                            ilvl_atual=atual,
                            ilvl_maximo=maximo,
                            mapeado=indice_slot == 14,
                        )
                    )
                personagem.slot_high_watermarks = marcas
            elif chave == "bonus_roll_currencies":
                personagem.bonus_roll_currencies = _parse_pares(
                    valor, chave, indice, alertas
                )
            elif chave == "bonus_roll_items":
                personagem.bonus_roll_items = valor
            elif chave == "upgrade_achievements":
                ids: list[int] = []
                for parte in valor.split("/"):
                    if not parte.strip():
                        continue
                    numero = _int(parte, chave, indice, alertas)
                    if numero is not None:
                        ids.append(numero)
                personagem.upgrade_achievements = ids
            continue

        if secao == "mochila":
            casamento = BAG_SLOT_RE.match(s)
            if casamento:
                slot = casamento.group(1)
                item = _parse_item(
                    slot,
                    casamento.group(2),
                    origem="mochila",
                    indice=indice,
                    linha_original=s,
                    nome=pendente_nome,
                    ilvl=pendente_ilvl,
                    alertas=alertas,
                )
                personagem.mochila.setdefault(slot, []).append(item)
                pendente_nome = None
                pendente_ilvl = None
                continue
            comentario = COMMENT_ILVL_RE.match(s)
            if comentario:
                pendente_nome = comentario.group(1).strip()
                pendente_ilvl = int(comentario.group(2))
            continue

        if secao == "outra":
            continue

        # Main section.
        casamento_loadout = LOADOUT_RE.match(s)
        if casamento_loadout:
            if pendente_loadout is not None:
                alertas.append(
                    AlertaParse(
                        codigo="loadout_sem_talents",
                        detalhe=pendente_loadout,
                        linha=indice + 1,
                    )
                )
            pendente_loadout = casamento_loadout.group(1).strip()
            continue

        if s.startswith("# talents=") and pendente_loadout is not None:
            personagem.loadouts[pendente_loadout] = s.split("=", 1)[1].strip()
            pendente_loadout = None
            continue

        if s.startswith("# loot_spec="):
            personagem.loot_spec = s.split("=", 1)[1].strip()
            continue

        casamento_checksum = CHECKSUM_RE.match(s)
        if casamento_checksum:
            personagem.checksum = casamento_checksum.group(1)
            continue

        comentario = COMMENT_ILVL_RE.match(s)
        if comentario:
            pendente_nome = comentario.group(1).strip()
            pendente_ilvl = int(comentario.group(2))
            continue

        if s.startswith("omnium_talents="):
            bruto = s.split("=", 1)[1].strip()
            ids: list[int] = []
            ranks: dict[int, int] = {}
            for parte in bruto.split("/"):
                if not parte.strip():
                    continue
                pedacos = parte.split(":")
                if len(pedacos) != 2:
                    alertas.append(
                        AlertaParse(
                            codigo="omnium_invalido",
                            detalhe=parte,
                            linha=indice + 1,
                        )
                    )
                    continue
                runa = _int(pedacos[0], "omnium_talents", indice, alertas)
                rank = _int(pedacos[1], "omnium_talents", indice, alertas)
                if runa is None or rank is None:
                    continue
                ids.append(runa)
                ranks[runa] = rank
            personagem.omnium_ids_brutos = ids
            personagem.omnium_ranks = ranks
            if ids and len(ids) != 5:
                alertas.append(
                    AlertaParse(
                        codigo="omnium_incompleto",
                        detalhe=f"{len(ids)} entradas; esperado 5",
                        linha=indice + 1,
                    )
                )
            continue

        casamento_slot = SLOT_RE.match(s)
        if casamento_slot:
            slot = casamento_slot.group(1)
            if slot not in SLOTS:
                alertas.append(
                    AlertaParse(
                        codigo="slot_desconhecido",
                        detalhe=slot,
                        linha=indice + 1,
                    )
                )
            item = _parse_item(
                slot,
                casamento_slot.group(2),
                origem="equipado",
                indice=indice,
                linha_original=s,
                nome=pendente_nome,
                ilvl=pendente_ilvl,
                alertas=alertas,
            )
            personagem.equipado[slot] = item
            if bloco_inicio is None:
                anterior = linhas[indice - 1].strip() if indice > 0 else ""
                if COMMENT_ILVL_RE.match(anterior):
                    bloco_inicio = indice - 1
                else:
                    bloco_inicio = indice
            bloco_fim = indice
            pendente_nome = None
            pendente_ilvl = None
            continue

        # Header key/value lines.
        casamento_kv = KEY_VALUE_RE.match(s)
        if casamento_kv:
            chave = casamento_kv.group(1)
            valor = casamento_kv.group(2).strip()
            if chave in CLASS_KEYS:
                personagem.classe = chave
                personagem.nome = valor.strip('"')
            elif chave == "level":
                personagem.nivel = _int(valor, chave, indice, alertas)
            elif chave == "race":
                personagem.raca = valor
            elif chave == "region":
                personagem.regiao = valor
            elif chave == "server":
                personagem.servidor = valor
            elif chave == "role":
                personagem.role = valor
            elif chave == "spec":
                personagem.spec = valor
            elif chave == "professions":
                profissoes: dict[str, int] = {}
                for parte in valor.split("/"):
                    if "=" not in parte:
                        continue
                    nome_prof, nivel_prof = parte.split("=", 1)
                    numero = _int(nivel_prof, "professions", indice, alertas)
                    if numero is not None:
                        profissoes[nome_prof.strip()] = numero
                personagem.profissoes = profissoes
            elif chave == "talents":
                if personagem.talents_atual is None:
                    personagem.talents_atual = valor
            continue

    casamento_versao = ADDON_RE.search(texto)
    if casamento_versao:
        personagem.versao_addon = casamento_versao.group(1)
    casamento_build = BUILD_RE.search(texto)
    if casamento_build:
        personagem.build_cliente = casamento_build.group(1)

    if pendente_loadout is not None:
        alertas.append(
            AlertaParse(
                codigo="loadout_sem_talents",
                detalhe=pendente_loadout,
                linha=None,
            )
        )
    if personagem.checksum is None:
        alertas.append(
            AlertaParse(
                codigo="checksum_ausente",
                severidade="info",
                detalhe="Export sem linha '# Checksum'.",
            )
        )
    if not personagem.equipado:
        alertas.append(
            AlertaParse(
                codigo="equipamento_ausente",
                severidade="info",
                detalhe="Nenhum slot equipado encontrado.",
            )
        )
    if bloco_inicio is not None and bloco_fim is not None:
        fim = inicios[bloco_fim] + len(linhas[bloco_fim].rstrip("\r\n"))
        personagem.bloco_equipamento_original = texto[inicios[bloco_inicio]:fim]

    personagem.alertas = alertas
    return personagem


def parse_arquivo(caminho: str | Path) -> Personagem:
    texto = Path(caminho).read_text(encoding="utf-8")
    return parse_texto(texto)


def serializar_bloco_equipamento(personagem: Personagem) -> str:
    """Return the original equipment block, byte for byte."""
    if not personagem.bloco_equipamento_original:
        raise ErroRoundTrip("O parser não guardou o bloco de equipamento original.")
    return personagem.bloco_equipamento_original


def serializar_texto(personagem: Personagem, *, incluir_checksum: bool = False) -> str:
    """Rebuild the full text, replacing slot lines with the current model.

    Unchanged items keep their original line, so the output is byte-identical
    to the input when nothing was modified.
    """
    linhas = personagem.texto_original.splitlines(keepends=True)
    substituicoes = {
        item.indice_linha: item
        for item in personagem.equipado.values()
        if item.indice_linha is not None
    }

    saida: list[str] = []
    for indice, linha in enumerate(linhas):
        if indice in substituicoes:
            item = substituicoes[indice]
            if linha.endswith("\r\n"):
                fim = "\r\n"
            elif linha.endswith("\n"):
                fim = "\n"
            else:
                fim = ""
            saida.append(item.linha_original + fim)
            continue
        if not incluir_checksum and CHECKSUM_RE.match(linha.strip()):
            continue
        saida.append(linha)
    return "".join(saida)
