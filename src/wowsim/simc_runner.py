"""SimulationCraft runner.

Responsibilities of phase 1:
- locate the simc binary through an explicit path, WOWSIM_SIMC, PATH or ./bin
- read the binary version and compare it with the addon build
- run simc with json2 pointing to a real file, never an empty value
- cache the raw JSON by input hash and parameters
- read base and profileset DPS defensively, because the JSON schema changes
  between builds
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .paths import PROJECT_ROOT

if getattr(sys, "frozen", False):
    _cache_padrao = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "WowSimCache"
else:
    _cache_padrao = PROJECT_ROOT / "cache"
CACHE_DIR = Path(os.environ.get("WOWSIM_CACHE", _cache_padrao))
BIN_DIR = PROJECT_ROOT / "bin"
BUILD_ESPERADO = "12.1.5.70783"


def _log_simc(mensagem: str) -> None:
    """Print simc activity to the terminal.

    Default is OFF for CLI/testes (``WOWSIM_LOG_SIMC`` unset = "0"). The web
    layer turns it ON at startup via :func:`configurar_log_simc`, so end users
    see per-round diagnostics without the CLI becoming noisy.
    """
    desligado = {"0", "false", "nao", "não", "off", ""}
    if os.environ.get("WOWSIM_LOG_SIMC", "0").strip().lower() in desligado:
        return
    print(f"[simc] {mensagem}", flush=True)


def configurar_log_simc(ligado: bool) -> None:
    """Enable/disable simc logging unless ``WOWSIM_LOG_SIMC`` is already set."""
    os.environ.setdefault("WOWSIM_LOG_SIMC", "1" if ligado else "0")


def _podar_cache() -> None:
    """Remove os JSONs mais antigos quando o cache passa do teto configurado.

    Teto em MB via ``WOWSIM_CACHE_MAX_MB`` (padrão 2048; 0 desliga).
    """
    try:
        limite_mb = float(os.environ.get("WOWSIM_CACHE_MAX_MB", "2048"))
    except ValueError:
        return
    if limite_mb <= 0:
        return
    limite = limite_mb * 1024 * 1024
    try:
        arquivos = [
            p for p in CACHE_DIR.glob("*.json") if ".meta." not in p.name and p.is_file()
        ]
    except OSError:
        return
    total = sum(p.stat().st_size for p in arquivos)
    if total <= limite:
        return
    for p in sorted(arquivos, key=lambda item: item.stat().st_mtime):
        if total <= limite:
            break
        try:
            tamanho = p.stat().st_size
            meta = p.with_suffix(".meta.json")
            p.unlink()
            if meta.exists():
                meta.unlink()
            total -= tamanho
        except OSError:
            continue

INSTRUCOES_SIMC = f"""O binário do SimulationCraft não foi encontrado.

Procurei em: --simc, WOWSIM_SIMC, PATH e {BIN_DIR}.

Escolha uma das opções:

(a) Baixar o binário oficial do SimulationCraft para o seu sistema em
    https://github.com/simulationcraft/simc/releases
    e colocar como bin/simc (Linux/macOS) ou bin/simc.exe (Windows), ou no PATH.

(b) Compilar a branch midnight:
    Windows: powershell -ExecutionPolicy Bypass -File scripts/build_simc.ps1
    Linux/macOS: bash scripts/build_simc.sh

