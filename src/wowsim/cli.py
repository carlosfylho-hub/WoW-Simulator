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


if __name__ == "__main__":
    app()
