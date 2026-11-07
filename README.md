# WoW Calculator Sim

Simulador local de equipamento para **World of Warcraft: Midnight — Temporada 2**, cliente **12.1.5**, build **12.1.5.70783**.

O cliente 12.1.5 contém o conteúdo do patch 12.1 (*The Curse of Ula'tek*, raid Abismo Peçonhento com **8 chefes**) e a atualização 12.1.5 (*The Promise of Tomorrow*, raid de um chefe Kith'ix). A distinção está em [`docs/VERIFICACAO-EXTERNA.md`](docs/VERIFICACAO-EXTERNA.md).

Todos os números vêm do **SimulationCraft**. Nada é estimado pelo código nem por LLM.

## Estado

| Fase | Escopo | Situação |
| :-: | :--- | :-: |
| 0 | arquitetura e fontes | concluída — [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md), [`docs/FONTES.md`](docs/FONTES.md) |
| 1 | motor SimC, fixture, scaffold e snapshot de dados | concluída — aceite do `simc-check` cumprido |
| 2 | parser do addon | concluída — round-trip byte a byte e 17 testes |
| 3 | catálogo | concluída — nomes, bônus, encantos, gemas, runas e loot |
| 4 | gerador de variações | concluída — 7 categorias e teste com simc real |
| 5 | relatório | concluída — Markdown e HTML com empate por erro, origem e limites |
| 6 | resumo opcional com DeepSeek | concluída — opcional, validado número a número |
| 6b | verificação externa | concluída — build, itens, runas, bônus, Catalisador e patch |
| 7 | interface unificada + app desktop | concluída — FastAPI serve o React, SimC real via API, `.exe` pywebview |

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
wowsim parse fixtures/pyrogalth.simc
wowsim parse fixtures/pyrogalth.simc --json personagem.json
wowsim upgrades fixtures/pyrogalth.simc --de 12846 --para 12854 --rodar
wowsim web --host 127.0.0.1 --port 8000
wowsim app
wowsim encantos fixtures/pyrogalth.simc
wowsim talentos fixtures/pyrogalth.simc --cenario mplus
wowsim folio fixtures/pyrogalth.simc
wowsim berloques fixtures/pyrogalth.simc --nivel 341
wowsim tudo fixtures/pyrogalth.simc --iteracoes 1000 --max-variacoes 40 --sem-llm
wowsim tudo fixtures/pyrogalth.simc --iteracoes 1000 --com-llm
```

## Resumo opcional com DeepSeek

`--sem-llm` é o padrão e sempre funciona. Com `--com-llm`, o resumo recebe **somente** o JSON já calculado, com prompt restritivo. Depois da resposta, todo número é comparado com o contexto; se houver um número que não exista lá, o texto é descartado e o resumo determinístico entra no lugar.

A chave fica em `DEEPSEEK_API_KEY` e nunca no código. O pacote `openai` é opcional: `pip install -e ".[llm]"`. Sem chave ou sem pacote, o fallback determinístico é usado sem quebrar o fluxo.

## Gerador de variações

`wowsim.gen.profilesets` monta um único arquivo `.simc` com a base e linhas `profileset."nome"+=override`. A base é sempre a primeira variação.

| Categoria | O que muda |
| :--- | :--- |
| `upgrade` | troca o `bonus_id` de trilha em cada slot que o usa |
| `item` | peça da mochila no lugar da equipada, preservando encantamento e gema |
| `encanto` | encantamento por slot; os dois anéis mudam juntos |
| `gema` | troca de gema dentro da mesma família, sem misturar diamante com granada |
| `talento` | uma variação por Saved Loadout |
| `folio` | uma runa por vez dentro da mesma linha |
| `berloque` | cada candidato em cada um dos dois slots, no nível 341, 334, 328 ou 321 |

O limite `--max-variacoes` corta o corpo, nunca a base. O tempo é estimado antes de rodar. Variações de berloque on-use carregam o aviso da regra R4.

## Parser do addon

`wowsim parse` lê o export do SimC AddOn sem simular nada. O parser é uma máquina de estados por seção, porque `neck=` significa coisas diferentes no bloco principal e em `Gear from Bags`.

O que ele extrai:

- identidade: nome, classe, spec, nível, raça, região, servidor, profissões, addon, build e checksum;
- 16 slots equipados, incluindo tabardo, com `item_id`, `enchant_id`, `gem_ids`, `bonus_ids`, `crafted_stats`, `crafting_quality`, `content_tuning` e `redirected_base_stats`;
- nome PT-BR e ilvl do comentário imediatamente acima de cada slot;
- itens da mochila agrupados por slot;
- loadouts salvos com a import string descomentada;
- `omnium_talents` bruto e por rank;
- moedas de Catalisador, moedas de upgrade, marcas de ilvl e extra rolls.

O texto original é preservado. `serializar_texto` reproduz o arquivo inteiro byte a byte, e `serializar_bloco_equipamento` devolve exatamente o trecho dos slots. O checksum é descartado por padrão ao reescrever.

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

## Catálogo

`wowsim.data.catalog` expõe, sempre com campo `fonte`:

| Função | O que devolve |
| :--- | :--- |
| `nome_item(item_id)` | nome PT-BR e EN, arquivo de origem e se o `simc` conhece o item |
| `bonus_para_ilvl(bonus_id)` | trilha, rank e ilvl, ou `None` quando não validado |
| `encantamentos_por_slot(slot)` | encantamentos, arte de batalha, tinker e Magilinha |
| `gemas(tipo)` | 72 gemas, com marca de única-equipada |
| `runas_folio()` | 13 runas com nó, buff e entrada do Folio |
| `itens_mplus(slot)` | loot de M+ normalizado por slot |
| `berloques_conjurador()` | berloques utilizáveis por conjurador |

O mapa de encantamento classifica a camada: `encantamento`, `arte_de_batalha`, `magilinha`, `tinker` ou `oleo_temporario`. `enchant_id` 8730 é Arte de Batalha Hash'ey e 7935 é Magilinha; trocar um pelo outro é erro de camada.

## Alvos de item level (321 / 334 / 341 / 328)

O escopo de comparação é limitado a quatro níveis, conforme o pedido do usuário:

| Alvo | Trilha | Forja com Peçonha | `bonus_id` |
| :-: | :--- | :-: | :-: |
| 321 | Herói 6/6 | não | `12846` |
| 328 | Herói 6/6 | sim (+7) | `12848` |
| 334 | Mítico 6/6 | não | `12854` |
| 341 | Mítico 6/6 | sim (+7) | `12856` |

`ILVLS_ALVO` em [`catalog.py`](src/wowsim/data/catalog.py:25) define essa lista, e o gerador de troca de item ignora candidatos fora dela. Um berloque tem um único `item_id`; a trilha e o estado de forja são expressos só pelo `bonus_id`. Por isso os quatro níveis de berloque usam os mesmos itens do balde `teto_341` do monitor, trocando apenas o bônus. Os itens são sempre reportados com **nome em PT-BR e em inglês** (campos `nome_pt` e `nome_en` no catálogo), e a resposta ao usuário é em PT-BR.

## Interface unificada (Python + React)

O FastAPI do `wow-sim` é o **único backend**: ele serve o build do React (`Simulator-WoW/dist`) e expõe a API. Em produção não há Node; o Vite só é usado no build. Requer `pip install -e ".[web]"`.

```bash
# Produção local: serve React + API numa só porta
wowsim web --host 127.0.0.1 --port 8000

