"""Combina um export do SimC e um export do AskMrRobot em um só perfil.

Cada formato carrega informação que o outro não tem:

- **SimC** (``/simc``): talentos (import string authority), omnium/runas,
  loadouts salvos, ``Gear from Bags`` e o build do cliente.
- **AMR** (``$181;...``): raça/facção, ``.inv`` (bolsas + Grande Cofre),
  ``.hlv`` (high watermarks por slot), ``content tuning``, ``crafting quality``
  e ``drop level`` de cada item.

O merge escolhe um **primário** (dono do equipado simulado e dos talentos) e usa
o outro como **complemento** para preencher o que falta, sem nunca inventar
números — o DPS continua 100% do SimulationCraft.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..models import AlertaParse, ItemEquipado, MarcaIlvl, Personagem
from .addon import parse_texto, serializar_texto
from .amr import ImportAMR, para_personagem, parse_amr

Primario = Literal["simc", "amr"]

# Campos escalares preenchidos do secundário quando o primário está vazio.
_CAMPOS_ESCALARES = (
    "nome",
    "classe",
    "spec",
    "nivel",
    "raca",
    "regiao",
    "servidor",
    "role",
    "loot_spec",
    "bonus_roll_items",
)

# Metadados que só o AMR traz e que enriquecem o item do SimC.
_META_AMR = (
    "content_tuning",
    "crafting_quality",
    "drop_level",
    "crafted_stats",
    "redirected_base_stats",
)

# Dados derivados exclusivamente do SimC (AMR não converte talentos).
_CAMPOS_SIMC = (
    "talents_atual",
    "loadouts",
    "omnium_ids_brutos",
    "omnium_ranks",
    "runas_declaradas",
    "profissoes",
    "build_cliente",
)


class CombinacaoImport(BaseModel):
    """Resultado do merge de dois exports."""

    model_config = ConfigDict(extra="forbid")

    personagem: Personagem
    simc: str
    primario: Primario
    fontes: list[str]
    avisos: list[AlertaParse]


def _eh_amr(texto: str | None) -> bool:
    return bool(texto and texto.strip().startswith("$"))


def _inv_para_equipados(importacao: ImportAMR) -> list[ItemEquipado]:
    """Converte os tokens do ``.inv`` em itens possuídos (slot via InventoryType)."""
    from ..droptimizer.pools import itens_do_inv  # import tardio evita ciclo

    equipados: list[ItemEquipado] = []
    for item in itens_do_inv(importacao):
        equipados.append(
            ItemEquipado(
                slot=item.slot,
                item_id=item.item_id,
                bonus_ids=list(item.bonus_ids),
                enchant_id=item.enchant_id,
                gem_ids=list(item.gem_ids),
                ilvl_comentario=item.ilvl,
                origem_linha="mochila",
                linha_original=f"# inv_amr {item.item_id}",
            )
        )
    return equipados


def _chave_item(item: ItemEquipado) -> tuple:
    return (
        item.item_id,
        tuple(sorted(item.bonus_ids)),
        item.enchant_id,
    )


def _mesclar_equipado(
    base: dict[str, ItemEquipado],
    outro: dict[str, ItemEquipado],
    avisos: list[AlertaParse],
) -> dict[str, ItemEquipado]:
    resultado = {slot: item.model_copy(deep=True) for slot, item in base.items()}
    conflitos: list[str] = []
    so_secundario: list[str] = []
    for slot, item_outro in outro.items():
        if slot not in resultado:
            resultado[slot] = item_outro.model_copy(deep=True)
            so_secundario.append(slot)
            continue
        item_base = resultado[slot]
        mesmo_item = (
            item_base.item_id is not None
            and item_outro.item_id is not None
            and item_base.item_id == item_outro.item_id
        )
        if item_base.item_id is not None and item_outro.item_id is not None and not mesmo_item:
            conflitos.append(slot)
            continue
        if mesmo_item or item_base.item_id is None:
            for campo in _META_AMR:
                if getattr(item_base, campo) is None and getattr(item_outro, campo) is not None:
                    setattr(item_base, campo, getattr(item_outro, campo))
            if item_base.ilvl_comentario is None and item_outro.ilvl_comentario is not None:
                item_base.ilvl_comentario = item_outro.ilvl_comentario
            for campo in ("nome_pt", "nome_en"):
                if getattr(item_base, campo) is None and getattr(item_outro, campo) is not None:
                    setattr(item_base, campo, getattr(item_outro, campo))
    if so_secundario:
        avisos.append(
            AlertaParse(
                codigo="combinar_slot_do_secundario",
                detalhe=(
                    f"{len(so_secundario)} slot(s) vieram só do secundário: "
                    f"{', '.join(sorted(so_secundario))}."
                ),
                severidade="info",
            )
        )
    if conflitos:
        avisos.append(
            AlertaParse(
                codigo="combinar_equipado_conflito",
                detalhe=(
                    f"{len(conflitos)} slot(s) divergem entre os exports "
                    f"({', '.join(sorted(conflitos))}); mantido o item do primário."
                ),
                severidade="aviso",
            )
        )
    return resultado


def _mesclar_mochila(
    base: dict[str, list[ItemEquipado]],
    outro: dict[str, list[ItemEquipado]],
    inv: list[ItemEquipado],
) -> dict[str, list[ItemEquipado]]:
    resultado = {slot: [i.model_copy(deep=True) for i in itens] for slot, itens in base.items()}
    vistos = {
        (slot, _chave_item(item))
        for slot, itens in resultado.items()
        for item in itens
    }

    def adicionar(slot: str, item: ItemEquipado) -> None:
        chave = (slot, _chave_item(item))
        if chave in vistos:
            return
        vistos.add(chave)
        resultado.setdefault(slot, []).append(item)

    for slot, itens in outro.items():
        for item in itens:
            adicionar(slot, item.model_copy(deep=True))
    for item in inv:
        adicionar(item.slot, item)
    return resultado


def _mesclar_marcas(
    base: list[MarcaIlvl], outro: list[MarcaIlvl]
) -> list[MarcaIlvl]:
    por_indice: dict[int, MarcaIlvl] = {}
    for marca in (*outro, *base):  # base sobrescreve
        anterior = por_indice.get(marca.indice)
        if anterior is None:
            por_indice[marca.indice] = marca
            continue
        # Prefere a marca mapeada; senão, a do primário (já aplicada).
        if marca.mapeado and not anterior.mapeado:
            por_indice[marca.indice] = marca
    return [por_indice[i] for i in sorted(por_indice)]


def mesclar_personagens(
    primario: Personagem,
    secundario: Personagem | None,
    *,
    inv: list[ItemEquipado] | None = None,
    fonte_simc: Personagem | None = None,
) -> tuple[Personagem, list[AlertaParse]]:
    """Mescla ``primario`` com ``secundario`` (complemento) em um novo Personagem."""
    avisos: list[AlertaParse] = []
    resultado = primario.model_copy(deep=True)

    if secundario is not None:
        for campo in _CAMPOS_ESCALARES:
            if not getattr(resultado, campo) and getattr(secundario, campo):
                setattr(resultado, campo, getattr(secundario, campo))
        resultado.equipado = _mesclar_equipado(
            primario.equipado, secundario.equipado, avisos
        )
        resultado.mochila = _mesclar_mochila(
            primario.mochila, secundario.mochila, []
        )
        for campo in (
            "catalyst_currencies",
            "upgrade_currencies",
            "bonus_roll_currencies",
        ):
            atual = dict(getattr(resultado, campo))
            for chave, valor in getattr(secundario, campo).items():
                atual.setdefault(chave, valor)
            setattr(resultado, campo, atual)
        resultado.slot_high_watermarks = _mesclar_marcas(
            primario.slot_high_watermarks, secundario.slot_high_watermarks
        )
        for campo in ("versao_addon", "checksum"):
            if not getattr(resultado, campo) and getattr(secundario, campo):
                setattr(resultado, campo, getattr(secundario, campo))
        resultado.upgrade_achievements = list(
            dict.fromkeys(
                [*primario.upgrade_achievements, *secundario.upgrade_achievements]
            )
        )
        resultado.alertas = [*primario.alertas, *secundario.alertas]

    # Itens do .inv AMR entram como possuídos (bolsas + Grande Cofre).
    if inv:
        resultado.mochila = _mesclar_mochila(resultado.mochila, {}, inv)
        avisos.append(
            AlertaParse(
                codigo="combinar_inv_mesclado",
                detalhe=f"{len(inv)} item(ns) do .inv AMR adicionados às bolsas.",
                severidade="info",
            )
        )

    # Talentos/omnium/loadouts só existem no SimC.
    if fonte_simc is not None and resultado is not fonte_simc:
        for campo in _CAMPOS_SIMC:
            if not getattr(resultado, campo) and getattr(fonte_simc, campo):
                setattr(resultado, campo, getattr(fonte_simc, campo))
        if not resultado.texto_original and fonte_simc.texto_original:
            resultado.texto_original = fonte_simc.texto_original
        _garantir_spec_e_talentos(resultado)

    return resultado, avisos


def _garantir_spec_e_talentos(p: Personagem) -> None:
    """Com o AMR como primário, o texto do simc vem do AMR (sem spec/talentos).

    Sem ``talents=`` o simc roda a spec sem talentos e o DPS sai dezenas de vezes
    menor (pré-voo "não devolveu o DPS"). As linhas vão no FIM do texto para não
    deslocar ``indice_linha`` dos itens; o simc aplica as opções do ator na
    inicialização, então a ordem não importa.
    """
    texto = p.texto_original or ""
    linhas = [l.strip() for l in texto.splitlines()]
    extra: list[str] = []
    if p.spec and not any(l.startswith("spec=") for l in linhas):
        extra.append(f"spec={p.spec}")
    if p.talents_atual and not any(l.startswith("talents=") for l in linhas):
        extra.append(f"talents={p.talents_atual}")
    if extra:
        fim = "" if texto.endswith(("\n", "\r\n")) or not texto else "\n"
        p.texto_original = texto + fim + "\n".join(extra) + "\n"


def combinar_textos(
    texto_principal: str | None,
    texto_amr: str | None = None,
    *,
    primario: Primario = "simc",
    classe_hint: str | None = None,
    spec_hint: str | None = None,
    incluir_inv: bool = True,
) -> CombinacaoImport:
    """Une um export SimC e/ou AMR em um ``Personagem`` enriquecido.

    ``texto_principal`` pode ser SimC ou AMR (detectado pelo prefixo ``$``).
    ``texto_amr`` é sempre tratado como AMR. Informe pelo menos um dos dois.
    """
    principal = (texto_principal or "").strip()
    amr_texto = (texto_amr or "").strip()

    if not principal and not amr_texto:
        raise ValueError("Informe pelo menos um export (SimC ou AMR).")

    personagem_simc: Personagem | None = None
    personagem_amr: Personagem | None = None
    amr_import: ImportAMR | None = None
    fontes: list[str] = []

    if _eh_amr(principal):
        amr_import = parse_amr(principal)
        personagem_amr = para_personagem(
            amr_import, classe_hint=classe_hint, spec_hint=spec_hint
        )
        fontes.append("amr:principal")
    elif principal:
        personagem_simc = parse_texto(
            principal, classe_hint=classe_hint, spec_hint=spec_hint
        )
        fontes.append("simc")

    if amr_texto:
        if personagem_amr is not None:
            # O principal já é AMR: só aceitar um segundo AMR idêntico; caso
            # contrário, dois exports distintos são ambíguos (P1-01).
            if amr_texto != principal:
                raise ValueError(
                    "Dois exports AMR diferentes foram enviados; informe apenas "
                    "um deles (no texto principal ou em 'amr')."
                )
        else:
            amr_import = parse_amr(amr_texto)
            personagem_amr = para_personagem(
                amr_import, classe_hint=classe_hint, spec_hint=spec_hint
            )
            if "amr" not in fontes:
                fontes.append("amr")

    inv = (
        _inv_para_equipados(amr_import)
        if (incluir_inv and amr_import is not None)
        else []
    )

    if primario == "amr":
        base = personagem_amr or personagem_simc
        outro = personagem_simc if personagem_amr is not None else None
    else:
        base = personagem_simc or personagem_amr
        outro = personagem_amr if personagem_simc is not None else None

    if base is None:  # pragma: no cover - já garantido acima
        raise ValueError("Não foi possível montar o personagem base.")

    personagem, avisos = mesclar_personagens(
        base,
        outro,
        inv=inv,
        fonte_simc=personagem_simc,
    )

    if primario == "amr" and personagem_amr is None:
        avisos.append(
            AlertaParse(
                codigo="combinar_primario_ausente",
                detalhe=(
                    "primário 'amr' solicitado, mas nenhum export AMR foi "
                    "enviado; usando o SimC como base."
                ),
                severidade="aviso",
            )
        )

    if incluir_inv and amr_import is not None:
        from ..droptimizer.pools import inv_ignorados  # import tardio evita ciclo

        ignorados = inv_ignorados(amr_import)
        if ignorados:
            lista = ", ".join(str(i) for i in ignorados[:10])
            if len(ignorados) > 10:
                lista += "…"
            avisos.append(
                AlertaParse(
                    codigo="amr_inv_ignorado",
                    detalhe=(
                        f"{len(ignorados)} item(ns) do .inv AMR sem slot de "
                        f"equipamento foram ignorados: {lista}."
                    ),
                    severidade="info",
                )
            )

    # Sinaliza a origem e eventuais limitações herdadas.
    avisos.append(
        AlertaParse(
            codigo="combinar_fontes",
            detalhe=f"Fontes combinadas: {', '.join(fontes)}; primário={primario}.",
            severidade="info",
        )
    )
    avisos.append(
        AlertaParse(
            codigo="combinar_simc_limitacoes",
            detalhe=(
                "O .simc combinado é regenerado do modelo mesclado; content "
                "tuning, crafting quality e .inv AMR não são representáveis em "
                "texto SimC."
            ),
            severidade="info",
        )
    )

    return CombinacaoImport(
        personagem=personagem,
        simc=serializar_texto(personagem),
        primario=primario,
        fontes=fontes,
        avisos=avisos,
    )
