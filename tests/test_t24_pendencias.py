"""T24: regras da temporada, forja por slot, marca do slot, spec do AMR, V-2/V-6, armas no craft."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from wowsim.data import regras, trilhas
from wowsim.masmorras import craft
from wowsim.models import MarcaIlvl
from wowsim.parser.amr import parse_amr, spec_do_import
from wowsim.parser.amr_codec import cabecalho_do_modelo
from wowsim.parser.combinar import combinar_textos
from wowsim.simc_runner import problemas_do_log

pytestmark = pytest.mark.unit
RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "fixtures"


def test_raspador_extrai_regras_das_paginas_salvas(tmp_path) -> None:
    sys.path.insert(0, str(RAIZ / "scripts"))
    import raspar_regras_temporada as r

    destino = tmp_path / "regras.json"
    assert r.main(["--md", str(FIX / "regras_temporada"), "--destino", str(destino)]) == 0
    import json

    d = json.loads(destino.read_text(encoding="utf-8"))
    assert d["forja"]["custo"] == 10
    assert d["forja"]["mito"] == {"antes": 334, "depois": 341}
    assert set(d["forja"]["slots"]) == {"main_hand", "off_hand", "trinket1", "trinket2", "neck"}
    assert d["craft"]["ilvl_max"] == {"heroi": 318, "mito": 331}
    assert d["upgrade"] == {"brasoes_por_etapa": 20, "marca_do_slot": True, "desconto_bando_pct": 50}


def test_raspador_nao_grava_com_campo_faltando(tmp_path) -> None:
    sys.path.insert(0, str(RAIZ / "scripts"))
    import raspar_regras_temporada as r

    vazio = tmp_path / "md"
    vazio.mkdir()
    (vazio / "icy_spark.md").write_text("nada aqui", encoding="utf-8")
    destino = tmp_path / "x.json"
    assert r.main(["--md", str(vazio), "--destino", str(destino)]) == 1
    assert not destino.exists()


def test_forja_so_em_arma_berloque_e_colar() -> None:
    forjado = trilhas.degrau("mito", 6, True)
    assert trilhas.degrau_no_slot(forjado, "trinket1").ilvl == 341
    assert trilhas.degrau_no_slot(forjado, "neck").forja
    assert trilhas.degrau_no_slot(forjado, "head") == trilhas.degrau("mito", 6)
    assert not regras.slot_aceita_forja("finger1")


def test_custo_com_marca_do_slot_e_forjado() -> None:
    d = trilhas.degrau("mito", 2)  # 321 -> 6/6 334: etapas 324, 328, 331, 334
    cheio = trilhas.custo_upgrade(d, slot="head")
    assert cheio["brasoes"] == 80 and cheio["etapas_gratis"] == 0
    com_marca = trilhas.custo_upgrade(d, slot="head", marcas={"head": 328})
    assert com_marca["etapas_gratis"] == 2 and com_marca["brasoes"] == 40
    forjado = trilhas.custo_upgrade(trilhas.degrau("mito", 6, True), slot="trinket1")
    assert forjado["brasoes"] == 0 and "máximo" in forjado["ate"] and forjado["forja"]["quantidade"] == 10


def test_marcas_por_slot_do_export() -> None:
    marcas = [MarcaIlvl(indice=0, ilvl_atual=305, ilvl_maximo=321), MarcaIlvl(indice=13, ilvl_atual=321, ilvl_maximo=341)]
    assert regras.marcas_por_slot(marcas) == {"head": 305, "main_hand": 321}


def test_spec_vem_do_amr_e_talentos_entram_no_texto() -> None:
    assert spec_do_import(parse_amr((FIX / "pyrogalth-amr-181.txt").read_text(encoding="utf-8"))) == "demonology"
    assert spec_do_import(parse_amr((FIX / "ngmmexe-amr-cofre.txt").read_text(encoding="utf-8"))) == "balance"
    r = combinar_textos(
        (FIX / "pyrogalth.simc").read_text(encoding="utf-8"),
        (FIX / "pyrogalth-amr-181.txt").read_text(encoding="utf-8"),
        primario="amr",
    )
    linhas = r.simc.splitlines()
    assert "spec=demonology" in linhas
    assert any(l.startswith("talents=") for l in linhas)


def test_v2_log_do_simc() -> None:
    erros, avisos = problemas_do_log(
        "Trivial: Player X item 'y' unknown embellishment 'z', ignoring\n"
        "Severe: Player 'Ngmmexe' does not support fight style DungeonSlice, results are inaccurate\n"
        "Severe: Player 'Ngmmexe' does not support fight style DungeonSlice, results are inaccurate\n"
    )
    assert len(erros) == 1 and len(avisos) == 1


def test_v6_export_do_personagem_tem_mensagem_clara() -> None:
    with pytest.raises(ValueError, match="Best in Bags"):
        cabecalho_do_modelo((FIX / "ngmmexe-amr-cofre.txt").read_text(encoding="utf-8"))
    assert cabecalho_do_modelo((FIX / "pyrogalth-bib-amr.txt").read_text(encoding="utf-8").splitlines()[0])


def test_craft_armas_por_classe_e_nivel() -> None:
    assert craft.tipo_da_arma("cajado 2M") == ("cajado", "main_hand", "2h")
    assert craft.tipo_da_arma("mão secundária (escudo)")[0] == "escudo"
    assert craft.tipo_da_arma("mira de arma de longo alcance") is None
    druida = {(i.slot, i.maos) for i in craft.itens_craftaveis("couro", "druid") if i.maos}
    assert ("main_hand", "2h") in druida  # cajado
    assert all(s != "off_hand" or m == "1h" for s, m in druida)
    assert not any(i.maos for i in craft.itens_craftaveis("couro"))  # sem classe: sem armas
    assert craft.nivel_craft("heroi") == 318 and craft.nivel_craft("mito") == 331


def test_token_do_embelezamento_igual_ao_simc() -> None:
    sys.path.insert(0, str(RAIZ / "scripts"))
    from derivar_embelezamentos import tokenizar

    assert tokenizar("M3DDY, Travel-Sized") == "m3ddy_travelsized"
    assert tokenizar("Coiled Snake-Eye") == "coiled_snakeeye"
    assert tokenizar("Hunter's Ritual Stone") == "hunters_ritual_stone"
    assert tokenizar("Darkmoon Sigil: Blood") == "darkmoon_sigil_blood"


def test_craft_herda_encanto_e_gema_so_nos_engastes() -> None:
    from wowsim.data import catalog
    from wowsim.topgear.models import Candidato

    assert catalog.engastes(251513) == 1  # Loa Worshiper's Band: 1 engaste prismático
    anel = next(i for i in craft.itens_craftaveis("tecido") if i.item_id == 251513)
    atual = Candidato(slot="finger2", item_id=1, enchant_id=7967, gem_ids=[], fonte="equipado")
    c = craft.candidato(anel, "finger2", ("crit", "haste"), ilvl=318, atual=atual, gema_padrao=240908)
    assert c.enchant_id == 7967 and c.gem_ids == [240908]
    peito = next(i for i in craft.itens_craftaveis("tecido") if i.slot == "chest")
    c2 = craft.candidato(peito, "chest", ("crit", "haste"), atual=Candidato(slot="chest", item_id=2, gem_ids=[1], fonte="equipado"))
    assert c2.gem_ids[: (catalog.engastes(peito.item_id) or 0)] == c2.gem_ids


def test_plano_de_duas_mede_duplas_juntas() -> None:
    from types import SimpleNamespace

    from wowsim.topgear.models import Candidato, Conjunto, ContextoSpec
    from wowsim.topgear.runner import LeituraSim

    base = Conjunto(itens={s: Candidato(slot=s, item_id=n, fonte="equipado") for n, s in enumerate(("head", "legs", "feet"), 1)})
    itens = {s: craft.ItemCraft(100 + n, f"P{s}", None, s, False) for n, s in enumerate(("head", "legs", "feet"))}
    conjuntos, meta, melhor = {}, {}, {}
    for n, (s, it) in enumerate(itens.items()):
        nome = f"c_{s}"
        conjuntos[nome] = base.com_troca(s, Candidato(slot=s, item_id=it.item_id, fonte="craft"))
        meta[nome] = (it, ("crit", "haste"), s)
        melhor[s] = (SimpleNamespace(delta_cru=3 - n, limiar_cru=5), it, ("crit", "haste"), nome)

    def simular(conjs, it):
        ganho = {"par_head_legs": 3.0, "par_head_feet": 2.0, "par_legs_feet": 1.0}
        return LeituraSim(base_dps=100.0, resultados={k: 100 + ganho[k] for k in conjs})

    plano = craft.plano_de_duas(
        base, melhor, conjuntos, meta, ctx=ContextoSpec(), simular=simular, iteracoes=2000, ilvl=318
    )
    assert plano["melhor"]["slots"] == ["head", "legs"]  # entra mesmo dentro da margem (delta > 0)
    assert [a["diferenca_pct"] for a in plano["alternativas"]] == [-1.0, -2.0]
