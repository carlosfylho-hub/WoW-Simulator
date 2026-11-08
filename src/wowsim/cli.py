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
from .gen import profilesets
from .llm import montar_contexto, resumir, resumo_deterministico
from .models import Personagem, Variacao
from .parser.addon import SLOTS, ErroParseAddon, parse_texto
from .report import render as render_relatorio
from .topgear.models import TopGearRequest
from .topgear.pools import construir_pools, resumo as resumo_pools
from .topgear.runner import criar_simulador, estilo_de_luta
from .topgear.search import executar_topgear

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


def _carregar_personagem(addon: Path) -> Personagem:
    if not addon.is_file():
        console.print(Panel(f"Arquivo não encontrado: {addon}", title="Falha", style="red"))
        raise typer.Exit(code=2)
    try:
        return parse_texto(addon.read_text(encoding="utf-8"))
    except ErroParseAddon as exc:
        console.print(Panel(str(exc), title="Falha no parse", style="red"))
        raise typer.Exit(code=2)


def _executar_lote(
    personagem: Personagem,
    variacoes: list[Variacao],
    *,
    destino: Path,
    iterations: int,
    rodar: bool,
    fight_style: str = "DungeonSlice",
    sem_llm: bool = True,
) -> None:
    caminho = profilesets.escrever_arquivo(personagem, variacoes, destino)
    estimativa = profilesets.estimar_segundos(len(variacoes) - 1, iterations)
    console.print(
        f"Arquivo: [bold]{caminho}[/bold] | "
        f"{len(variacoes) - 1} variações + base | "
        f"estimativa ~{estimativa:.0f}s com {iterations} iterações"
    )
    if sem_llm:
        console.print("[dim]Resumo por LLM desligado (--sem-llm).[/dim]")

    if not rodar:
        tabela = Table(title="Variações geradas", header_style="bold")
        tabela.add_column("Nome")
        tabela.add_column("Categoria")
        tabela.add_column("Overrides", justify="right")
        tabela.add_column("Primeira linha")
        for variacao in variacoes:
            primeira = variacao.linhas_override[0] if variacao.linhas_override else "—"
            tabela.add_row(
                variacao.nome,
                variacao.categoria,
                str(len(variacao.linhas_override)),
                primeira[:70],
            )
        console.print(tabela)
        console.print("Use --rodar para executar o simc e ver os DPS.")
        return

    execucao = sr.run_simc(
        caminho,
        iterations=iterations,
        fight_style=fight_style,
        threads=sr.threads_padrao(),
    )
    resultado = sr.read_results(execucao.json_path)
    if resultado.base is None:
        console.print(
            Panel(
                "O simc não devolveu DPS da base.",
                title="Resultado inválido",
                style="red",
            )
        )
        raise typer.Exit(code=4)

    base = resultado.base.dps
    tabela = Table(title=f"Resultado — {fight_style}", header_style="bold")
    tabela.add_column("Variação")
    tabela.add_column("DPS", justify="right")
    tabela.add_column("Delta", justify="right")
    for variacao in resultado.variacoes:
        delta = 100.0 * (variacao.dps - base) / base
        tabela.add_row(variacao.nome, f"{variacao.dps:,.0f}", f"{delta:+.2f}%")
    console.print(f"Base: {base:,.0f} DPS")
    console.print(tabela)
    console.print(f"JSON: {execucao.json_path}")

    caminho_md, caminho_html = render_relatorio(
        personagem,
        resultado,
        variacoes,
        destino=PROJECT_ROOT / "saida",
        iterations=iterations,
        fight_style=fight_style,
    )
    console.print(f"Relatório: [bold]{caminho_md}[/bold] e [bold]{caminho_html}[/bold]")

    if not sem_llm:
        contexto = montar_contexto(
            resultado, variacoes, iterations=iterations, fight_style=fight_style
        )
        texto = resumir(contexto)
        if texto:
            console.print(Panel(texto, title="Resumo DeepSeek", style="cyan"))
        else:
            console.print(
                Panel(
                    resumo_deterministico(contexto),
                    title="Resumo determinístico — LLM indisponível ou descartado",
                    style="yellow",
                )
            )


def _destino(nome: str) -> Path:
    return PROJECT_ROOT / "saida" / nome


