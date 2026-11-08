"""Worker tests: class→armor mapping (P0-02) and zombie-job guard (P0-07)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wowsim.topgear.models import TopGearRequest
from wowsim.web import topgear_db, topgear_worker

pytestmark = pytest.mark.unit

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "fixtures" / "pyrogalth.simc"


@pytest.mark.parametrize(
    ("classe", "esperado"),
    [
        ("warlock", "tecido"),
        ("priest", "tecido"),
        ("mage", "tecido"),
        ("druid", "couro"),
        ("rogue", "couro"),
        ("monk", "couro"),
        ("demonhunter", "couro"),
        ("hunter", "malha"),
        ("shaman", "malha"),
        ("evoker", "malha"),
        ("warrior", "placa"),
        ("paladin", "placa"),
        ("deathknight", "placa"),
    ],
)
def test_tipo_armadura_por_classe(classe: str, esperado: str) -> None:
    assert topgear_worker.tipo_armadura_da_classe(classe) == esperado


def test_excecao_generica_marca_erro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(topgear_db, "DB_PATH", tmp_path / "topgear.db")
    topgear_db.init_db()

    addon = FIXTURE.read_text(encoding="utf-8")
    pedido = TopGearRequest(
        addon=addon,
        iterations_triagem=10,
        iterations_refino=10,
        pool_por_slot=2,
        orcamento_segundos=60,
    )
    job_id = topgear_db.criar_job(pedido.model_dump_json())

    def boom(*_args, **_kwargs):
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr(topgear_worker, "executar_topgear", boom)

    topgear_worker.processar(job_id)

    job = topgear_db.obter_job(job_id)
    assert job is not None
    assert job["status"] == "error"
    assert "falha inesperada" in (job["erro"] or "")
