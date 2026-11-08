"""Testes das correções do ranking: erro da média, agrupamento e CSV.

O defeito que motivou estes testes: o limiar de aceitação usava a dispersão
entre lutas (``stddev``, 3% a 7%) em vez do erro da média (~0,5%), e o ranking
marcava "empate" em todos os candidatos — inclusive num ganho real de +4%.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wowsim import simc_runner as sr
from wowsim.droptimizer.export import gerar_csv, nome_do_arquivo, salvar_csv
from wowsim.droptimizer.models import DropRankingItem, DropResult
from wowsim.droptimizer.search import _agrupar_equivalentes

pytestmark = pytest.mark.unit


def item(slot: str, item_id: int | None, ilvl: int | None, delta: float, **kwargs) -> DropRankingItem:
    dados = {
        "slot": slot,
        "item_id": item_id,
        "ilvl": ilvl,
        "dps": 100_000.0 * (1 + delta / 100),
        "delta_pct": delta,
        "limiar_pct": 0.15,
        "veredito": "ganho" if delta > 0.15 else "empate",
        "slots_testados": [slot],
    }
    dados.update(kwargs)
    return DropRankingItem(**dados)


# --------------------------------------------------------------------------
# erro da média vs dispersão entre lutas
# --------------------------------------------------------------------------


def test_profileset_usa_mean_error_e_nao_stddev() -> None:
    """Num profileset do simc, ``stddev`` é ~7x maior e não mede incerteza."""
    bloco = {
        "mean": 145_179.37,
        "stddev": 9_869.99,       # dispersão entre lutas: 6,8%
        "mean_stddev": 699.66,    # erro padrão da média: 0,48%
        "mean_error": 1_371.31,   # intervalo de confiança: 0,94%
    }
    resultado = sr._resultado_de_bloco("x", bloco, eh_base=False)

    assert resultado is not None
    assert resultado.erro_abs == pytest.approx(1_371.31)
    assert resultado.erro_pct == pytest.approx(0.944, abs=0.01)


def test_base_usa_mean_std_dev_e_nao_std_dev() -> None:
    """Em ``collected_data.dps`` o nome é outro: ``mean_std_dev``."""
    bloco = {
        "mean": 139_972.0,
        "median": 139_900.0,
        "std_dev": 9_268.0,      # 6,6%
        "mean_std_dev": 656.0,   # 0,47%
    }
    resultado = sr._resultado_de_bloco("base", bloco, eh_base=True)

    assert resultado is not None
    assert resultado.erro_abs == pytest.approx(656.0)
    assert resultado.erro_pct == pytest.approx(0.469, abs=0.01)


def test_dispersao_sozinha_nao_vira_erro() -> None:
    """Sem chave de erro da média, o erro é desconhecido — nunca a dispersão.

    Assim o limiar cai no piso fixo em vez de inflar e engolir todo ganho real.
    """
    resultado = sr._resultado_de_bloco("x", {"mean": 100.0, "stddev": 7.0}, eh_base=False)

    assert resultado is not None
    assert resultado.erro_abs is None
    assert resultado.erro_pct is None


def test_ganho_real_deixa_de_ser_empate() -> None:
    """Reproduz o caso da tela: +3,6% com dispersão de 6,8%."""
    from wowsim.droptimizer.search import _veredito
    from wowsim.topgear.search import _limiar_por_erro

    base_erro_pct, cand_erro_pct = 0.469, 0.944  # erro da média
    limiar = _limiar_por_erro(0.15, base_erro_pct, cand_erro_pct)

    assert limiar == pytest.approx(0.944, abs=0.01)
    assert _veredito(3.60, limiar) == "ganho"
    # Com a dispersão (6,8%) o mesmo ganho virava empate.
    assert _veredito(3.60, _limiar_por_erro(0.15, 6.62, 6.84)) == "empate"


# --------------------------------------------------------------------------
# agrupamento de slots equivalentes
# --------------------------------------------------------------------------


def test_agrupa_mesmo_item_medido_em_dois_slots() -> None:
    linhas = _agrupar_equivalentes(
        [item("trinket1", 9, 341, 3.9), item("trinket2", 9, 341, 4.2)]
    )

    assert len(linhas) == 1
    assert linhas[0].delta_pct == 4.2
    assert linhas[0].slot == "trinket2"
    assert linhas[0].slots_testados == ["trinket1", "trinket2"]


def test_nao_agrupa_ilvls_diferentes() -> None:
    linhas = _agrupar_equivalentes(
        [item("trinket1", 9, 341, 3.9), item("trinket1", 9, 334, 3.1)]
    )

    assert len(linhas) == 2
    assert {linha.ilvl for linha in linhas} == {334, 341}


def test_agrupamento_preserva_a_ordem_de_entrada() -> None:
    linhas = _agrupar_equivalentes(
        [
            item("head", 5, 341, 1.0),
            item("trinket1", 9, 341, 3.9),
            item("trinket2", 9, 341, 4.2),
            item("legs", 6, 341, 0.5),
        ]
    )

    assert [linha.item_id for linha in linhas] == [5, 9, 6]


def test_worst_in_bags_mantem_a_maior_perda() -> None:
    linhas = _agrupar_equivalentes(
        [item("finger1", 7, 341, -1.0), item("finger2", 7, 341, -3.0)], pior=True
    )

    assert len(linhas) == 1
    assert linhas[0].delta_pct == -3.0


def test_item_sem_id_nunca_e_agrupado() -> None:
    linhas = _agrupar_equivalentes(
        [item("head", None, None, 1.0), item("head", None, None, 2.0)]
    )

    assert len(linhas) == 2


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------


def _resultado() -> DropResult:
    return DropResult(
        modo="upgrade",
        base_dps=138_881.0,
        iterations=200,
        itens=[
            item(
                "trinket2",
                273649,
                341,
                4.19,
                nome_pt="Emblema Tempestuoso de Dazar",
                nome_en="Stormbound Emblem of Dazar",
                slots_testados=["trinket1", "trinket2"],
            ),
            item("head", 271546, 334, -0.5, nome_pt="Crânio do Necrólito"),
        ],
    )


def test_csv_tem_cabecalho_e_uma_linha_por_item() -> None:
    linhas = gerar_csv(_resultado()).strip().splitlines()

    assert linhas[0].startswith("slot;slots_testados;item_id;nome_pt;nome_en;ilvl")
    assert len(linhas) == 3


def test_csv_usa_virgula_decimal_e_registra_os_slots() -> None:
    texto = gerar_csv(_resultado())

    assert "4,190" in texto  # delta com vírgula, para o Excel PT-BR
    assert "trinket1 trinket2" in texto


def test_csv_escapa_separador_no_nome() -> None:
    import csv as csv_mod
    import io as io_mod

    resultado = _resultado()
    resultado.itens[0].nome_pt = "Item; com ponto e vírgula"
    texto = gerar_csv(resultado)

    # O campo é citado, então o leitor continua enxergando o mesmo nº de colunas.
    linhas = list(csv_mod.reader(io_mod.StringIO(texto), delimiter=";"))
    assert len(linhas[1]) == len(linhas[0])
    assert linhas[1][3] == "Item; com ponto e vírgula"


def test_salvar_grava_arquivo_legivel_pelo_excel(tmp_path: Path) -> None:
    caminho = salvar_csv(_resultado(), "abcdef1234", destino=tmp_path)

    assert caminho.is_file()
    assert caminho.parent == tmp_path.resolve()
    bruto = caminho.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")  # BOM: Excel abre com acento certo
    assert "Emblema Tempestuoso de Dazar" in bruto.decode("utf-8-sig")


def test_nome_do_arquivo_e_seguro_no_windows() -> None:
    nome = nome_do_arquivo("abc/def:123", "upgrade")

    assert not set(nome) & set('\\/:*?"<>|')
    assert nome.endswith(".csv")


def test_endpoint_csv_salva_e_devolve_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from wowsim.web import db, drop_api, drop_db, perfil_store, topgear_db
    from wowsim.web.app import app

    # Cada módulo faz ``from .db import DB_PATH``, então o nome é um objeto por
    # módulo: trocar só em ``db`` deixa os outros apontando para o banco real e o
    # worker falha ao abrir o WAL.
    for modulo in (db, perfil_store, topgear_db):
        monkeypatch.setattr(modulo, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(drop_db, "DB_PATH", tmp_path / "drop.db")
    monkeypatch.setattr(drop_api, "enfileirar_drop", lambda job_id: None)
    monkeypatch.setattr(
        drop_api, "salvar_csv", lambda resultado, job_id: tmp_path / "saida.csv"
    )

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "pyrogalth.simc"
    pedido = {"addon": fixture.read_text(encoding="utf-8"), "modo": "upgrade"}

    with TestClient(app) as cliente:
        job_id = cliente.post("/api/droptimizer", json=pedido).json()["id"]

        # Antes de concluir, não há CSV.
        assert cliente.post(f"/api/droptimizer/{job_id}/csv").status_code == 409

        drop_db.atualizar_job(
            job_id,
            status="done",
            resultado_json=_resultado().model_dump_json(),
        )
        resposta = cliente.post(f"/api/droptimizer/{job_id}/csv")

        assert resposta.status_code == 200
        assert resposta.json()["linhas"] == 2
        assert resposta.json()["arquivo"] == "saida.csv"

        texto = cliente.get(f"/api/droptimizer/{job_id}/csv")
        assert texto.status_code == 200
        assert "Emblema Tempestuoso de Dazar" in texto.text