@app.command("upgrades")
def upgrades(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    de: int = typer.Option(12846, "--de", help="bonus_id da trilha atual."),
    para: int = typer.Option(12854, "--para", help="bonus_id da trilha alvo."),
    iterations: int = typer.Option(200, "--iterations", "-n", min=10),
    rodar: bool = typer.Option(False, "--rodar", help="Executa o simc."),
) -> None:
    """Troca o bonus_id de trilha em cada slot que o usa."""
    personagem = _carregar_personagem(addon)
    variacoes = profilesets.gerar(
        personagem,
        categorias={"upgrade"},
        de_bonus=de,
        para_bonus=para,
    )
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino(f"upgrades_{de}_{para}.simc"),
        iterations=iterations,
        rodar=rodar,
    )


@app.command("encantos")
def encantos(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    iterations: int = typer.Option(200, "--iterations", "-n", min=10),
    rodar: bool = typer.Option(False, "--rodar"),
) -> None:
    """Gera variações de encantamento, anéis em par e camadas separadas."""
    personagem = _carregar_personagem(addon)
    variacoes = profilesets.gerar(personagem, categorias={"encanto"})
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino("encantos.simc"),
        iterations=iterations,
        rodar=rodar,
    )


@app.command("talentos")
def talentos(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    cenario: str = typer.Option("mplus", "--cenario", help="mplus ou alvo."),
    iterations: int = typer.Option(200, "--iterations", "-n", min=10),
    rodar: bool = typer.Option(False, "--rodar"),
) -> None:
    """Gera uma variação por Saved Loadout."""
    if cenario not in {"mplus", "alvo"}:
        console.print(Panel("Cenário deve ser mplus ou alvo.", title="Falha", style="red"))
        raise typer.Exit(code=2)
    personagem = _carregar_personagem(addon)
    variacoes = profilesets.gerar(personagem, categorias={"talento"})
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino(f"talentos_{cenario}.simc"),
        iterations=iterations,
        rodar=rodar,
        fight_style="DungeonSlice" if cenario == "mplus" else "Patchwerk",
    )


@app.command("folio")
def folio(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    runas: Optional[str] = typer.Option(None, "--runas", help="Ex.: 1A-2B-3A-4A-5A."),
    iterations: int = typer.Option(200, "--iterations", "-n", min=10),
    rodar: bool = typer.Option(False, "--rodar"),
) -> None:
    """Troca uma runa por vez dentro da mesma linha do Folio."""
    personagem = _carregar_personagem(addon)
    variacoes = profilesets.gerar(personagem, categorias={"folio"}, runas=runas)
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino("folio.simc"),
        iterations=iterations,
        rodar=rodar,
    )


@app.command("berloques")
def berloques(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    nivel: int = typer.Option(341, "--nivel", help="341, 334 ou 328."),
    iterations: int = typer.Option(200, "--iterations", "-n", min=10),
    rodar: bool = typer.Option(False, "--rodar"),
) -> None:
    """Testa cada candidato nos dois slots de berloque."""
    personagem = _carregar_personagem(addon)
    try:
        variacoes = profilesets.gerar(
            personagem, categorias={"berloque"}, nivel_berloque=nivel
        )
    except ValueError as exc:
        console.print(Panel(str(exc), title="Falha", style="red"))
        raise typer.Exit(code=2)
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino(f"berloques_{nivel}.simc"),
        iterations=iterations,
        rodar=rodar,
    )


@app.command("tudo")
def tudo(
    addon: Path = typer.Argument(..., help="Export do SimC AddOn."),
    iterations: int = typer.Option(1000, "--iteracoes", "--iterations", min=10),
    max_variacoes: int = typer.Option(40, "--max-variacoes", min=1),
    de: int = typer.Option(12846, "--de"),
    para: int = typer.Option(12854, "--para"),
    nivel: int = typer.Option(341, "--nivel"),
    runas: Optional[str] = typer.Option(None, "--runas"),
    rodar: bool = typer.Option(False, "--rodar"),
    sem_llm: bool = typer.Option(True, "--sem-llm/--com-llm"),
) -> None:
    """Gera todas as categorias com limite de variações."""
    personagem = _carregar_personagem(addon)
    variacoes = profilesets.gerar(
        personagem,
        de_bonus=de,
        para_bonus=para,
        runas=runas,
        nivel_berloque=nivel,
        max_variacoes=max_variacoes,
    )
    _executar_lote(
        personagem,
        variacoes,
        destino=_destino("tudo.simc"),
        iterations=iterations,
        rodar=rodar,
        sem_llm=sem_llm,
    )


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Sobe a interface web local, sem login."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            Panel(
                "Instale as dependências web: pip install -e \".[web]\"",
                title="FastAPI ausente",
                style="red",
            )
        )
        raise typer.Exit(code=2)
    uvicorn.run("wowsim.web.app:app", host=host, port=port)


