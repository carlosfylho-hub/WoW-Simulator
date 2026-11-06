# WoW Calculator Sim

Simulador local de equipamento para **World of Warcraft: Midnight — Temporada 2**, patch **12.1.5**, build **12.1.5.70783**.

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
wowsim parse fixtures/pyrogalth.simc
wowsim parse fixtures/pyrogalth.simc --json personagem.json
wowsim upgrades fixtures/pyrogalth.simc --de 12846 --para 12854 --rodar
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
| `berloque` | cada candidato em cada um dos dois slots, no nível 341, 334 ou 328 |

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
python scripts/inspecionar_json.py dados/bonus_ids_s2.json
python scripts/extrair_texto_html.py pagina.html
python scripts/buscar_texto.py bundle.js "padrao"
```

## Regras

- Saída para o usuário em PT-BR; código e comentários em inglês.
- Todo dado de catálogo carrega `fonte` com o nome do arquivo.
- Dado ausente vira `null`, alerta e pendência; nunca estimativa.
- `--sem-llm` é o comportamento padrão até a Fase 6.
