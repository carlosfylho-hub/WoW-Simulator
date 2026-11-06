"""Command line interface.

Phase 1 exposes only the engine checks. The install/parse/generate commands
arrive in the next phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import simc_runner as sr
from .parser.addon import SLOTS, ErroParseAddon, parse_texto

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PADRAO = PROJECT_ROOT / "fixtures" / "pyrogalth.simc"

REFERENCIAS = {
    "DungeonSlice": (254_000.0, "M+ em DungeonSlice"),
    "Patchwerk": (204_000.0, "alvo único em Patchwerk"),
}

app = typer.Typer(
    help="WoW Calculator Sim — simulador local de equipamento baseado no SimulationCraft.",
    no_args_is_help=True,
)
console = Console()


def _erro_simc(exc: Exception, codigo: int) -> None:
    console.print(Panel(str(exc), title="Falha no SimulationCraft", style="red"))
    raise typer.Exit(code=codigo)


@app.command("simc-info")
def simc_info(
    simc: Optional[Path] = typer.Option(
        None, "--simc", help="Caminho explícito para o binário do simc."
    ),
) -> None:
    """Mostra o binário encontrado e compara a build com o patch do addon."""
    try:
        caminho = sr.find_simc(simc)
    except sr.SimcNaoEncontrado as exc:
        _erro_simc(exc, 2)
        return

    info = sr.ler_versao(caminho)
    tabela = Table(title="SimulationCraft", show_header=True, header_style="bold")
    tabela.add_column("Campo")
    tabela.add_column("Valor")
    tabela.add_row("Binário", str(info.caminho))
    tabela.add_row("Versão", info.versao or "não informada")
    tabela.add_row("Build", info.build or "não informada")
    tabela.add_row("Build esperada", sr.BUILD_ESPERADO)
    tabela.add_row(
        "Situação",
        "compatível"
        if info.build_compativel
        else ("não verificada" if info.build_compativel is None else "divergente"),
    )
    console.print(tabela)

    if info.aviso_build:
        console.print(Panel(info.aviso_build, title="Aviso", style="yellow"))


@app.command("simc-check")
def simc_check(
    fixture: Path = typer.Option(
        FIXTURE_PADRAO, "--fixture", "-f", help="Export do addon em formato .simc."
    ),
    simc: Optional[Path] = typer.Option(
        None, "--simc", help="Caminho explícito para o binário do simc."
    ),
    iterations: int = typer.Option(
        500, "--iterations", "-n", min=10, help="Iterações por cenário."
    ),
    tolerancia: float = typer.Option(
        0.03, "--tolerancia", min=0.0, help="Tolerância relativa contra a referência."
    ),
    sem_cache: bool = typer.Option(
        False, "--sem-cache", help="Ignora o cache e executa de novo."
    ),
    forcar: bool = typer.Option(
        False, "--forcar", help="Recalcula mesmo que exista cache válido."
    ),
) -> None:
    """Roda o fixture nos dois cenários e compara com os valores de referência."""
    perfil = Path(fixture)
    if not perfil.is_file():
        console.print(
            Panel(
                f"Fixture não encontrado: {perfil}\n"
                "Cole a saída de /simc em fixtures/pyrogalth.simc antes de rodar.",
                title="Fixture ausente",
                style="red",
            )
        )
        raise typer.Exit(code=2)

    threads = sr.threads_padrao()
    linhas: list[tuple[str, float, float, float, str]] = []
    avisos: list[str] = []

    for cenario, (referencia, descricao) in REFERENCIAS.items():
        extra = ["desired_targets=1"] if cenario == "Patchwerk" else []
        console.print(
            f"[bold]{descricao}[/bold] — {cenario}, {iterations} iterações, "
            f"{threads} thread(s)"
        )
        try:
            execucao = sr.run_simc(
                perfil,
                simc_path=simc,
                iterations=iterations,
                fight_style=cenario,
                threads=threads,
                extra_args=extra,
                usar_cache=not sem_cache,
                forcar=forcar,
            )
            resultado = sr.read_results(execucao.json_path)
        except sr.SimcNaoEncontrado as exc:
            _erro_simc(exc, 2)
            return
        except sr.SimcFalhou as exc:
            _erro_simc(exc, 3)
            return
        except sr.SimcSemJson as exc:
            _erro_simc(exc, 4)
            return

        if resultado.base is None:
            _erro_simc(
                sr.SimcSemJson(
                    f"O JSON de {cenario} não trouxe DPS da base. "
                    f"Avisos: {', '.join(resultado.avisos) or 'nenhum'}."
                ),
                4,
            )
            return

        if execucao.info.aviso_build:
            avisos.append(execucao.info.aviso_build)

        delta, dentro = sr.comparar_com_referencia(
            resultado.base.dps, referencia, tolerancia
        )
        linhas.append(
            (
                cenario,
                resultado.base.dps,
                referencia,
                delta,
                "dentro" if dentro else "fora",
            )
        )
        origem = "cache" if execucao.cache_hit else f"{execucao.duracao_s:.1f} s"
        console.print(
            f"  DPS base: [bold]{resultado.base.dps:,.0f}[/bold] "
            f"(referência {referencia:,.0f}, {delta:+.2f}%), {origem}"
        )

    tabela = Table(title="simc-check", show_header=True, header_style="bold")
    tabela.add_column("Cenário")
    tabela.add_column("DPS", justify="right")
    tabela.add_column("Referência", justify="right")
    tabela.add_column("Delta", justify="right")
    tabela.add_column("Tolerância")
    for cenario, dps, referencia, delta, situacao in linhas:
        tabela.add_row(
            cenario,
            f"{dps:,.0f}",
            f"{referencia:,.0f}",
            f"{delta:+.2f}%",
            situacao,
        )
    console.print(tabela)

    for aviso in dict.fromkeys(avisos):
        console.print(Panel(aviso, title="Aviso de versão", style="yellow"))

    if any(linha[4] == "fora" for linha in linhas):
        console.print(
            Panel(
                "Resultado fora da tolerância. Antes de concluir qualquer coisa, "
                "confira o binário, a build e o fixture. Nenhum número foi estimado.",
                title="Atenção",
                style="yellow",
            )
        )
        raise typer.Exit(code=1)


@app.command("parse")
def parse(
    addon: Path = typer.Argument(..., help="Arquivo com o export do SimC AddOn."),
    json_out: Optional[Path] = typer.Option(
        None, "--json", help="Grava o personagem parseado em JSON."
    ),
) -> None:
    """Resume o personagem sem simular nada."""
    if not addon.is_file():
        console.print(Panel(f"Arquivo não encontrado: {addon}", title="Falha", style="red"))
        raise typer.Exit(code=2)

    try:
        personagem = parse_texto(addon.read_text(encoding="utf-8"))
    except ErroParseAddon as exc:
        console.print(Panel(str(exc), title="Falha no parse", style="red"))
        raise typer.Exit(code=2)

    identidade = Table(title="Personagem", show_header=False)
    identidade.add_column("Campo", style="bold")
    identidade.add_column("Valor")
    identidade.add_row("Nome", personagem.nome or "não informado")
    identidade.add_row("Classe / spec", f"{personagem.classe or '?'} / {personagem.spec or '?'}")
    identidade.add_row("Nível / raça", f"{personagem.nivel or '?'} / {personagem.raca or '?'}")
    identidade.add_row(
        "Região / servidor",
        f"{personagem.regiao or '?'} / {personagem.servidor or '?'}",
    )
    identidade.add_row(
        "Profissões",
        ", ".join(f"{nome}={nivel}" for nome, nivel in personagem.profissoes.items())
        or "não informadas",
    )
    identidade.add_row(
        "Addon / cliente",
        f"{personagem.versao_addon or '?'} / {personagem.build_cliente or '?'}",
    )
    identidade.add_row("Checksum", personagem.checksum or "ausente")
    console.print(identidade)

    equipamento = Table(title="Equipamento", header_style="bold")
    equipamento.add_column("Slot")
    equipamento.add_column("Item")
    equipamento.add_column("Nome PT-BR")
    equipamento.add_column("ilvl", justify="right")
    equipamento.add_column("Encanto", justify="right")
    equipamento.add_column("Gemas")
    equipamento.add_column("Bônus", justify="right")
    for slot in SLOTS:
        item = personagem.equipado.get(slot)
        if item is None:
            continue
        equipamento.add_row(
            slot,
            str(item.item_id or "?"),
            item.nome_pt or "PT a confirmar",
            str(item.ilvl_comentario or "?"),
            str(item.enchant_id or "—"),
            ", ".join(str(gema) for gema in item.gem_ids) or "—",
            str(len(item.bonus_ids)),
        )
    console.print(equipamento)

    console.print(
        f"Loadouts salvos: {len(personagem.loadouts)} — "
        + ", ".join(personagem.loadouts)
        if personagem.loadouts
        else "Loadouts salvos: nenhum"
    )
    console.print(
        "Folio Ômnico: "
        + (
            ", ".join(str(runa) for runa in personagem.omnium_ids_brutos)
            or "não informado"
        )
    )
    console.print(
        f"Mochila: {sum(len(itens) for itens in personagem.mochila.values())} peças | "
        f"Catalisador: {len(personagem.catalyst_currencies)} moedas | "
        f"Marcas de ilvl: {len(personagem.slot_high_watermarks)}"
    )

    if personagem.alertas:
        tabela_alertas = Table(title="Alertas de parse", header_style="bold")
        tabela_alertas.add_column("Código")
        tabela_alertas.add_column("Severidade")
        tabela_alertas.add_column("Detalhe")
        for alerta in personagem.alertas:
            tabela_alertas.add_row(alerta.codigo, alerta.severidade, alerta.detalhe)
        console.print(tabela_alertas)

    if json_out is not None:
        json_out.write_text(
            personagem.model_dump_json(
                indent=2,
                exclude={"texto_original", "bloco_equipamento_original"},
            ),
            encoding="utf-8",
        )
        console.print(f"JSON gravado em {json_out}")


if __name__ == "__main__":
    app()
