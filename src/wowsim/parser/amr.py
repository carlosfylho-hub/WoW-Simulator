"""Parser puro do export AskMrRobot v181.

Decodifica o envelope ``$...$`` em um modelo neutro (:class:`ImportAMR`) sem
converter ainda para :class:`~wowsim.models.Personagem` (isso é a Fase 2).
Nada é estimado: campos desconhecidos viram aviso e ficam preservados no token
bruto para auditoria.

Token de item (confirmado no ADR-001/ADR-002)::

    <item_id> s<slot> n<content_tuning>?  (b<bonus_id>)*
    (j<crafted1>)? (k<crafted2>)? (l<crafting_quality>)?
    (d<drop_level>)? (e<enchant_id>)? (x<gem_id>)*  !A<checksum>
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import AlertaParse, ItemEquipado, MarcaIlvl, Personagem
from ..paths import DADOS_DIR

# Slots do AskMrRobot (1..17) para os nomes internos do projeto.
SLOTS_AMR: dict[int, str] = {
    1: "head",
    2: "neck",
    3: "shoulder",
    4: "shirt",
    5: "chest",
    6: "waist",
    7: "legs",
    8: "feet",
    9: "wrist",
    10: "hands",
    11: "finger1",
    12: "finger2",
    13: "trinket1",
    14: "trinket2",
    15: "back",
    16: "main_hand",
    17: "off_hand",
}

_MARCADOR_SECAO = re.compile(r"^\.([a-z]+\d*)$", re.IGNORECASE)
_TOKEN_ITEM = re.compile(r"^(\d+)s(\d+)(?:n(-?\d+))?(.*)$")
_CAMPO_NUMERICO = re.compile(r"([a-zA-Z!])(-?\d+)")
_CHECKSUM = re.compile(r"!A([0-9A-Fa-f]+)")


class ErroAmr(ValueError):
    """Texto não é um export AskMrRobot reconhecível."""


class ItemAMR(BaseModel):
    """Um item decodificado do conjunto AMR."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int
    content_tuning: int | None = None
    bonus_ids: list[int] = Field(default_factory=list)
    bonus_ids_negativos: list[int] = Field(default_factory=list)
    crafted_stats: tuple[int, int] | None = None
    crafting_quality: int | None = None
    drop_level: int | None = None
    enchant_id: int | None = None
    gem_ids: list[int] = Field(default_factory=list)
    checksum: str | None = None
    campos_desconhecidos: list[str] = Field(default_factory=list)
    token_bruto: str


class ConjuntoAMR(BaseModel):
    """Um conjunto de equipamento (``.q2``, ``.q3``...)."""

    model_config = ConfigDict(extra="forbid")

    chave: str
    itens: dict[str, ItemAMR] = Field(default_factory=dict)
    slots_desconhecidos: list[int] = Field(default_factory=list)


class TalentoAMR(BaseModel):
    """Conjunto de talentos cru (``.s2``/``.s3``); não vira import string SimC."""

    model_config = ConfigDict(extra="forbid")

    chave: str
    grupo: int | None = None
    talentos: str | None = None
    runas: dict[int, int] = Field(default_factory=dict)


class WatermarkAMR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indice: int
    atual: int
    maximo: int


class ImportAMR(BaseModel):
    """Resultado da decodificação de um export AMR v181."""

    model_config = ConfigDict(extra="forbid")

    versao: str | None = None
    regiao: str | None = None
    reino: str | None = None
    nome: str | None = None
    guilda: str | None = None
    raca_id: int | None = None
    classe_id: int | None = None
    nivel: int | None = None
    campo_extra: str | None = None
    moedas: dict[int, int] = Field(default_factory=dict)
    conjuntos: dict[str, ConjuntoAMR] = Field(default_factory=dict)
    talentos: dict[str, TalentoAMR] = Field(default_factory=dict)
    watermarks: list[WatermarkAMR] = Field(default_factory=list)
    inv: list[str] = Field(default_factory=list)
    ach: list[int] = Field(default_factory=list)
    avisos: list[AlertaParse] = Field(default_factory=list)
    texto_original: str = Field(exclude=True, repr=False)

    @property
    def conjunto_atual(self) -> ConjuntoAMR | None:
        """AMR coloca o conjunto ativo em ``.q2``; cai no primeiro ``.q``."""
        if "q2" in self.conjuntos:
            return self.conjuntos["q2"]
        for chave in sorted(self.conjuntos):
            return self.conjuntos[chave]
        return None


