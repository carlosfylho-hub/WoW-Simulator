# WoW Calculator Sim

Simulador local de equipamento para **World of Warcraft: Midnight — Temporada 2**, patch **12.1.5**, build **12.1.5.70783**.

Todos os números vêm do **SimulationCraft**. Nada é estimado pelo código nem por LLM.

## Estado

| Fase | Escopo | Situação |
| :-: | :--- | :-: |
| 0 | arquitetura e fontes | concluída — [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), [`docs/FONTES.md`](docs/FONTES.md) |
| 1 | motor SimC, fixture, scaffold e snapshot de dados | concluída — aceite do `simc-check` cumprido |
| 2 | parser do addon | pendente |
| 3 | catálogo | pendente |
| 4 | gerador de variações | pendente |
| 5 | relatório | pendente |
| 6 | resumo opcional com DeepSeek | pendente |
| 7 | interface web | opcional |

## Instalação

```bash
cd wow-sim
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## Dados

O projeto lê um snapshot versionado em `dados/`, com hash em `dados/MANIFEST.json`. Para copiar ou conferir a partir do repositório de dados:

```bash
python scripts/sincronizar_dados.py --check
python scripts/sincronizar_dados.py --aceitar
```

O caminho de origem padrão é `../../WoW Calculator`, relativo a `wow-sim`. Use `--origem` para apontar outro diretório e `WOWSIM_DADOS` para fazer o código ler outro snapshot.

## Binário do simc

O simulador procura, nesta ordem: `--simc`, variável `WOWSIM_SIMC`, `simc` no `PATH`, `bin/simc` ou `bin/simc.exe`.

Se não houver binário, escolha uma das opções:

1. **Baixar** o binário oficial do SimulationCraft para o seu sistema e colocar em `bin/` ou no `PATH`.
2. **Compilar** com um dos scripts:

```powershell
# Windows: instala o toolchain, se ainda não existir
winget install Kitware.CMake Ninja-build.Ninja Microsoft.VisualStudio.2022.BuildTools

# Compila a partir de um fonte já extraído
powershell -ExecutionPolicy Bypass -File scripts/build_simc.ps1 -SourceDir ..\..\simc-midnight

# Ou clona a branch midnight e compila
powershell -ExecutionPolicy Bypass -File scripts/build_simc.ps1
```

```bash
# Linux ou macOS
bash scripts/build_simc.sh
```

O script Windows importa o `vcvars64.bat`, configura com CMake e Ninja, compila sem GUI e sem rede e copia o binário para `bin/simc.exe`. O fonte usado nesta máquina declara `12.1.5.70783` e foi compilado em cerca de 1,5 min com 19 jobs. Em máquina de 2 núcleos, espere cerca de 35 minutos.

## Comandos

```bash
wowsim simc-info
wowsim simc-check
wowsim simc-check --iterations 1000 --forcar
```

`simc-check` roda o fixture `fixtures/pyrogalth.simc` em dois cenários e compara com os valores de referência:

| Cenário | Referência | Tolerância |
| :--- | --: | :-: |
| DungeonSlice | 254.000 DPS | ±3% |
| Patchwerk, 1 alvo | 204.000 DPS | ±3% |

Os valores de referência vêm do prompt de especificação e **não** substituem a execução: se o binário estiver ausente, o comando falha com código 2 e mostra as instruções, em vez de estimar.

**Resultado do aceite com 1000 iterações:**

| Cenário | DPS medido | Referência | Delta | Situação |
| :--- | --: | --: | --: | :-: |
| DungeonSlice | 255.601 | 254.000 | +0,63% | dentro |
| Patchwerk, 1 alvo | 199.485 | 204.000 | −2,21% | dentro |

O Patchwerk fica abaixo da referência do prompt, mas dentro da tolerância de ±3%; o valor é reportado como medido, não ajustado.

## Estrutura

```text
wow-sim/
  dados/          snapshot dos arquivos do projeto, com MANIFEST
  docs/           arquitetura e fontes
  fixtures/       export real do addon e fixtures sintéticos
  scripts/        sincronização de dados e compilação do simc
  src/wowsim/     pacote Python
  tests/          pytest
```

## Referências

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisões, contratos, riscos e critérios de aceite.
- [`docs/FONTES.md`](docs/FONTES.md) — inventário de dados, confiança e conflitos.
- [`docs/RAIDBOTS-REFERENCIA.md`](docs/RAIDBOTS-REFERENCIA.md) — dados estáticos do Raidbots, o que serve e o que não serve.
- [`PENDENCIAS.md`](PENDENCIAS.md) — bloqueios e pendências numeradas.

## Scripts auxiliares

```bash
python scripts/sincronizar_dados.py --check
python scripts/inspecionar_json.py dados/bonus_ids_s2.json
python scripts/extrair_texto_html.py pagina.html
python scripts/buscar_texto.py bundle.js "padrao"
```

## Regras

- Saída para o usuário em PT-BR; código e comentários em inglês.
- Todo dado de catálogo carrega `fonte` com o nome do arquivo.
- Dado ausente vira `null`, alerta e pendência; nunca estimativa.
- `--sem-llm` é o comportamento padrão até a Fase 6.
