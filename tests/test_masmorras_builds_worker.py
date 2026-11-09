"""T9/T11/T12 de ponta a ponta sem simc: worker com builds, API de builds e string do AMR."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wowsim.parser.amr_codec import itens_da_linha  # noqa: E402
from wowsim.topgear.runner import LeituraSim  # noqa: E402
from wowsim.web import (  # noqa: E402
    db,
    drop_db,
    exportar_api,
    masmorras_api,
    masmorras_db,
    masmorras_worker,
    perfil_store,
    topgear_db,
)
from wowsim.web.app import app  # noqa: E402

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"
BIB = RAIZ / "fixtures" / "pyrogalth-bib-amr.txt"


def _bases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for modulo, nome in (
        (db, "jobs.db"),
        (drop_db, "drop.db"),
        (perfil_store, "perfil.db"),
        (topgear_db, "topgear.db"),
        (masmorras_db, "masmorras.db"),
    ):
        monkeypatch.setattr(modulo, "DB_PATH", tmp_path / nome)
    masmorras_db.init_db()


class _SimFalso:
    """DPS = 100 × fator da build; +2% para UM item alvo; nada mais muda."""

    def __init__(self, alvo: dict, fator: float) -> None:
        self.alvo = alvo
        self.fator = fator

    def __call__(self, conjuntos, iterations):
        resultados = {}
        for nome, conjunto in conjuntos.items():
            ganho = 2.0 if any(c.item_id in self.alvo for c in conjunto.itens.values()) else 0.0
            resultados[nome] = (100.0 + ganho) * self.fator
        return LeituraSim(base_dps=1.0, resultados=resultados)


def _rodar(tmp_path, monkeypatch, **extra) -> dict:
    _bases(tmp_path, monkeypatch)
    alvos: set[int] = set()
    fatores = iter([1.0, 3.0, 5.0])

    def criar(personagem, *, fight_style, **kw):
        return _SimFalso(alvos, next(fatores))

    monkeypatch.setattr(masmorras_worker, "criar_simulador", criar)
    monkeypatch.setattr(
        masmorras_worker,
        "preflight",
        lambda *a, **k: SimpleNamespace(ok=True, duracao_s=0.1, erro=None),
    )
    monkeypatch.setattr(masmorras_worker, "threads_para_job", lambda: 1)
    # Um item de cabeça qualquer vira o "upgrade" medido.
    from wowsim.data.classes import atributo_da_classe, tipo_armadura_da_classe
    from wowsim.masmorras.catalogo import elegivel, itens_por_masmorra

    cabeca = next(
        i for i in itens_por_masmorra()
        if i.slot == "head"
        and elegivel(i, tipo_armadura=tipo_armadura_da_classe("warlock"), atributo=atributo_da_classe("warlock"))
    )
    alvos.add(cabeca.item_id)

    pedido = {
        "addon": FIXTURE.read_text(encoding="utf-8"),
        "scenario": "dungeon_slice",
        "ilvl": 341,
        "iteracoes_triagem": 50,
        "iteracoes_refino": 200,
        "orcamento_segundos": 600,
        **extra,
    }
    job_id = masmorras_db.criar_job(json.dumps(pedido))
    masmorras_worker.processar(job_id)
    job = masmorras_db.obter_job(job_id)
    assert job["status"] == "done", job.get("erro")
    return {"resultado": job["resultado"], "alvo": cabeca}


def test_worker_com_duas_builds_monta_e_confirma(tmp_path, monkeypatch) -> None:
    saida = _rodar(
        tmp_path, monkeypatch,
        loadouts=["raid maxroll", "Diabolist Delves"],
        pesos_loadouts={"raid maxroll": 1, "Diabolist Delves": 3},
    )
    r, alvo = saida["resultado"], saida["alvo"]
    assert [b["nome"] for b in r["builds"]] == ["raid maxroll", "Diabolist Delves"]
    assert [b["cenario"] for b in r["builds"]] == ["patchwerk", "dungeon_slice"]
    assert r["pesos_builds"] == pytest.approx({"raid maxroll": 0.25, "Diabolist Delves": 0.75})
    for b in r["builds"]:
        # delta contra o próprio ref (P4), igual nas duas builds apesar dos fatores 1×/3×
        assert b["delta_conjunto_pct"] == pytest.approx(2.0)
        assert [t["item_id"] for t in b["trocas"]] == [alvo.item_id]
        assert any(i["item_id"] == alvo.item_id and i["slot"] == "head" for i in b["conjunto_itens"])
    linha = next(l for l in r["matriz"] if l["item_id"] == alvo.item_id)
    assert linha["deltas"] == pytest.approx({"raid maxroll": 2.0, "Diabolist Delves": 2.0})
    assert linha["divergente"] is False
    assert r["masmorras"][0]["masmorra"] == alvo.masmorra
    assert any("média ponderada" in a for a in r["avisos"])


def test_worker_mede_escala_do_pawn_por_build(tmp_path, monkeypatch) -> None:
    from wowsim.data.pesos_medidos import EscalaMedida

    chamadas = []

    def medir(personagem, *, talentos, fight_style, iterations, **kw):
        chamadas.append((talentos, fight_style, iterations))
        f = {"Int": 20.0, "Crit": 9.0, "Haste": 10.0, "Mastery": 8.0, "Vers": 7.0}
        return EscalaMedida(talentos, fight_style, iterations, 200_000.0, 50.0, f, {k: 0.2 for k in f})

    monkeypatch.setattr(masmorras_worker, "medir_escala", medir)
    r = _rodar(
        tmp_path, monkeypatch,
        loadouts=["raid maxroll", "m+ icy"], medir_pesos=True,
    )["resultado"]
    assert [c[2] for c in chamadas] == [5000, 5000]
    assert {c[1] for c in chamadas} == {"Patchwerk", "DungeonSlice"}
    assert all(b["pawn"].startswith('( Pawn: v1: "Pyrogalth - ') for b in r["builds"])
    assert r["pawn_mistura"].startswith('( Pawn: v1: "Pyrogalth - Mistura"')
    assert r["pawn_iguais"] == [["raid maxroll", "m+ icy"]]  # escalas idênticas


def test_build_desconhecida_vira_erro(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)
    pedido = {"addon": FIXTURE.read_text(encoding="utf-8"), "loadouts": ["não existe"]}
    job_id = masmorras_db.criar_job(json.dumps(pedido))
    masmorras_worker.processar(job_id)
    job = masmorras_db.obter_job(job_id)
    assert job["status"] == "error" and "não existe" in job["erro"]


def test_api_lista_builds_com_cenario_sugerido(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)
    monkeypatch.setattr(masmorras_api, "enfileirar_masmorras", lambda job_id: None)
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/api/masmorras/builds", json={"addon": FIXTURE.read_text(encoding="utf-8")}
        )
    assert resposta.status_code == 200
    builds = {b["nome"]: b["cenario_sugerido"] for b in resposta.json()["builds"]}
    assert builds["Atual"] == "dungeon_slice"
    assert builds["raid maxroll"] == "patchwerk"
    assert builds["m+ icy"] == "dungeon_slice"


def test_estimativa_multiplica_por_build_e_aceita_cofre(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)
    addon = FIXTURE.read_text(encoding="utf-8")
    with TestClient(app) as cliente:
        uma = cliente.get("/api/masmorras/estimativa", params={"addon": addon}).json()
        duas = cliente.get("/api/masmorras/estimativa", params={"addon": addon, "builds": 2}).json()
        cofre = cliente.get(
            "/api/masmorras/estimativa",
            params={
                "addon": addon,
                "modo": "cofre",
                "amr": (RAIZ / "fixtures" / "ngmmexe-amr-cofre.txt").read_text(encoding="utf-8"),
            },
        )
    assert duas["profilesets_total_estimado"] == 2 * uma["profilesets_total_estimado"]
    assert duas["segundos_estimados"] > 2 * uma["segundos_estimados"] - 1
    assert cofre.status_code == 200
    assert set(cofre.json()["contagens"]) == {"Grande Cofre"}


def test_string_amr_com_o_conjunto_montado(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)
    modelo = BIB.read_text(encoding="utf-8")
    itens = [
        {"slot": "head", "item_id": 271546, "bonus_ids": [12345], "fonte": "teste", "redirected_base_stats": 250000},
        {"slot": "finger1", "item_id": 240000, "bonus_ids": [1, 2], "gem_ids": [240983], "enchant_id": 7935, "fonte": "teste"},
    ]
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/api/exportar/amr", json={"modelo": modelo, "build": "m+ icy", "itens": itens}
        )
        ruim = cliente.post(
            "/api/exportar/amr", json={"modelo": "x" * 30, "build": "a", "itens": itens}
        )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["setup_id"] == "WSIM-m+-icy"
    assert corpo["string"].count("$") == 2
    assert "@WSIM-m+-icy#_@WSIM m+ icy" in corpo["string"]
    decod = {i.item_id: i for i in itens_da_linha(corpo["string"])}
    assert decod[271546].catalyst_source == 250000
    assert decod[240000].enchant_id == 7935 and decod[240000].gem_ids[0] == 240983
    assert "Best in Bags" in corpo["aviso"]
    assert ruim.status_code == 400


def test_setup_id_saneado() -> None:
    assert exportar_api.setup_id_da_build("a$b;c@d#e") == "WSIM-a-b-c-d-e"
    assert not exportar_api.setup_id_da_build("AMR x").upper().startswith("AMR")


def test_tempo_esgotado_na_segunda_build_guarda_a_primeira(tmp_path, monkeypatch) -> None:
    from wowsim import simc_runner as sr

    original = masmorras_worker.rodar_build
    chamadas = {"n": 0}

    def rodar(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise sr.SimcOrcamentoEsgotado("O simc excedeu 405 s (orçamento). Comando: simc.exe ...")
        return original(*a, **k)

    monkeypatch.setattr(masmorras_worker, "rodar_build", rodar)
    r = _rodar(tmp_path, monkeypatch, loadouts=["raid maxroll", "Diabolist Delves"])["resultado"]
    assert [b["nome"] for b in r["builds"]] == ["raid maxroll"]
    assert r["pesos_builds"] == {"raid maxroll": 1.0}
    assert any("ficaram de fora Diabolist Delves" in a for a in r["avisos"])


def test_tempo_esgotado_sem_nada_pronto_vira_mensagem_legivel(tmp_path, monkeypatch) -> None:
    from wowsim import simc_runner as sr

    def rodar(*a, **k):
        raise sr.SimcOrcamentoEsgotado("O simc excedeu 405 s (orçamento). Comando: simc.exe x y z")

    _bases(tmp_path, monkeypatch)
    monkeypatch.setattr(masmorras_worker, "rodar_build", rodar)
    monkeypatch.setattr(masmorras_worker, "criar_simulador", lambda *a, **k: None)
    monkeypatch.setattr(
        masmorras_worker, "preflight", lambda *a, **k: SimpleNamespace(ok=True, duracao_s=0.1, erro=None)
    )
    monkeypatch.setattr(masmorras_worker, "threads_para_job", lambda: 1)
    pedido = {"addon": FIXTURE.read_text(encoding="utf-8"), "loadouts": ["raid maxroll"], "orcamento_segundos": 900}
    job_id = masmorras_db.criar_job(json.dumps(pedido))
    masmorras_worker.processar(job_id)
    job = masmorras_db.obter_job(job_id)
    assert job["status"] == "error"
    assert "tempo máximo (15 min)" in job["erro"] and "simc.exe" not in job["erro"]


def test_trilha_e_rank_viram_bonus_e_custo_de_upgrade(tmp_path, monkeypatch) -> None:
    saida = _rodar(tmp_path, monkeypatch, trilha="mito", rank=2, loadouts=["raid maxroll"])
    r, alvo = saida["resultado"], saida["alvo"]
    assert r["nivel"] == "Mito 2/6" and r["ilvl"] == 321
    item = next(i for m in r["masmorras"] for i in m["itens"] if i["item_id"] == alvo.item_id)
    assert item["degrau"] == "Mito 2/6"
    assert item["upgrade"] == {"moeda": "Brasão Mítico", "brasoes": 80, "etapas": 4, "ate": "Mito 6/6 (334)"}
    troca = r["builds"][0]["trocas"][0]
    assert troca["upgrade"]["brasoes"] == 80
    assert r["builds"][0]["brasoes"] == {"Brasão Mítico": 80}


def test_forja_fora_do_seis_de_seis_vira_erro(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)
    pedido = {"addon": FIXTURE.read_text(encoding="utf-8"), "trilha": "mito", "rank": 3, "forja": True}
    job_id = masmorras_db.criar_job(json.dumps(pedido))
    masmorras_worker.processar(job_id)
    job = masmorras_db.obter_job(job_id)
    assert job["status"] == "error" and "6/6" in job["erro"]


def test_modo_craft_no_worker(tmp_path, monkeypatch) -> None:
    _bases(tmp_path, monkeypatch)

    class Sim:
        def __call__(self, conjuntos, iterations):
            r = {}
            for nome, c in conjuntos.items():
                dps = 100.0
                for cand in c.itens.values():
                    if cand.crafted_stats == [36, 49] and cand.slot == "shoulder":
                        dps += 1.0
                    if cand.embelezamento_simc == "arcanoweave_lining":
                        dps += 0.4
                r[nome] = dps
            return LeituraSim(base_dps=100.0, resultados=r)

    monkeypatch.setattr(masmorras_worker, "criar_simulador", lambda *a, **k: Sim())
    monkeypatch.setattr(
        masmorras_worker, "preflight", lambda *a, **k: SimpleNamespace(ok=True, duracao_s=0.1, erro=None)
    )
    monkeypatch.setattr(masmorras_worker, "threads_para_job", lambda: 1)
    pedido = {"addon": FIXTURE.read_text(encoding="utf-8"), "modo": "craft", "orcamento_segundos": 600}
    job_id = masmorras_db.criar_job(json.dumps(pedido))
    masmorras_worker.processar(job_id)
    job = masmorras_db.obter_job(job_id)
    assert job["status"] == "done", job.get("erro")
    craft = job["resultado"]["craft"]
    assert craft["custo"]["brasoes"] == 80 and craft["custo"]["ilvl"] == 331
    assert craft["pecas"][0]["slot"] == "shoulder"
    assert craft["pecas"][0]["missiva"] == "Aceleração + Maestria"
    # O personagem do fixture já usa Forro de Arcanotrama aplicado em duas peças
    # (costas e pulsos), então está no teto: medir outro embelezamento exige
    # TROCAR o reagente, nunca somar um terceiro (P-050).
    trocas = [e for e in craft["embelezamentos"] if e["tipo"] == "troca"]
    assert trocas, craft["embelezamentos"]
    assert all(e["troca_de"] == "Forro de Arcanotrama" for e in trocas)
    assert any(e["descricao"] for e in craft["embelezamentos"])
    assert job["resultado"]["masmorras"] == []