O build esperado para este patch é {BUILD_ESPERADO} (WoW 12.1.5).
"""


class SimcError(RuntimeError):
    """Base error for simc integration."""


class SimcNaoEncontrado(SimcError):
    """The simc binary could not be located."""


class SimcFalhou(SimcError):
    """simc ran but exited with a non-zero code or produced no usable JSON."""


class SimcOrcamentoEsgotado(SimcFalhou):
    """The time budget ran out while simc was still running.

    Subclasses :class:`SimcFalhou` so existing handlers still work, but lets the
    search degrade gracefully (return the best partial result) instead of
    failing the whole job.
    """


class SimcSemJson(SimcError):
    """The JSON file was produced but its content is not usable."""


class SimcCancelado(SimcError):
    """The user cancelled the job while simc was running."""


@dataclass(frozen=True)
class SimcInfo:
    caminho: Path
    versao: str | None = None
    build: str | None = None
    saida_bruta: str = ""

    @property
    def build_compativel(self) -> bool | None:
        if not self.build:
            return None
        return self.build == BUILD_ESPERADO

    @property
    def aviso_build(self) -> str | None:
        if self.build is None:
            return (
                "Não foi possível ler a build do simc; a conferência de versão "
                f"ficou pendente. Build esperado: {BUILD_ESPERADO}."
            )
        if self.build != BUILD_ESPERADO:
            return (
                f"Build do simc é {self.build}, diferente do cliente do addon "
                f"({BUILD_ESPERADO}). Os números podem não valer para o patch."
            )
        return None


@dataclass(frozen=True)
class SimcExecucao:
    json_path: Path
    chave: str
    cache_hit: bool
    duracao_s: float
    comando: tuple[str, ...]
    info: SimcInfo
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass(frozen=True)
class ResultadoDps:
    nome: str
    dps: float
    erro_abs: float | None = None
    amostras: int | None = None
    eh_base: bool = False

    @property
    def erro_pct(self) -> float | None:
        if self.erro_abs is None or not self.dps:
            return None
        return 100.0 * self.erro_abs / self.dps


@dataclass(frozen=True)
class SimcResultado:
    json_path: Path
    base: ResultadoDps | None
    variacoes: tuple[ResultadoDps, ...] = ()
    avisos: tuple[str, ...] = ()
    bruto: dict[str, Any] = field(default_factory=dict)


def threads_padrao() -> int:
    """Leave one core for the system, as required by the project plan."""
    nucleos = os.cpu_count() or 2
    return max(1, nucleos - 1)


def _candidatos(explicit: str | Path | None) -> Iterable[Path]:
    if explicit:
        yield Path(explicit)
    env = os.environ.get("WOWSIM_SIMC")
    if env:
        yield Path(env)
    for nome in ("simc", "simc.exe"):
        achado = shutil.which(nome)
        if achado:
            yield Path(achado)
    yield BIN_DIR / "simc.exe"
    yield BIN_DIR / "simc"


def find_simc(explicit: str | Path | None = None) -> Path:
    """Return the first usable simc binary or raise SimcNaoEncontrado."""
    for candidato in _candidatos(explicit):
        if candidato.is_file():
            return candidato
    raise SimcNaoEncontrado(INSTRUCOES_SIMC)


_VERSAO_RE = re.compile(r"SimulationCraft\s+([0-9A-Za-z._-]+)", re.IGNORECASE)
_BUILD_RE = re.compile(r"World\s+of\s+Warcraft\s+([0-9][0-9.]*)", re.IGNORECASE)


def _parse_versao(saida: str) -> tuple[str | None, str | None]:
    versao = _VERSAO_RE.search(saida)
    build = _BUILD_RE.search(saida)
    return (
        versao.group(1) if versao else None,
        build.group(1).rstrip(".") if build else None,
    )


def ler_versao(simc: str | Path, timeout: float = 30.0) -> SimcInfo:
    """Read version and build from simc --version. Never guesses."""
    caminho = Path(simc)
    try:
        proc = subprocess.run(
            [str(caminho), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        saida = (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return SimcInfo(caminho=caminho, saida_bruta=str(exc))
    versao, build = _parse_versao(saida)
    return SimcInfo(caminho=caminho, versao=versao, build=build, saida_bruta=saida.strip())


def _parametros_canonicos(
    *,
    iterations: int,
    fight_style: str,
    threads: int | None,
    target_error: float | None,
    desired_targets: int | None,
    extra_args: Sequence[str],
    max_time: int | None = None,
) -> dict[str, Any]:
    return {
        "iterations": int(iterations),
        "fight_style": fight_style,
        "threads": threads,
        "target_error": target_error,
        "desired_targets": desired_targets,
        "extra_args": list(extra_args),
        "max_time": max_time,
    }


def chave_cache(arquivo_simc: str | Path, parametros: dict[str, Any], simc: str | Path) -> str:
    """Stable cache key from profile bytes, parameters and binary identity."""
    caminho = Path(arquivo_simc)
    binario = Path(simc)
    digest = hashlib.sha256()
    digest.update(caminho.read_bytes())
    digest.update(json.dumps(parametros, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    try:
        stat = binario.stat()
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(int(stat.st_mtime)).encode("ascii"))
    except OSError:
        digest.update(str(binario).encode("utf-8"))
    return digest.hexdigest()[:24]


def montar_comando(
    simc: str | Path,
    arquivo_simc: str | Path,
    json_path: str | Path,
    *,
    iterations: int = 200,
    fight_style: str = "DungeonSlice",
    threads: int | None = None,
    target_error: float | None = None,
    desired_targets: int | None = None,
    extra_args: Sequence[str] = (),
    max_time: int | None = None,
) -> list[str]:
    """Build the simc command line. json2 always receives a non-empty path.

    ``max_time`` is the simulated FIGHT LENGTH (simc default 300 s). Pass it only
    when a scenario needs a specific length; never derive it from a timeout.
    """
    destino = str(json_path).strip()
    if not destino:
        raise ValueError("json2 exige um caminho de arquivo; valor vazio quebra o simc.")

    comando = [
        str(simc),
        str(arquivo_simc),
        f"json2={destino}",
        f"iterations={int(iterations)}",
        f"fight_style={fight_style}",
        "report_details=0",
    ]
    if threads is not None:
        comando.append(f"threads={int(threads)}")
    if target_error is not None:
        comando.append(f"target_error={float(target_error)}")
    if desired_targets is not None:
        comando.append(f"desired_targets={int(desired_targets)}")
    if max_time is not None:
        comando.append(f"max_time={max(1, int(max_time))}")
    comando.extend(str(arg) for arg in extra_args)
    return comando


def _tail(texto: str, linhas: int = 40) -> str:
    partes = [linha for linha in (texto or "").splitlines() if linha.strip()]
    return "\n".join(partes[-linhas:])


def run_simc(
    arquivo_simc: str | Path,
    *,
    simc_path: str | Path | None = None,
    iterations: int = 200,
    fight_style: str = "DungeonSlice",
    threads: int | None = None,
    target_error: float | None = None,
    desired_targets: int | None = None,
    extra_args: Sequence[str] = (),
    timeout: float | None = 3600.0,
    max_time: int | None = None,
    cancelar: Callable[[], bool] | None = None,
    usar_cache: bool = True,
    forcar: bool = False,
) -> SimcExecucao:
    """Run simc once and return the execution metadata and JSON path."""
    perfil = Path(arquivo_simc)
    if not perfil.is_file():
        raise SimcFalhou(f"Arquivo .simc não encontrado: {perfil}")

    simc = find_simc(simc_path)
    info = ler_versao(simc)
    # ``max_time`` é a DURAÇÃO DA LUTA simulada (simc: sim.cpp, padrão 300 s), não
    # um limite de execução. Nunca derivar do ``timeout``: isso mudava o DPS
    # medido em até 2,4x e variava a luta entre rodadas. O limite de tempo de
    # parede é o ``timeout`` (subprocess.run / Popen + kill) mais abaixo.
    max_time_efetivo = max_time
    parametros = _parametros_canonicos(
        iterations=iterations,
        fight_style=fight_style,
        threads=threads,
        target_error=target_error,
        desired_targets=desired_targets,
        extra_args=extra_args,
        max_time=max_time_efetivo,
    )
    chave = chave_cache(perfil, parametros, simc)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_json = CACHE_DIR / f"{chave}.json"
    cache_meta = CACHE_DIR / f"{chave}.meta.json"

    if usar_cache and not forcar and cache_json.is_file():
        try:
            json.loads(cache_json.read_text(encoding="utf-8"))
            meta = json.loads(cache_meta.read_text(encoding="utf-8")) if cache_meta.is_file() else {}
            _log_simc(f"cache hit {chave} ({cache_json})")
            return SimcExecucao(
                json_path=cache_json,
                chave=chave,
                cache_hit=True,
                duracao_s=float(meta.get("duracao_s", 0.0)),
                comando=tuple(meta.get("comando", [])),
                info=info,
                stdout_tail=str(meta.get("stdout_tail", "")),
                stderr_tail=str(meta.get("stderr_tail", "")),
            )
        except (OSError, json.JSONDecodeError):
            pass

    tmp_dir = CACHE_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_json = tmp_dir / f"{chave}.json"
    if tmp_json.exists():
        tmp_json.unlink()

    comando = montar_comando(
        simc,
        perfil,
        tmp_json,
        iterations=iterations,
        fight_style=fight_style,
        threads=threads,
        target_error=target_error,
        desired_targets=desired_targets,
        extra_args=extra_args,
        max_time=max_time_efetivo,
    )

    _log_simc(" ".join(str(parte) for parte in comando))

    inicio = time.monotonic()
    if cancelar is None:
        # Caminho simples (CLI/testes): sem cancelamento cooperativo.
        try:
            proc = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(PROJECT_ROOT),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SimcOrcamentoEsgotado(
                f"O simc excedeu {timeout:.0f} s (orçamento). "
                f"Comando: {' '.join(comando)}"
            ) from exc
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        returncode = proc.returncode
    else:
        # Caminho com cancelamento. NÃO use PIPE aqui: o simc escreve muito no
        # stdout; sem drenar o pipe durante o polling o processo bloqueia no
        # buffer (~64 KB) e nunca termina. Redirecionamos para arquivos.
        tmp_dir_run = CACHE_DIR / "tmp"
        tmp_dir_run.mkdir(parents=True, exist_ok=True)
        out_log = tmp_dir_run / f"{chave}.stdout.log"
        err_log = tmp_dir_run / f"{chave}.stderr.log"
        with (
            open(out_log, "w", encoding="utf-8", errors="replace") as fo,
            open(err_log, "w", encoding="utf-8", errors="replace") as fe,
        ):
            proc = subprocess.Popen(
                comando,
                stdout=fo,
                stderr=fe,
                cwd=str(PROJECT_ROOT),
            )
            try:
                while True:
                    returncode = proc.poll()
                    if returncode is not None:
                        break
                    if cancelar():
                        proc.kill()
                        proc.wait()
                        raise SimcCancelado(
                            "Cancelado pelo usuário durante a simulação."
                        )
                    if timeout is not None and (time.monotonic() - inicio) > timeout:
                        proc.kill()
                        proc.wait()
                        raise SimcOrcamentoEsgotado(
                            f"O simc excedeu {timeout:.0f} s (orçamento). "
                            f"Comando: {' '.join(comando)}"
                        )
                    time.sleep(0.5)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        stdout_text = out_log.read_text(encoding="utf-8", errors="replace")
        stderr_text = err_log.read_text(encoding="utf-8", errors="replace")

    duracao = time.monotonic() - inicio
    _log_simc(f"fim em {duracao:.2f}s (codigo {returncode})")

    stdout_tail = _tail(stdout_text)
    stderr_tail = _tail(stderr_text)

    if returncode != 0:
        raise SimcFalhou(
            "O simc terminou com código "
            f"{returncode}.\nComando: {' '.join(comando)}\n"
            f"Últimas linhas:\n{stderr_tail or stdout_tail}"
        )
    if not tmp_json.is_file():
        raise SimcFalhou(
            "O simc terminou sem gerar o JSON. Confirme que json2 recebeu um "
            f"caminho válido.\nComando: {' '.join(comando)}\n"
            f"Últimas linhas:\n{stderr_tail or stdout_tail}"
        )

    try:
        dados = json.loads(tmp_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SimcSemJson(f"JSON inválido em {tmp_json}: {exc}") from exc

    meta = {
        "chave": chave,
        "criado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "perfil": str(perfil),
        "parametros": parametros,
        "comando": comando,
        "duracao_s": duracao,
        "simc": {
            "caminho": str(simc),
            "versao": info.versao,
            "build": info.build,
            "build_esperado": BUILD_ESPERADO,
            "build_compativel": info.build_compativel,
        },
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "chaves_topo": sorted(dados.keys()) if isinstance(dados, dict) else [],
    }

    shutil.move(str(tmp_json), str(cache_json))
    cache_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _podar_cache()

    return SimcExecucao(
        json_path=cache_json,
        chave=chave,
        cache_hit=False,
        duracao_s=duracao,
        comando=tuple(comando),
        info=info,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
    )


_KEYS_DPS = ("median", "mean", "avg", "dps", "value")
# Incerteza da MÉDIA, nunca a dispersão entre lutas.
#
# O simc publica as duas coisas com nomes parecidos, e elas diferem por uma ordem
# de grandeza: ``std_dev``/``stddev`` é o desvio padrão das lutas individuais
# (3% a 7% da média num perfil típico), enquanto ``mean_error`` e
# ``mean_std_dev``/``mean_stddev`` são o erro da média — o que de fato diz se uma
# diferença entre dois conjuntos é real.
#
# Usar a dispersão aqui inflava o limiar de aceitação em cerca de sete vezes e
# fazia o ranking marcar "empate" em tudo: numa execução real de 103 candidatos,
# nenhum ganho era reconhecido com ``stddev`` e 32 passam com ``mean_error``.
#
# Os blocos têm vocabulários diferentes: ``collected_data.dps`` usa
# ``mean_std_dev`` e um profileset usa ``mean_stddev``/``mean_error``. Faltando
# todos, o erro fica ``None`` e o limiar cai no piso fixo — conservador e correto.
_KEYS_ERRO = ("mean_error", "mean_std_dev", "mean_stddev")
_KEYS_AMOSTRAS = ("count", "iterations", "num_iterations", "samples")


def _numero(bloco: dict[str, Any], chaves: Sequence[str]) -> float | None:
    for chave in chaves:
        valor = bloco.get(chave)
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return float(valor)
    return None


def _resultado_de_bloco(nome: str, bloco: Any, *, eh_base: bool) -> ResultadoDps | None:
    if isinstance(bloco, (int, float)) and not isinstance(bloco, bool):
        return ResultadoDps(nome=nome, dps=float(bloco), eh_base=eh_base)
    if not isinstance(bloco, dict):
        return None

    dps = _numero(bloco, _KEYS_DPS)
    if dps is None:
        aninhado = bloco.get("dps")
        if isinstance(aninhado, dict):
            dps = _numero(aninhado, _KEYS_DPS)
            bloco = aninhado
    if dps is None:
        return None

    erro = _numero(bloco, _KEYS_ERRO)
    amostras = _numero(bloco, _KEYS_AMOSTRAS)
    return ResultadoDps(
        nome=nome,
        dps=dps,
        erro_abs=erro,
        amostras=int(amostras) if amostras is not None else None,
        eh_base=eh_base,
    )


def read_results(json_path: str | Path) -> SimcResultado:
    """Read base and profileset DPS from a simc JSON, tolerating schema drift."""
    caminho = Path(json_path)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SimcSemJson(f"Não foi possível ler {caminho}: {exc}") from exc

    if not isinstance(dados, dict):
        raise SimcSemJson(f"JSON de {caminho} não é um objeto.")

    sim = dados.get("sim", dados)
    if not isinstance(sim, dict):
        raise SimcSemJson("Bloco 'sim' ausente ou inválido.")

    avisos: list[str] = []
    base: ResultadoDps | None = None
    jogadores = sim.get("players")
    if isinstance(jogadores, list) and jogadores:
        primeiro = jogadores[0] if isinstance(jogadores[0], dict) else {}
        coletado = primeiro.get("collected_data", primeiro)
        bloco = coletado.get("dps", coletado) if isinstance(coletado, dict) else coletado
        base = _resultado_de_bloco("base", bloco, eh_base=True)
    if base is None:
        avisos.append("base_ausente_no_json")

    variacoes: list[ResultadoDps] = []
    perfis = sim.get("profilesets")
    if isinstance(perfis, list):
        # Observed in build 12.1.5.70783: profilesets is a list of results.
        resultados = perfis
    elif isinstance(perfis, dict):
        resultados = perfis.get("results")
    else:
        resultados = None

    if isinstance(resultados, list):
        for indice, entrada in enumerate(resultados):
            if not isinstance(entrada, dict):
                continue
            nome = str(entrada.get("name") or entrada.get("profile") or f"variacao_{indice}")
            resultado = _resultado_de_bloco(nome, entrada, eh_base=False)
            if resultado is not None:
                variacoes.append(resultado)
    elif resultados is None:
        avisos.append("profilesets_ausentes")

    return SimcResultado(
        json_path=caminho,
        base=base,
        variacoes=tuple(variacoes),
        avisos=tuple(avisos),
        bruto=dados,
    )


def comparar_com_referencia(
    dps: float,
    referencia: float,
    tolerancia: float = 0.03,
) -> tuple[float, bool]:
    """Return percentual difference and whether it is inside tolerance."""
    if referencia <= 0:
        raise ValueError("Referência de DPS precisa ser positiva.")
    delta_pct = 100.0 * (dps - referencia) / referencia
    return delta_pct, abs(delta_pct) <= tolerancia * 100.0