# Desenvolvimento: terminal 1 sobe o backend; terminal 2 o Vite (proxy /api e /sim)
wowsim web
cd ../Simulator-WoW && npm run dev
```

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/api/health` | espelho do healthcheck do frontend |
| `POST` | `/api/advisor` | consultor Gemini com fallback local auditado |
| `POST` | `/api/sim/profile` | roda um `.simc` e devolve **DPS medido** |
| `POST` | `/api/sim/compare` | compara base × candidato com empate por erro |
| `GET` | `/health` | estado e número de workers/threads |
| `POST` | `/sim` | enfileira um job a partir do texto do addon, responde `202` |
| `GET` | `/sim/{id}` | status e resultado do job |
| `GET` | `/sim/{id}/relatorio` | baixa o relatório Markdown quando concluído |

O worker usa `núcleos − 1` jobs simultâneos e divide as threads do `simc` entre eles. Os endpoints `/api/sim/*` rodam o **SimC real** (`simc_runner`), nunca estimam. A consulta ao `/api/advisor` usa `GEMINI_API_KEY` (e `GEMINI_MODEL`); sem chave, cai no fallback determinístico.

## App desktop independente (.exe)

O app abre numa **janela própria** (pywebview/WebView2), sem navegador e sem terminal. O backend sobe numa thread e a janela aponta para `http://127.0.0.1:<porta livre>`.

```bash
pip install -e ".[desktop]"
wowsim app
```

Para gerar um `.exe` único e clicável (Python + SimC + frontend embutidos):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_desktop.ps1
# resultado: dist_app/SimuladorWoW.exe (aprox. 52 MB)
```

O script roda `vite build`, instala o PyInstaller e empacota `frontend/`, `dados/`, `bin/simc.exe` e os templates. O binário resultante não depende de Python nem de Node instalados.

## Verificação externa

[`docs/VERIFICACAO-EXTERNA.md`](docs/VERIFICACAO-EXTERNA.md) confronta o projeto com Blizzard, SimC, Wowhead e Raidbots.

- Build do cliente: `12.1.5.70783`, confirmado no endpoint da Blizzard.
- SimC: branch `midnight`, commit `c20e2ad` com dados do build `70783`; a versão interna `1210-01` não é o patch do cliente.
- 42 itens e 13 runas comparados no Wowhead sem divergência.
- Seis faixas de `bonus_id` conferidas no Wowhead: 266, 282, 318, 321, 334 e 341.
- Catalisador preserva secundários e cantrip desde o 12.1.
- Correções: o Abismo Peçonhento tem 8 chefes, e o 12.1.5 é *The Promise of Tomorrow*, não *The Curse of Ula'tek*.

## Referências

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisões, contratos, riscos e critérios de aceite.
- [`docs/FONTES.md`](docs/FONTES.md) — inventário de dados, confiança e conflitos.
- [`docs/RAIDBOTS-REFERENCIA.md`](docs/RAIDBOTS-REFERENCIA.md) — dados estáticos do Raidbots, o que serve e o que não serve.
- [`PENDENCIAS.md`](PENDENCIAS.md) — bloqueios e pendências numeradas.

## Scripts auxiliares

```bash
python scripts/sincronizar_dados.py --check
python scripts/derivar_bonus_ilvl.py
python scripts/derivar_omnium.py
python scripts/verificar_externo.py
python scripts/verificar_bonus.py
python scripts/inspecionar_json.py dados/bonus_ids_s2.json
python scripts/extrair_texto_html.py pagina.html
python scripts/buscar_texto.py bundle.js "padrao"
```

## Regras

- Saída para o usuário em PT-BR; código e comentários em inglês.
- Todo dado de catálogo carrega `fonte` com o nome do arquivo.
- Dado ausente vira `null`, alerta e pendência; nunca estimativa.
- `--sem-llm` é o comportamento padrão até a Fase 6.