@app.command("app")
def app_desktop(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(0, "--port", help="0 escolhe uma porta livre."),
) -> None:
    """Abre a janela desktop (pywebview) sobre o mesmo backend local."""
    try:
        from .web.desktop import run
    except ImportError:
        console.print(
            Panel(
                "Instale as dependências de desktop: pip install -e \".[desktop]\"",
                title="pywebview ausente",
                style="red",
            )
        )
        raise typer.Exit(code=2)
    try:
        run(host, port)
    except RuntimeError as exc:
        console.print(Panel(str(exc), title="Falha ao abrir o app", style="red"))
        raise typer.Exit(code=2) from exc


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


@app.command("topgear")
def topgear_cmd(
    fixture: Path = typer.Option(
        FIXTURE_PADRAO, "--fixture", "-f", help="Export do addon em formato .simc."
    ),
    scenario: str = typer.Option(
        "patchwerk", "--scenario", help="patchwerk | dungeon_slice | raid | mplus."
    ),
    iterations_triagem: int = typer.Option(
        200, "--iterations-triagem", "-n", min=10, help="Iterações da triagem."
    ),
    orcamento: int = typer.Option(
        600, "--orcamento", min=1, help="Orçamento de tempo em segundos."
    ),
    pool: int = typer.Option(
        12, "--pool", min=1, help="Máximo de candidatos por slot."
    ),
    tipo_armadura: str = typer.Option(
        "tecido", "--tipo-armadura", help="tecido | couro."
    ),
    atributo: str = typer.Option(
        "Intelecto", "--atributo", help="Atributo primário da spec."
    ),
    simc: Optional[Path] = typer.Option(
        None, "--simc", help="Caminho explícito para o binário do simc."
    ),
    somente_pools: bool = typer.Option(
        False, "--somente-pools", help="Só mostra a prévia das pools, sem simular."
    ),
) -> None:
    """Top Gear: melhor conjunto medido dentro das pools e restrições."""
    caminho = Path(fixture)
    if not caminho.is_file():
        console.print(
            Panel(
                f"Fixture não encontrado: {caminho}\n"
                "Cole a saída de /simc em fixtures/pyrogalth.simc antes de rodar.",
                title="Fixture ausente",
                style="red",
            )
        )
        raise typer.Exit(code=2)

    texto = caminho.read_text(encoding="utf-8")
    personagem = parse_texto(texto)
    pools = construir_pools(
        tipo_armadura=tipo_armadura, atributo=atributo, pool_por_slot=pool
    )
    contagens = resumo_pools(pools)

    if somente_pools:
        tabela = Table(title="Pools do Top Gear", header_style="bold")
        tabela.add_column("Slot")
        tabela.add_column("Candidatos", justify="right")
        for slot, total in contagens.items():
            tabela.add_row(slot, str(total))
        console.print(tabela)
        return

    request = TopGearRequest(  # type: ignore[call-arg]
        addon=texto,
        scenario=scenario,
        iterations_triagem=iterations_triagem,
        orcamento_segundos=orcamento,
        pool_por_slot=pool,
    )
    simulador = criar_simulador(
        personagem, fight_style=estilo_de_luta(scenario), simc_path=simc
    )

    try:
        resultado = executar_topgear(personagem, pools, simulador=simulador, request=request)
    except sr.SimcError as exc:
        _erro_simc(exc, 3)
        return

    resumo = Table(title="Top Gear — resultado", header_style="bold")
    resumo.add_column("Métrica")
    resumo.add_column("Valor", justify="right")
    resumo.add_row("Pools", ", ".join(f"{slot}={n}" for slot, n in contagens.items()))
    resumo.add_row("DPS da base", f"{resultado.base_dps:,.0f}")
    resumo.add_row("DPS do melhor conjunto", f"{resultado.melhor_dps:,.0f}")
    resumo.add_row("Ganho", f"{resultado.delta_pct:+.2f}%")
    resumo.add_row("Limiar de empate", f"{resultado.limiar_pct:.2f}%")
    console.print(resumo)

    if resultado.trocas:
        trocas = Table(title="Trocas por slot", header_style="bold")
        trocas.add_column("Slot")
        trocas.add_column("De")
        trocas.add_column("Para")
        for troca in resultado.trocas:
            trocas.add_row(troca.slot, troca.de or "—", troca.para or "—")
        console.print(trocas)

    for aviso in resultado.avisos:
        console.print(Panel(aviso, title="Aviso", style="yellow"))


if __name__ == "__main__":
    app()