def detectar(texto: str) -> bool:
    """True quando o texto parece um export AMR (começa com ``$``)."""
    return texto.lstrip().startswith("$")


def _int(texto: str | None) -> int | None:
    if texto is None:
        return None
    try:
        return int(texto.strip())
    except (TypeError, ValueError):
        return None


def _secoes(tokens: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Separa o cabeçalho das seções ``.sN``/``.qN``/``.tal``/... """
    cabecalho: list[str] = []
    indice = 0
    while indice < len(tokens) and not _MARCADOR_SECAO.match(tokens[indice].strip()):
        cabecalho.append(tokens[indice])
        indice += 1

    secoes: dict[str, list[str]] = {}
    while indice < len(tokens):
        marcador = tokens[indice].strip()
        casamento = _MARCADOR_SECAO.match(marcador)
        indice += 1
        if casamento is None:
            continue
        chave = casamento.group(1).lower()
        valores: list[str] = []
        while indice < len(tokens) and not _MARCADOR_SECAO.match(tokens[indice].strip()):
            valores.append(tokens[indice])
            indice += 1
        secoes[chave] = valores
    return cabecalho, secoes


def _decodificar_item(token: str, avisos: list[AlertaParse]) -> ItemAMR | None:
    casamento = _TOKEN_ITEM.match(token)
    if casamento is None:
        avisos.append(
            AlertaParse(codigo="amr_item_invalido", detalhe=token, severidade="aviso")
        )
        return None

    item_id = int(casamento.group(1))
    slot_numero = int(casamento.group(2))
    tuning = _int(casamento.group(3))
    resto = casamento.group(4)

    slot = SLOTS_AMR.get(slot_numero)
    if slot is None:
        slot = f"slot_{slot_numero}"
        avisos.append(
            AlertaParse(
                codigo="amr_slot_desconhecido",
                detalhe=f"slot {slot_numero} no item {item_id}",
                severidade="aviso",
            )
        )

    bonus_ids: list[int] = []
    bonus_negativos: list[int] = []
    crafted: list[int] = []
    qualidade: int | None = None
    drop: int | None = None
    enchant: int | None = None
    gems: list[int] = []
    desconhecidos: list[str] = []

    for campo in _CAMPO_NUMERICO.finditer(resto):
        tag = campo.group(1)
        valor = int(campo.group(2))
        if tag == "b":
            if valor < 0:
                bonus_negativos.append(valor)
            else:
                bonus_ids.append(valor)
        elif tag in ("j", "k"):
            crafted.append(valor)
        elif tag == "l":
            qualidade = valor
        elif tag == "d":
            drop = valor
        elif tag == "e":
            enchant = valor
        elif tag == "x":
            if valor > 0:
                gems.append(valor)
            else:
                desconhecidos.append(f"x{valor}")
        else:
            desconhecidos.append(f"{tag}{valor}")

    checksum = _CHECKSUM.search(resto)

    return ItemAMR(
        slot=slot,
        item_id=item_id,
        content_tuning=tuning,
        bonus_ids=bonus_ids,
        bonus_ids_negativos=bonus_negativos,
        crafted_stats=(crafted[0], crafted[1]) if len(crafted) >= 2 else None,
        crafting_quality=qualidade,
        drop_level=drop,
        enchant_id=enchant,
        gem_ids=gems,
        checksum=checksum.group(1) if checksum else None,
        campos_desconhecidos=desconhecidos,
        token_bruto=token,
    )


def _parse_conjunto(chave: str, tokens: list[str], avisos: list[AlertaParse]) -> ConjuntoAMR:
    itens: dict[str, ItemAMR] = {}
    desconhecidos: list[int] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        item = _decodificar_item(token, avisos)
        if item is None:
            continue
        if item.slot.startswith("slot_"):
            desconhecidos.append(int(item.slot.split("_", 1)[1]))
        # Mesa de anéis/berloques: AMR já traz finger1/finger2 explícitos.
        itens[item.slot] = item
    return ConjuntoAMR(chave=chave, itens=itens, slots_desconhecidos=desconhecidos)


def _parse_talentos(chave: str, tokens: list[str]) -> TalentoAMR:
    valores = [token.strip() for token in tokens]
    grupo = _int(valores[0]) if valores else None
    talentos = valores[1] if len(valores) > 1 and valores[1] else None
    runas: dict[int, int] = {}
    if len(valores) > 2 and valores[2]:
        for par in valores[2].split("_"):
            if "=" not in par:
                continue
            esquerda, direita = par.split("=", 1)
            id_runo = _int(esquerda)
            rank = _int(direita)
            if id_runo is not None and rank is not None:
                runas[id_runo] = rank
    return TalentoAMR(chave=chave, grupo=grupo, talentos=talentos, runas=runas)


def _parse_watermarks(tokens: list[str]) -> list[WatermarkAMR]:
    saida: list[WatermarkAMR] = []
    for token in tokens:
        partes = token.strip().split("|")
        if len(partes) != 3:
            continue
        indice, atual, maximo = (_int(parte) for parte in partes)
        if indice is None or atual is None or maximo is None:
            continue
        saida.append(WatermarkAMR(indice=indice, atual=atual, maximo=maximo))
    return saida


def parse_amr(texto: str) -> ImportAMR:
    """Decodifica um export AMR v181. Levanta :class:`ErroAmr` se inválido."""
    bruto = texto.strip()
    if not detectar(bruto):
        raise ErroAmr("O texto não começa com '$'; não é um export AskMrRobot.")

    corpo = bruto
    if corpo.startswith("$"):
        corpo = corpo[1:]
    if corpo.endswith("$"):
        corpo = corpo[:-1]

    tokens = corpo.split(";")
    cabecalho, secoes = _secoes(tokens)
    if len(cabecalho) < 8:
        raise ErroAmr("Cabeçalho AMR incompleto (menos de 8 campos).")

    avisos: list[AlertaParse] = []

    moedas: dict[int, int] = {}
    if len(cabecalho) > 8 and cabecalho[8]:
        for par in cabecalho[8].split(","):
            if ":" not in par:
                continue
            chave, valor = par.split(":", 1)
            chave_id = _int(chave)
            valor_id = _int(valor)
            if chave_id is not None and valor_id is not None:
                moedas[chave_id] = valor_id

    importacao = ImportAMR(
        versao=cabecalho[0] or None,
        regiao=cabecalho[1] or None,
        reino=cabecalho[2] or None,
        nome=cabecalho[3] or None,
        guilda=cabecalho[4] or None,
        raca_id=_int(cabecalho[5]) if len(cabecalho) > 5 else None,
        classe_id=_int(cabecalho[6]) if len(cabecalho) > 6 else None,
        nivel=_int(cabecalho[7]) if len(cabecalho) > 7 else None,
        campo_extra=cabecalho[9] if len(cabecalho) > 9 and cabecalho[9] else None,
        moedas=moedas,
        inv=[token for token in secoes.get("inv", []) if token],
        ach=[
            valor
            for token in secoes.get("ach", [])
            if (valor := _int(token)) is not None
        ],
        watermarks=_parse_watermarks(secoes.get("hlv", [])),
        avisos=avisos,
        texto_original=texto,
    )

    for chave, valores in secoes.items():
        if chave in ("inv", "gv", "hlv", "ach", "tal"):
            continue
        if chave.startswith("q"):
            importacao.conjuntos[chave] = _parse_conjunto(chave, valores, avisos)
        elif chave.startswith("s"):
            importacao.talentos[chave] = _parse_talentos(chave, valores)

    if not importacao.conjuntos:
        avisos.append(
            AlertaParse(
                codigo="amr_sem_conjunto",
                detalhe="Nenhuma seção .qN encontrada.",
                severidade="aviso",
            )
        )
    return importacao


# ---------------------------------------------------------------------------
# Fase 2: adaptador AMR -> Personagem + texto SimC canônico
# ---------------------------------------------------------------------------

_ORDEM_SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
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

_CLASSES = {
    "warrior": "warrior",
    "guerreiro": "warrior",
    "paladin": "paladin",
    "paladino": "paladin",
    "hunter": "hunter",
    "caçador": "hunter",
    "cacador": "hunter",
    "rogue": "rogue",
    "ladino": "rogue",
    "priest": "priest",
    "sacerdote": "priest",
    "deathknight": "deathknight",
    "cavaleiro da morte": "deathknight",
    "shaman": "shaman",
    "xamã": "shaman",
    "xama": "shaman",
    "mage": "mage",
    "mago": "mage",
    "monk": "monk",
    "monge": "monk",
    "druid": "druid",
    "druida": "druid",
    "demonhunter": "demonhunter",
    "caçador de demônios": "demonhunter",
    "cacador de demonios": "demonhunter",
    "evoker": "evoker",
    "evocador": "evoker",
    "warlock": "warlock",
    "bruxo": "warlock",
}


def _slug_texto(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


def normalizar_classe(valor: str | None) -> str | None:
    """Converte nome PT/EN da classe para o token interno (ex.: warlock)."""
    if not valor:
        return None
    return _CLASSES.get(_slug_texto(valor))


_MAPA_ARQUIVO = "amr_mapa.json"


@lru_cache(maxsize=1)
def _mapa() -> dict:
    try:
        return json.loads((DADOS_DIR / _MAPA_ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"versoes": {}}


def limpar_cache_mapa() -> None:
    _mapa.cache_clear()


def classe_da_spec(versao: str | None, spec_id: int | None) -> str | None:
    """Classe para um (versão, spec_id) do AMR, ou None se não mapeado."""
    if versao is None or spec_id is None:
        return None
    dados = _mapa().get("versoes", {}).get(str(versao))
    if not isinstance(dados, dict):
        return None
    return dados.get("specs", {}).get(str(spec_id))


def classe_do_import(importacao: ImportAMR) -> str | None:
    """Infere a classe votando nos ids de spec das seções ``.sN``."""
    votos: dict[str, int] = {}
    for talento in importacao.talentos.values():
        classe = classe_da_spec(importacao.versao, talento.grupo)
        if classe:
            votos[classe] = votos.get(classe, 0) + 1
    if not votos:
        return None
    return max(votos, key=votos.get)


def raca_da_import(importacao: ImportAMR) -> str | None:
    """Nome da raça a partir do enum autoritativo do addon (``amr_mapa.json``)."""
    if importacao.versao is None or importacao.raca_id is None:
        return None
    dados = _mapa().get("versoes", {}).get(str(importacao.versao))
    if not isinstance(dados, dict):
        return None
    return dados.get("racas", {}).get(str(importacao.raca_id))


def normalizar_spec(valor: str | None) -> str | None:
    if not valor:
        return None
    return re.sub(r"[^a-z0-9_]+", "", _slug_texto(valor)) or None


def _linha_item(item: ItemAMR) -> str:
    partes = [f"{item.slot}=", f"id={item.item_id}"]
    if item.enchant_id:
        partes.append(f"enchant_id={item.enchant_id}")
    for indice, gema in enumerate(item.gem_ids):
        campo = "gem_id" if indice == 0 else f"gem_id{indice + 1}"
        partes.append(f"{campo}={gema}")
    if item.bonus_ids:
        partes.append("bonus_id=" + "/".join(str(bonus) for bonus in item.bonus_ids))
    if item.content_tuning is not None:
        partes.append(f"content_tuning={item.content_tuning}")
    if item.crafted_stats is not None:
        partes.append(
            f"crafted_stats={item.crafted_stats[0]}/{item.crafted_stats[1]}"
        )
    if item.crafting_quality is not None:
        partes.append(f"crafting_quality={item.crafting_quality}")
    if item.drop_level is not None:
        partes.append(f"drop_level={item.drop_level}")
    return ",".join(partes)


def para_personagem(
    importacao: ImportAMR,
    *,
    classe_hint: str | None = None,
    spec_hint: str | None = None,
    incluir_inv: bool = False,
) -> Personagem:
    """Converte um :class:`ImportAMR` em :class:`Personagem`.

    O ``texto_original`` doPersonagem é um perfil SimC canônico gerado a partir
    do conjunto ``.q2``, para que ``serializar_texto`` e o runner funcionem sem
    alterações. Classe e spec vêm de hints; o cabeçalho AMR é ambíguo e nunca é
    usado como verdade. Talentos AMR não são convertidos (não são import string
    do SimC) e geram aviso.
    """
    avisos: list[AlertaParse] = list(importacao.avisos)
    conjunto = importacao.conjunto_atual

    classe = normalizar_classe(classe_hint)
    spec = normalizar_spec(spec_hint)
    nome = importacao.nome or "Personagem AMR"

    classe_mapa = classe_do_import(importacao)
    if classe is None and classe_mapa:
        classe = classe_mapa
        avisos.append(
            AlertaParse(
                codigo="amr_classe_do_mapa",
                detalhe=f"Classe inferida das specs do export: {classe_mapa}.",
                severidade="info",
            )
        )
    elif classe and classe_mapa and classe != classe_mapa:
        avisos.append(
            AlertaParse(
                codigo="amr_classe_conflito",
                detalhe=(
                    f"classe_hint={classe!r} difere do mapa AMR ({classe_mapa!r}); "
                    "prevalece o hint."
                ),
                severidade="aviso",
            )
        )

    if classe is None:
        avisos.append(
            AlertaParse(
                codigo="amr_classe_ausente",
                detalhe=(
                    "Não foi possível inferir a classe (versão/spec fora do "
                    "amr_mapa.json); informe classe_hint (ex.: warlock)."
                ),
                severidade="aviso",
            )
        )
    if spec is None:
        avisos.append(
            AlertaParse(
                codigo="amr_spec_ausente",
                detalhe="Spec não informada; o SimC usará o padrão da classe.",
                severidade="info",
            )
        )
    if importacao.talentos:
        avisos.append(
            AlertaParse(
                codigo="amr_talentos_nao_convertidos",
                detalhe=(
                    "Talentos do AMR não são import string do SimC e não foram "
                    "aplicados; use um export SimC ou loadouts salvos."
                ),
                severidade="aviso",
            )
        )

    linhas: list[str] = [
        f"# {nome} - {spec or 'AMR'} - AMR v{importacao.versao or '?'} - "
        f"{importacao.regiao or '?'}/{importacao.reino or '?'}"
    ]
    if classe:
        linhas.append(f'{classe}="{nome}"')
    if importacao.nivel is not None:
        linhas.append(f"level={importacao.nivel}")
    if importacao.regiao:
        linhas.append(f"region={importacao.regiao.lower()}")
    if importacao.reino:
        linhas.append(f"server={importacao.reino.lower()}")
    if spec:
        linhas.append(f"spec={spec}")

    equipado: dict[str, ItemEquipado] = {}
    if conjunto is not None:
        for slot in _ORDEM_SLOTS:
            item = conjunto.itens.get(slot)
            if item is None:
                continue
            if item.bonus_ids_negativos:
                avisos.append(
                    AlertaParse(
                        codigo="amr_bonus_negativo",
                        detalhe=(
                            f"{slot}: bônus negativos {item.bonus_ids_negativos} "
                            "preservados no token bruto; não enviados ao simc."
                        ),
                        severidade="aviso",
                    )
                )
            linha = _linha_item(item)
            linhas.append(linha)
            equipado[slot] = ItemEquipado(
                slot=slot,
                item_id=item.item_id,
                enchant_id=item.enchant_id,
                gem_ids=list(item.gem_ids),
                bonus_ids=list(item.bonus_ids),
                crafted_stats=item.crafted_stats,
                crafting_quality=item.crafting_quality,
                drop_level=item.drop_level,
                content_tuning=item.content_tuning,
                linha_original=linha,
                origem_linha="equipado",
            )

        if "shirt" in conjunto.itens:
            avisos.append(
                AlertaParse(
                    codigo="amr_slot_ignorado",
                    detalhe="Slot shirt do AMR não é usado no cálculo.",
                    severidade="info",
                )
            )

    if incluir_inv:
        avisos.append(
            AlertaParse(
                codigo="amr_inv_inventario",
                detalhe=(
                    ".inv do AMR é o inventário possuído (bolsas + Grande Cofre); "
                    "é mesclado às bolsas pela combinação de exports e usado pelo "
                    "Droptimizer (Best/Worst in Bags)."
                ),
                severidade="info",
            )
        )

    marcas = [
        MarcaIlvl(
            indice=marca.indice,
            ilvl_atual=marca.atual,
            ilvl_maximo=marca.maximo,
            mapeado=marca.indice == 14,
        )
        for marca in importacao.watermarks
    ]

    personagem = Personagem(
        texto_original="\n".join(linhas) + "\n",
        versao_addon=f"AMR v{importacao.versao}" if importacao.versao else None,
        nome=importacao.nome,
        classe=classe,
        spec=spec,
        nivel=importacao.nivel,
        raca=raca_da_import(importacao),
        regiao=importacao.regiao.lower() if importacao.regiao else None,
        servidor=importacao.reino.lower() if importacao.reino else None,
        equipado=equipado,
        slot_high_watermarks=marcas,
        alertas=avisos,
    )
    return personagem
