# Workflow de Implementação — Simulador WoW

**Criado em:** 2026-11-08 · **Para:** a IA ou pessoa que vai construir o que foi planejado.
**Este arquivo diz COMO.** O PORQUÊ de cada decisão está em
[`PLANO-CONTINUIDADE.md`](PLANO-CONTINUIDADE.md) (visão, auditoria 6.A, requisitos 6.B).

> **Leia as seções 0 a 3 inteiras antes de tocar em qualquer arquivo.** Elas contêm as
> regras cuja quebra já corrompeu dados neste projeto (quebra de linha, unidade errada,
> duração de luta, formato do AMR). Cada uma delas custou horas para achar.

---

## 0. Como usar este documento

1. **Faça as tarefas na ordem do checklist (§2).** Várias dependem da anterior. A fase 1
   conserta defeitos que invalidam número; nenhuma funcionalidade nova antes dela.
2. **Uma tarefa por vez, um commit por tarefa** (ou mais de um, nunca um commit com duas
   tarefas). A mensagem segue o modelo da §1.6.
3. **Antes de corrigir um defeito, escreva o teste que o prova e veja ele falhar.** Só
   depois corrija e veja passar. Todos os testes desta lista foram desenhados assim.
4. **Ao terminar a tarefa, marque `[x]` no checklist e anote o hash do commit.** Se parou
   no meio, escreva `[~]` e uma linha dizendo onde parou.
5. **Se o código real contradizer este documento** (nome de função, linha, assinatura),
   o código real vale. Pare, registre em §9 "Desvios encontrados" e só então continue.
6. **Não "aproveite para melhorar" nada fora da tarefa.** Melhoria não pedida neste
   projeto já introduziu defeito que levou dias para ser achado.
7. **Código de referência validado** está em [`docs/referencia/`](referencia/). Foi rodado
   contra os fixtures reais. Quando uma tarefa mandar copiar de lá, copie; não reescreva.

---

## 1. Protocolo de trabalho

### 1.1 Onde está cada coisa

```
C:\Users\carlo\Desktop\
├── Crawl4AI\                  scraper do Wowhead (não é tocado neste workflow)
└── Simulador WoW\
    ├── simc-midnight\         FONTE do SimulationCraft 12.1.5.70783 — só leitura
    ├── wow-sim\               BACKEND Python (este repositório)
    │   ├── src\wowsim\        pacote
    │   ├── tests\             pytest
    │   ├── dados\             snapshot de dados do jogo (MANIFEST.json) — não editar à mão
    │   ├── dados\derivados\   dados gerados por scripts (tier_sets.json, bonus_ilvl.json…)
    │   ├── fixtures\          exports reais do personagem (pyrogalth.simc, pyrogalth-amr-181.txt)
    │   ├── docs\              este arquivo, PLANO-CONTINUIDADE.md, referencia\
    │   ├── bin\simc.exe       binário (ignorado pelo git)
    │   └── cache\             resultados do simc (ignorado pelo git)
    ├── Simulator-WoW\         FRONTEND React + Vite + Tailwind
    ├── plans\                 auditorias antigas (não versionado)
    └── enviar_github.bat      dá push nos três repositórios
```

Addons do jogo, úteis como **fonte autoritativa** de formato (só leitura):
`C:\Program Files (x86)\World of Warcraft\_retail_\Interface\AddOns\AskMrRobot\` e `…\Pawn\`.

### 1.2 Invariantes do produto (quebrar isto é bug grave)

| Id | Regra | Como verificar |
| :-: | :--- | :--- |
| P1 | **Só o SimulationCraft produz número de dano.** Heurística é *score* e nunca aparece como DPS. Suposição (ex.: "chance" de cair) aparece **rotulada** como suposição. | Todo número exibido tem origem em `LeituraSim`/JSON do simc, ou está rotulado. |
| P2 | **Não inventar dado de jogo.** Id, nome, ilvl, bônus, regra de sistema saem de `dados/`, do `item_data.inc` do simc ou de um addon instalado. Tradução de cabeça é proibida. | Toda constante nova cita o arquivo e a linha de onde veio. |
| P3 | **Teste de parser confronta fonte independente.** Para o AMR, a fonte é o export do SimC do mesmo personagem (`fixtures/pyrogalth.simc`). | O teste falha se o parser errar *qualquer* slot, não só o primeiro. |
| P4 | **1 build = 1 execução do simc.** Base e candidatos no mesmo arquivo de profileset; delta sempre contra a base **da mesma leitura**. | Nenhum delta mistura `base_dps` de uma execução com resultado de outra. |
| P5 | Código, comentários e textos de tela em **PT-BR**. Comentário explica o porquê. | — |

### 1.3 Proibições (cada uma já causou defeito real)

| Não faça | Por quê (achado) |
| :--- | :--- |
| Derivar `max_time` de `timeout` | `max_time` é a **duração da luta**. O mesmo Patchwerk mediu 351.323 DPS (15 s) e 143.412 (598 s). A-01. |
| Usar `std_dev`/`stddev` como erro | É a dispersão entre lutas (3–7%), não o erro da média (~0,5%). Fazia o ranking dar "empate" em tudo. P-035. |
| Ler número do AMR como absoluto | O AMR grava **diferença acumulada**. Lido como absoluto, o parser acertava 1 de 15 itens. A-07. |
| Emitir `drop_level` a partir da tag `d` do AMR | `d` é **vínculo** (1 = soulbound, 5 = warbound). `drop_level` < 80 reduz o nível do item no simc (`sc_item_data.cpp:208`). |
| Emitir `gem_id2=` | O simc só tem `gem_id=` (lista com `/`) e `gems=` (`item.cpp:842,858`). `gem_id2` é ignorado. |
| Emitir `crafting_quality` vindo do AMR | A escala do AMR é outra: `l8` no AMR = `crafting_quality=5` no SimC do mesmo item. |
| Usar pesos "medidos" na poda | Os salvos vieram de luta de 118 s, 69 iterações, sem versatilidade; puseram Aceleração em último, contra o guia. A-12. |
| Reativar ou expandir Top Gear/beam/poda | Escopo congelado: o Raidbots cobre. O código fica, sem manutenção. |
| Editar `dados/*.json` ou `MANIFEST.json` à mão | O gate de dados valida hashes. Dado novo vai para `dados/derivados/` por script. |
| Versionar `cache/`, `bin/`, `wowsim.db`, `.env` | Já estão no `.gitignore`. Nunca use `git add -f`. |
| Trocar CRLF por LF | O diff vira milhares de linhas falsas. Ver §1.5. |
| `git push --force`, `git reset --hard`, apagar branch | O usuário não tem como recuperar trabalho perdido. |

### 1.4 Ambiente

**Windows (máquina do usuário) — onde o simc roda:**

```bat
cd "C:\Users\carlo\Desktop\Simulador WoW\wow-sim"
.venv\Scripts\activate
pytest -q                                   :: suíte inteira
pytest -q tests\test_amr_codec.py -vv       :: um arquivo
cd ..\Simulator-WoW && npx tsc --noEmit     :: tipos do frontend
cd .. && iniciar.bat                         :: compila o frontend e abre o app
enviar_github.bat                            :: push nos 3 repositórios
```

**Linux (análise, sem simc):** o `simc.exe` e o `tsc` do projeto são binários Windows.

```bash
python3 -m venv ~/venv-wowsim
~/venv-wowsim/bin/pip install "pydantic>=2.6" pytest httpx fastapi uvicorn typer rich jinja2
cd wow-sim
PYTHONDONTWRITEBYTECODE=1 ~/venv-wowsim/bin/python -m pytest -q -p no:cacheprovider -m "not integration_simc"

# tsc para Linux, instalado FORA do projeto
mkdir -p ~/tscheck && (cd ~/tscheck && npm install --silent typescript@5.9.2)
cd ../Simulator-WoW && ~/tscheck/node_modules/.bin/tsc --noEmit -p tsconfig.json
```

Falhas **esperadas** em Linux (binário Windows: `Exec format error`), não são defeito:
`test_topgear_worker.py::test_excecao_generica_marca_erro`,
`test_web_sim_api.py::test_integracao_perfil_real`,
`test_web_sim_api.py::test_integracao_compare_mesmo_perfil_empata`
e os marcados `integration_simc`.

Para testar uma alteração **sem tocar no repositório**, copie `src/` e aponte o pytest
para a cópia. O `pyproject.toml` força `pythonpath = ["src"]`, então é preciso `-o`:

```bash
cp -r src ~/copia_src   # aplique a mudança na cópia
WOWSIM_DADOS="$PWD/dados" WOWSIM_SIMC_SRC="$PWD/../simc-midnight" \
  ~/venv-wowsim/bin/python -m pytest -q -p no:cacheprovider -o "pythonpath=$HOME/copia_src" tests/
```

### 1.5 Editar arquivos sem corromper (CRLF)

Os arquivos do repositório são **CRLF** (Windows). Ferramentas de edição comuns e
`Path.write_text` gravam LF e transformam uma mudança de 10 linhas num diff de 3.000.

Use este utilitário para qualquer edição por script. Ele aborta se o trecho não aparecer
**exatamente uma vez** e preserva a quebra de linha original:

```python
# patch_util.py — guarde FORA do repositório (ex.: ~/patch_util.py)
from pathlib import Path

def aplicar(caminho, trocas):
    """trocas = [(texto_antigo, texto_novo), ...]; tudo-ou-nada por arquivo."""
    p = Path(caminho)
    bruto = p.read_bytes()
    crlf = b"\r\n" in bruto
    texto = bruto.decode("utf-8").replace("\r\n", "\n")
    novo = texto
    for antigo, nova in trocas:
        n = novo.count(antigo)
        if n != 1:
            raise SystemExit(f"ABORTADO {caminho}: trecho aparece {n}x (esperado 1):\n{antigo[:120]!r}")
        novo = novo.replace(antigo, nova)
    p.write_bytes((novo.replace("\n", "\r\n") if crlf else novo).encode("utf-8"))
    print(f"ok {caminho} ({len(trocas)} alteracao(oes))")
```

Arquivo **novo**: grave com CRLF.

```python
Path("src/wowsim/x.py").write_bytes(conteudo.replace("\n", "\r\n").encode("utf-8"))
```

**Verificação obrigatória antes de todo commit** — os dois números têm de ser parecidos:

```bash
git diff --stat | tail -1
git diff --stat --ignore-cr-at-eol | tail -1
```

Se o primeiro for muito maior, a quebra de linha foi corrompida. Corrija antes do commit:

```python
from pathlib import Path
for a in ["src/wowsim/arquivo_afetado.py"]:
    p = Path(a); b = p.read_bytes()
    p.write_bytes(b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
```

Um `patch_util` que aborta no meio de uma lista **não aplica as trocas seguintes**. Faça
uma chamada `aplicar` por arquivo e confira a saída `ok` de cada uma.

### 1.6 Git

Identidade e mensagem (o rodapé de atribuição é o que a sessão atual definir):

```bash
git -c user.name=carlosfylho-hub -c user.email=carlosngm06@gmail.com commit -F - <<'MSG'
fix(amr): decodifica diferenca acumulada no export do AskMrRobot

<o que mudou e por quê, com a evidência medida>

<rodapé de atribuição da sessão>
MSG
```

- Repositórios: `wow-sim` (branch `master`), `Simulator-WoW` (`main`), `Crawl4AI` (`main`).
- **Pasta acessada remotamente:** o git pode não conseguir apagar os próprios arquivos
  temporários e deixa `.git/HEAD.lock`, `.git/index.lock` ou `.git/objects/maintenance.lock`.
  Depois de confirmar que **nenhum git está rodando**, remova o lock (`rm .git/HEAD.lock`);
  sem permissão de apagar, renomeie para `.git/stale-HEAD.lock` (nunca dentro de `.git/refs`).
- Lixo `.fuse_hidden*` na raiz do repositório aparece depois de rodar testes em pasta
  remota. Apague antes do `git add -A` (`rm -f .fuse_hidden*`) e confira `git status`.
- O push quem faz é o usuário, com duplo clique em `enviar_github.bat`.

### 1.7 Testes

- Marcadores: `unit` (sem simc), `golden` (fixture real), `integration_simc` (binário), `slow`.
- Todo arquivo de teste novo começa com `pytestmark = pytest.mark.unit` quando não usa simc.
- **Isolar banco em teste que sobe o app:** `db`, `perfil_store` e `topgear_db` fazem
  `from .db import DB_PATH`, então cada um tem o **seu** objeto. Patchear só `db` deixa os
  outros no banco real:

```python
from wowsim.web import db, drop_db, perfil_store, topgear_db
for modulo in (db, perfil_store, topgear_db):
    monkeypatch.setattr(modulo, "DB_PATH", tmp_path / "jobs.db")
monkeypatch.setattr(drop_db, "DB_PATH", tmp_path / "drop.db")
```

- Teste que lê um número do simc usa o **vocabulário real** do JSON: a base usa
  `collected_data.dps.mean_std_dev`; um profileset usa `mean_error` e `mean_stddev`.
  `median_std_dev` **não existe** na saída real.
- Teste que compara duas execuções ignora `Rodada.duracao_s` (tempo de parede).

### 1.8 Definição de pronto (vale para toda tarefa)

- [ ] Teste novo escrito **antes** da correção e visto falhando (quando é defeito).
- [ ] `pytest -q -m "not integration_simc"` sem falhas novas (só as esperadas da §1.4).
- [ ] `tsc --noEmit` limpo se tocou no frontend.
- [ ] `git diff --stat` ≈ `git diff --stat --ignore-cr-at-eol`.
- [ ] Checklist (§2) atualizado com o hash.
- [ ] `PENDENCIAS.md` atualizado (fechar com evidência ou abrir com condição de fechamento).

---

## 2. Checklist

Já entregue antes deste workflow (não refazer):

| Entrega | Commit |
| :--- | :--- |
| Catalisador: tier sets das 13 classes do `item_data.inc`, gêmeos e pacotes 2/4 peças | `afa468d` |
| Limiar usa erro da média; CSV e `.simc` gravados pelo backend; ícone, tooltip, sem itens repetidos | `2f20be9` (wow-sim), `bdb16a4` (Simulator-WoW) |
| Auditoria A-01…A-14 e requisitos 6.B | `cf040cd` … `8c10ccb` |

A fazer:

| Fase | Tarefa | Status | Commit |
| :-: | :--- | :-: | :-- |
| 1 | **T1** Duração da luta não vem do relógio (A-01) | [x] | `84ce4d9` |
| 1 | **T2** Codec do AMR por diferença acumulada (A-07) | [x] | `2ca377c` |
| 1 | **T3** Pesos: `Vers` e poda só com pesos curados (A-12) | [x] | `6cc1e82` |
| 1 | **T4** Pré-voo não publica DPS (A-02) | [x] | `964b4ca` |
| 2 | **T5** Catálogo de M+ por masmorra e elegibilidade | [x] | `3e26a67` |
| 2 | **T6** Motor do ranking de masmorras | [x] | `847eb25` |
| 2 | **T7** API, worker e tela do ranking | [x] | `016170b` (backend), `db117a5` (UI) |
| 2 | **T8** Grande Cofre a partir do `.gv` | [x] | `092211f`/`925fccc` (lib), `c7eba46` (backend), `8c6bbf0` (UI) |
| 2 | **T9** Várias builds: matriz, média e montagem | [x] | `551f15b` (montagem), `03221d7` (worker/API), UI `Simulator-WoW@HEAD` |
| 2 | **T10** Validação ao vivo no Windows (usuário) | [ ] | |
| 3 | **T11** String do Pawn | [x] | `32b9888` (medição), `03221d7`, UI; validar no jogo (T10) |
| 3 | **T12** String do AMR | [x] | `03221d7` (`/api/exportar/amr`), UI; importar no jogo (T10) |
| 4 | **T13** Base por lote (A-03) | [x] | |
| 4 | **T14** Cenários equivalentes na tela (A-04) | [x] | `18c39ae` |
| 4 | **T15** Higiene: nome de arquivo e threads no cache (A-05, A-06) | [x] | `65e8a23` (A-05), `8e7761a` (A-06) |
| 4 | **T16** Bloco de encantamentos do AMR fecha P-016 (A-10) | [x] | mapa gerado de BiB real |
| 5 | **U0–U7** Redesign da interface (abas Masmorras/Perfil/Histórico, tema azul-noite, Top Gear e Droptimizer em "Avançado") | [ ] | plano e checklist próprios em `Simulator-WoW/docs/PLANO-REDESIGN-UI.md` |

---

## 3. Mapa do código que este workflow toca

| Arquivo | Papel |
| :--- | :--- |
| `src/wowsim/simc_runner.py` | `run_simc`, `montar_comando`, `chave_cache`, `read_results`, `_KEYS_ERRO`. |
| `src/wowsim/topgear/runner.py` | `criar_simulador(personagem, *, fight_style, threads, target_error, simc_path, usar_cache, pasta, cancelar, orcamento_restante)` devolve `executar(candidatos: Mapping[str, Conjunto], iterations) -> LeituraSim`. Uma chamada = **uma execução** do simc com a base e os candidatos. `estilo_de_luta(cenario)`. `linhas_override` emite `talents=` quando `Conjunto.talentos` está preenchido. `preflight(...)`. |
| `src/wowsim/topgear/models.py` | `Candidato`, `Conjunto` (`com_troca`, `item_id`), `ContextoSpec`, `TopGearRequest`, `Cenario`. |
| `src/wowsim/topgear/search.py` | `conjunto_do_personagem(personagem)`, `_limiar_por_erro(piso, *erros)`. |
| `src/wowsim/topgear/catalisador.py` | `gemeo_catalisado(origem, classe)`, `pacotes_de_tier`, `contexto_com_catalisador`. |
| `src/wowsim/topgear/pools.py` | `NIVEL_PARA_BONUS = {341: 12856, 334: 12854, 328: 12848, 321: 12846}`, `construir_contexto`. |
| `src/wowsim/topgear/constraints.py` | `validar(conjunto, ctx) -> (ok, motivos)`. |
| `src/wowsim/data/catalog.py` | `_flatten_mplus()`, `normalizar_slot`, `atributo_primario`, `slots_do_item`, `bonus_para_ilvl`, `nome_item`, `visual_item`. **`ItemLoot.origem` é a subseção (slot para armadura), não a masmorra.** |
| `src/wowsim/data/pesos.py` | `pesos_para(classe, spec)` — pesos curados, fonte `curado:…`. |
| `src/wowsim/data/pesos_medidos.py` | `normalizar_scale_factors`, `derivar_pesos_medidos`, `carregar_pesos_medidos`. |
| `src/wowsim/parser/amr.py` | `parse_amr`, `ItemAMR`, `_decodificar_item`, `_parse_conjunto`, `_linha_item`, `para_personagem`. |
| `src/wowsim/droptimizer/pools.py` | `ids_do_inv`, `inv_ignorados`, `itens_do_inv` — leem o `.inv` do AMR. |
| `src/wowsim/models.py` | `Personagem` (`classe`, `spec`, `loadouts: dict[nome, import string]`, `equipado`, `talents_atual`), `ItemEquipado`, `ItemLoot`. |
| `src/wowsim/web/drop_api.py`, `drop_worker.py`, `drop_db.py`, `worker.py` | Padrão de job assíncrono a copiar (criar, consultar, cancelar, resultado, fila). |
| `Simulator-WoW/src/components/DroptimizerPanel.tsx` | Padrão de tela: ícone (`iconeDoItem`), tooltip (`useItemTooltip().showTooltip`), botão que grava arquivo pelo backend. |

---

## 4. Fase 1 — números em que dá para confiar

### T1 — A duração da luta não vem do relógio (A-01)

**Problema.** `run_simc` transforma o `timeout` (limite de execução) em `max_time`, que no
simc é a **duração da luta** (`simc-midnight/engine/sim/sim.cpp:3802`; padrão 300 s em
`sim.cpp:1590`). `criar_simulador` passa o orçamento restante como `timeout` (ou 3600 s na
CLI), então a luta encolhe a cada rodada e a CLI simula luta de uma hora. O DungeonSlice
escapou porque força 360 s (`sim.cpp:2349`); o Patchwerk, cenário padrão, não.

**Arquivos.** `src/wowsim/simc_runner.py`, novo `tests/test_max_time_fight_length.py`.

**Passo 1 — teste primeiro.** Copie `docs/referencia/test_max_time_fight_length.py` para
`tests/`. Rode e **confirme que 2 testes falham** (`assert 598 is None` e chaves de cache
diferentes). Esse teste já foi executado contra o código atual com esse resultado.

**Passo 2 — correção** em `run_simc` (troca exata, via `patch_util`):

```python
# ANTES
    # Deixa o simc parar sozinho 2 s antes do nosso timeout: ele ainda gravou o
    # JSON (iterações parciais) e evitamos matar o processo sem resultado.
    max_time_efetivo = max_time
    if max_time_efetivo is None and timeout is not None:
        max_time_efetivo = max(1, int(timeout) - 2)

# DEPOIS
    # ``max_time`` é a DURAÇÃO DA LUTA simulada (simc: sim.cpp, padrão 300 s), não
    # um limite de execução. Nunca derivar do ``timeout``: isso mudava o DPS
    # medido em até 2,4x e variava a luta entre rodadas. O limite de tempo de
    # parede é o ``timeout`` (subprocess.run / Popen + kill) mais abaixo.
    max_time_efetivo = max_time
```

E a docstring de `montar_comando`:

```python
# ANTES
    ``max_time`` is passed straight to simc so it stops by itself and still
    writes the JSON (partial iterations) instead of being killed by our
    timeout with no output.

# DEPOIS
    ``max_time`` is the simulated FIGHT LENGTH (simc default 300 s). Pass it only
    when a scenario needs a specific length; never derive it from a timeout.
```

**Por que é seguro.** O estouro de tempo continua protegido: `subprocess.run(timeout=…)`
e o laço do `Popen` matam o processo e levantam `SimcOrcamentoEsgotado`, que a busca já
trata devolvendo o melhor parcial. O `max_time` nunca deu "JSON parcial" — ele só mudava
o tamanho da luta.

**Passo 3 — validar.** Os 3 testes novos passam; `tests/test_degradacao_orcamento.py`
(inclusive `test_montar_comando_inclui_max_time`, que passa `max_time` explícito) e
`tests/test_simc_runner.py` continuam verdes. Validado numa cópia: 101 passaram.

**Efeitos colaterais esperados.** As chaves de cache antigas (com `max_time` no
parâmetro) deixam de ser usadas; não apague `cache/`, a poda (`_podar_cache`) cuida. O
pré-voo passa a simular luta de 300 s com 5 iterações (segundos).

**Aceite.** (a) testes acima; (b) no Windows, `wowsim simc-check --forcar` e registrar no
README os novos números de aceite, que podem ter sido medidos com a luta errada.

**Commit:** `fix(simc): max_time e duracao da luta, nao limite de execucao (A-01)`

---

### T2 — Codec do AMR por diferença acumulada (A-07)

**Problema.** O AskMrRobot grava os números de cada item como **diferença** para o item
anterior da mesma seção. Fonte: `AddOns/AskMrRobot/AskMrRobot-Serializer/AskMrRobot-Serializer.lua`
(`appendItemsToExport`, linhas 751–870) e o leitor oficial
`AddOns/AskMrRobot/Import.lua` (`parseItemList`, linhas 127–272). O parser do projeto lê
como valor absoluto e acerta **1 de 15** itens. Do mesmo erro nascem:

- `drop_level=1` na linha do simc (a tag `d` é vínculo, não nível de drop);
- `gem_id2=` (inexistente no simc);
- `crafting_quality=8` (escala do AMR, não do simc);
- `bonus_ids_negativos` (bônus negativo não existe; eram diferenças negativas);
- itens repetidos da mochila descartados (diferença `0` lida como id `0`).

**Tabela das tags** (conferida no `Import.lua`):

| Tag | Campo | Diferença? |
| :-: | :--- | :-: |
| (início) | id do item | **sim** |
| `s` | slot (1–17) | não |
| `u` | upgradeId | **sim** |
| `v` | level | **sim** |
| `n` | content tuning | **sim** |
| `b` | cada bônus, encadeado | **sim** |
| `j` `k` | stats de craft | não |
| `l` | qualidade de craft (escala do AMR) | não |
| `d` | vínculo: 1 soulbound, 5 warbound | não |
| `c` | `c1` = item catalisado | não |
| `h` | discSpellId | não |
| `o` | origem do Catalisador (= `redirected_base_stats` do simc) | **sim** |
| `x` `y` `z` | gemas 1–3, **contador compartilhado** | **sim** |
| `e` | encantamento | **sim** |
| `t` | inventoryId (só em strings de importação) | não |
| `!…` | guid, sempre no fim | — |

Os contadores **zeram por seção** (`.q2`, `.q3`, `.inv`, `.gv`) e os itens vêm ordenados
por id. A ordem das tags dentro do token não importa para o `Import.lua` (ele lê letra a
letra), **exceto** `x → y → z`, que dividem o contador.

**Arquivos.**
- novo `src/wowsim/parser/amr_codec.py` ← copie `docs/referencia/amr_codec.py` (sem o
  cabeçalho "REFERÊNCIA VALIDADA"; mantenha o resto idêntico);
- `src/wowsim/parser/amr.py` (modelo `ItemAMR`, `_parse_conjunto`, `_linha_item`,
  `ImportAMR`, `parse_amr`);
- `src/wowsim/droptimizer/pools.py` (`ids_do_inv`, `inv_ignorados`, `itens_do_inv`);
- novo `tests/test_amr_codec.py`; ajustes em `tests/test_parser_amr.py`.

**Validação já feita do codec de referência** contra os fixtures reais:

| Verificação | Resultado |
| :--- | :--- |
| `.q2` × `fixtures/pyrogalth.simc` | ids **15/15**, encantos **15/15**, gemas **15/15**, bônus **14/15** (a capa diverge em um bônus — item craftado, investigar à parte) |
| Origem do Catalisador | pernas `271545 ← 273786`, torso `271549 ← 272231` = **exatamente** os `redirected_base_stats` do export do SimC |
| `.inv` | 418 itens, 68 repetidos em sequência preservados |
| Ida e volta (`codificar_itens(decodificar_itens(x)) == x`) | **idêntico byte a byte** em `.q2`, `.q3` e `.inv` |

**Passo 1 — testes primeiro** (`tests/test_amr_codec.py`). Os três primeiros falham hoje.

```python
"""Codec do AMR: diferença acumulada, confrontado com o export do SimC (fonte independente)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from wowsim.parser.amr import parse_amr, _linha_item
from wowsim.parser.amr_codec import codificar_itens, decodificar_itens

pytestmark = pytest.mark.golden

RAIZ = Path(__file__).resolve().parents[1]
AMR = (RAIZ / "fixtures" / "pyrogalth-amr-181.txt").read_text(encoding="utf-8")
SIMC = (RAIZ / "fixtures" / "pyrogalth.simc").read_text(encoding="utf-8")


def _verdade() -> dict[str, dict]:
    saida = {}
    for m in re.finditer(r"^(\w+)=,id=(\d+)(.*)$", SIMC, re.M):
        extra = m.group(3)
        def lista(campo):
            achado = re.search(campo + r"=([\d/]+)", extra)
            return sorted(int(x) for x in achado.group(1).split("/")) if achado else []
        enchant = re.search(r"enchant_id=(\d+)", extra)
        redirect = re.search(r"redirected_base_stats=(\d+)", extra)
        saida[m.group(1)] = {
            "id": int(m.group(2)),
            "gemas": lista("gem_id"),
            "enchant": int(enchant.group(1)) if enchant else None,
            "redirect": int(redirect.group(1)) if redirect else None,
        }
    return saida


def _secao(nome: str) -> list[str]:
    m = re.search(r"\." + nome + r";(.*?)(?:;\.[a-z]+\d*;|\$|$)", AMR, re.S)
    return [t for t in m.group(1).split(";") if t.strip()] if m else []


def test_todos_os_slots_batem_com_o_export_do_simc() -> None:
    verdade = _verdade()
    conjunto = parse_amr(AMR).conjunto_atual
    erros = [
        (slot, item.item_id, verdade[slot]["id"])
        for slot, item in conjunto.itens.items()
        if slot in verdade and item.item_id != verdade[slot]["id"]
    ]
    assert erros == []
    assert len([s for s in conjunto.itens if s in verdade]) == 15


def test_encantos_gemas_e_origem_do_catalisador() -> None:
    verdade = _verdade()
    conjunto = parse_amr(AMR).conjunto_atual
    for slot, item in conjunto.itens.items():
        v = verdade.get(slot)
        if not v:
            continue
        assert (item.enchant_id or None) == v["enchant"], slot
        assert sorted(item.gem_ids) == v["gemas"], slot
        if v["redirect"]:
            assert item.catalyst_source == v["redirect"], slot


def test_linha_do_simc_nao_tem_campos_corrompidos() -> None:
    conjunto = parse_amr(AMR).conjunto_atual
    for item in conjunto.itens.values():
        linha = _linha_item(item)
        assert "drop_level=" not in linha
        assert "gem_id2=" not in linha
        assert "crafting_quality=" not in linha


def test_mochila_preserva_itens_repetidos() -> None:
    itens = decodificar_itens(_secao("inv"))
    assert len(itens) == 418
    assert sum(a.item_id == b.item_id for a, b in zip(itens, itens[1:])) == 68


@pytest.mark.parametrize("secao", ["q2", "q3", "inv"])
def test_ida_e_volta_identica(secao: str) -> None:
    original = _secao(secao)
    assert codificar_itens(decodificar_itens(original)) == original
```

**Passo 2 — modelo `ItemAMR`** em `parser/amr.py`:

```python
class ItemAMR(BaseModel):
    """Um item decodificado do conjunto AMR (valores já sem diferença acumulada)."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    item_id: int
    content_tuning: int | None = None
    bonus_ids: list[int] = Field(default_factory=list)
    crafted_stats: tuple[int, int] | None = None
    # Escala do AMR, NÃO é o crafting_quality do simc ('l8' no AMR = 5 no SimC).
    craft_quality_amr: int | None = None
    # Tag 'd': 1 = soulbound, 5 = warbound. Não é nível de drop.
    vinculo: int | None = None
    enchant_id: int | None = None
    gem_ids: list[int] = Field(default_factory=list)
    # Tag 'o': item de origem do Catalisador = redirected_base_stats do simc.
    catalyst_source: int | None = None
    guid: str | None = None
    token_bruto: str
```

Saem: `bonus_ids_negativos`, `crafting_quality`, `drop_level`, `checksum`,
`campos_desconhecidos`. Antes de remover, procure os usos:

```bash
grep -rn "bonus_ids_negativos\|\.drop_level\|campos_desconhecidos\|\.checksum\|crafting_quality" src tests
```

`Personagem.checksum` e `ItemEquipado.crafting_quality` (do export do SimC) **não** são
deste modelo — não mexa neles.

**Passo 3 — decodificação** em `parser/amr.py`. Apague `_TOKEN_ITEM`, `_CAMPO_NUMERICO`,
`_CHECKSUM` e `_decodificar_item`; reescreva `_parse_conjunto`:

```python
from .amr_codec import ItemAmr, decodificar_itens


def _para_item_amr(token: str, dec: ItemAmr, avisos: list[AlertaParse]) -> ItemAMR:
    slot = SLOTS_AMR.get(dec.slot) if dec.slot is not None else None
    if slot is None:
        slot = f"slot_{dec.slot}"
        avisos.append(
            AlertaParse(
                codigo="amr_slot_desconhecido",
                detalhe=f"slot {dec.slot} no item {dec.item_id}",
                severidade="aviso",
            )
        )
    return ItemAMR(
        slot=slot,
        item_id=dec.item_id,
        content_tuning=dec.tuning or None,
        bonus_ids=list(dec.bonus_ids),
        crafted_stats=(dec.stat1, dec.stat2) if dec.stat1 and dec.stat2 else None,
        craft_quality_amr=dec.craft_quality or None,
        vinculo=dec.vinculo or None,
        enchant_id=dec.enchant_id or None,
        gem_ids=[g for g in dec.gem_ids if g],
        catalyst_source=dec.catalyst_source or None,
        guid=dec.guid,
        token_bruto=token,
    )


def _parse_conjunto(chave: str, tokens: list[str], avisos: list[AlertaParse]) -> ConjuntoAMR:
    # decodificar_itens pula exatamente os mesmos tokens (vazios e "_"),
    # então o zip mantém o par token <-> item.
    validos = [t.strip() for t in tokens if t.strip() and t.strip() != "_"]
    itens: dict[str, ItemAMR] = {}
    desconhecidos: list[int] = []
    for token, dec in zip(validos, decodificar_itens(validos)):
        item = _para_item_amr(token, dec, avisos)
        if item.slot.startswith("slot_"):
            desconhecidos.append(int(item.slot.split("_", 1)[1]))
        itens[item.slot] = item
    return ConjuntoAMR(chave=chave, itens=itens, slots_desconhecidos=desconhecidos)
```

**Passo 4 — linha do simc** (`_linha_item`):

```python
def _linha_item(item: ItemAMR) -> str:
    partes = [f"{item.slot}=", f"id={item.item_id}"]
    if item.enchant_id:
        partes.append(f"enchant_id={item.enchant_id}")
    if item.gem_ids:
        # O simc só conhece gem_id= (lista com "/") e gems=; não existe gem_id2.
        partes.append("gem_id=" + "/".join(str(g) for g in item.gem_ids))
    if item.bonus_ids:
        partes.append("bonus_id=" + "/".join(str(b) for b in item.bonus_ids))
    if item.content_tuning:
        partes.append(f"content_tuning={item.content_tuning}")
    if item.crafted_stats is not None:
        partes.append(f"crafted_stats={item.crafted_stats[0]}/{item.crafted_stats[1]}")
    if item.catalyst_source:
        partes.append(f"redirected_base_stats={item.catalyst_source}")
    # Nunca emitir drop_level (a tag 'd' é vínculo) nem crafting_quality (escala do
    # AMR difere da do simc). Com o export do SimC presente, a combinação usa os dele.
    return ",".join(partes)
```

**Passo 5 — `.gv` no `ImportAMR`.** Adicione `gv: list[str] = Field(default_factory=list)`
ao lado de `inv`, e em `parse_amr` preencha igual ao `.inv`:
`gv=[token for token in secoes.get("gv", []) if token],`.

**Passo 6 — mochila** em `droptimizer/pools.py`. Troque a leitura manual pelos itens
decodificados:

```python
from ..parser.amr_codec import decodificar_itens


def ids_do_inv(importacao) -> list[int]:
    """Ids de item do ``.inv`` do AMR (já sem diferença acumulada)."""
    return sorted({it.item_id for it in decodificar_itens(importacao.inv) if it.item_id > 0})


def inv_ignorados(importacao) -> list[int]:
    return sorted({
        it.item_id
        for it in decodificar_itens(importacao.inv)
        if it.item_id > 0 and not catalog.slots_do_item(it.item_id)
    })
```

Em `itens_do_inv`, substitua o laço sobre `_ID_INV` e `_CAMPO_INV` por
`for it in decodificar_itens(importacao.inv):`, usando `it.item_id`, `list(it.bonus_ids)`,
`[g for g in it.gem_ids if g]` e `it.enchant_id or None`. Mantenha o resto da função
(ilvl via `bonus_para_ilvl`, um `ItemPossuido` por slot, `deduplicar`). Remova `_ID_INV`
e `_CAMPO_INV` se ficarem sem uso.

**Passo 7 — testes antigos.** Rode `tests/test_parser_amr.py`, `tests/test_combinar.py`,
`tests/test_droptimizer*.py`. **Regra:** se um teste antigo afirma um valor que contradiz o
export do SimC do mesmo personagem, o teste está errado — corrija citando a linha do
`fixtures/pyrogalth.simc`. Exemplo: um teste que espere `bonus_ids_negativos` deve
passar a esperar o bônus decodificado.

**Aceite.** Os 7 testes novos verdes; nenhum teste antigo removido sem justificativa no
commit; `grep -rn "drop_level\|gem_id2" src/wowsim/parser` vazio.

**Commit:** `fix(amr): decodifica diferenca acumulada; sem drop_level, gem_id2 e crafting_quality do AMR (A-07)`

---

### T3 — Pesos: `Vers` e poda só com pesos curados (A-12)

**Problema.** O simc chama o fator de versatilidade de `Vers`
(`cache/752b8725be1361d8a9eb4bce.json`: `Int, SP, Crit, Haste, Mastery, Vers`), e
`normalizar_scale_factors` filtra por `"versatility"`: a versatilidade some. Pior: os
pesos medidos salvos (luta de 118 s, 69 iterações) puseram **Aceleração em último**,
contra o guia do projeto (`dados/demonology_warlock.json`,
`prioridade_atributos_secundarios`: Aceleração 1º), e são eles que a poda usa.

**Passo 1 — alias** em `data/pesos_medidos.py`, logo abaixo de `SECUNDARIOS`:

```python
# Nomes que o simc usa em scale_factors -> nomes do projeto (o simc diz "Vers").
_ALIAS_SIMC = {
    "crit": "crit",
    "haste": "haste",
    "mastery": "mastery",
    "vers": "versatility",
    "versatility": "versatility",
}
```

e no laço de `normalizar_scale_factors`:

```python
# ANTES
        nome = str(chave).strip().lower()
# DEPOIS
        nome = _ALIAS_SIMC.get(str(chave).strip().lower())
```

**Passo 2 — poda só com curados.** Em `topgear/search.py` (perto da linha 843) e
`droptimizer/search.py` (linha 220), o mesmo trecho:

```python
# ANTES
        pesos_heur = pesos_medidos.carregar_pesos_medidos(
            personagem
        ) or pesos_mod.pesos_para(contexto.classe, contexto.spec)

# DEPOIS
        # Pesos medidos ficam fora da poda até haver medição válida (luta de
        # duração correta, milhares de iterações). Os salvos hoje puseram
        # Aceleração em último, contra o guia. Ver PLANO-CONTINUIDADE A-12.
        pesos_heur = pesos_mod.pesos_para(contexto.classe, contexto.spec)
```

Se `pesos_medidos` ficar sem uso no arquivo, remova o import.

**Testes.**

```python
# tests/test_pesos_alias.py
import pytest
from wowsim.data.pesos_medidos import normalizar_scale_factors

pytestmark = pytest.mark.unit


def test_vers_do_simc_vira_versatility() -> None:
    bruto = {"sim": {"players": [{"scale_factors": {
        "Int": 64.4, "SP": 60.0, "Crit": 47.3, "Haste": 31.7, "Mastery": 42.8, "Vers": 36.7,
    }}]}}
    pesos = normalizar_scale_factors(bruto)
    assert set(pesos) == {"crit", "haste", "mastery", "versatility"}
    assert pesos["crit"] == 1.0
```

E um teste de que a poda ignora pesos medidos: `monkeypatch` em
`pesos_medidos.carregar_pesos_medidos` devolvendo pesos absurdos e conferir que o aviso
de poda cita a fonte `curado:`.

**Commit:** `fix(pesos): Vers vira versatility e a poda usa so pesos curados (A-12)`

---

### T4 — Pré-voo não publica DPS (A-02)

**Gravidade revista: baixa.** A tela mostra só `rodada` e `estagio`
(`TopGearPanel.tsx:691`); o DPS inflado do pré-voo aparece no log e no JSON de
progresso. Em `web/topgear_worker.py` (linha ~128) e `web/drop_worker.py` (~160):

```python
# ANTES
                "estagio": "pre-voo",
                "dps": pre.dps,
                "duracao_s": round(pre.duracao_s, 2),
# DEPOIS
                "estagio": "pre-voo",
                # Sem DPS: 5 iterações servem para saber se o simc roda o perfil,
                # não para medir dano.
                "duracao_s": round(pre.duracao_s, 2),
```

**Commit:** `fix(worker): pre-voo nao publica DPS de 5 iteracoes (A-02)`

---

## 5. Fase 2 — o que o sistema vai responder

Requisitos completos: `PLANO-CONTINUIDADE.md` §6.B. Resumo: ranking de masmorras para o
bonus roll, com o % de cada item e etiquetas "upgrade direto / para catalisar / ambos /
não serve"; duas ordens (quantidade × maior item); Grande Cofre; várias builds.

Pacote novo: `src/wowsim/masmorras/` com `__init__.py`, `catalogo.py`, `avaliar.py`,
`modelos.py`.

### T5 — Catálogo de M+ por masmorra e elegibilidade

**Problema.** O catálogo descarta a masmorra: `_loot_de_item` guarda `origem=sub`, que
para armadura é o slot (`helm`). Os berloques ficam em subseções com o nome da masmorra e
não têm `dungeon_pt`. As subseções foram conferidas em `dados/mplus_loot_database.json`.

**Arquivo.** `src/wowsim/masmorras/catalogo.py` ← copie as partes
`MASMORRA_DA_SUBSECAO`, `SECAO_ARMADURA`, `ItemDeMasmorra`, `itens_por_masmorra` e
`elegivel` de `docs/referencia/masmorras.py`. Troque `from wowsim.data import catalog` por
`from ..data import catalog`.

Resultado validado com os dados reais: **90** itens com masmorra, **51** elegíveis para
Warlock (tecido, Intelecto), de 4 a 8 por masmorra:

| Masmorra | Elegíveis |
| :--- | --: |
| Altar das Presas | 8 |
| Templo de Sethraliss | 8 |
| Murder Row | 7 |
| Descanso do Rei | 7 |
| Arena da Chaga do Caos | 6 |
| Covil de Nalorakk | 6 |
| O Vale Ofuscante | 5 |
| Piscinas da Vida Rubi | 4 |

**Regras de elegibilidade** (`elegivel`): armadura só do tipo da classe; berloque de
conjurador para Intelecto (`usavel_por_conjurador is not False`); demais itens pelo
atributo primário de `catalog.atributo_primario`; **atributo desconhecido = mantém** (o
simc decide). Tipo de armadura e atributo vêm de `tipo_armadura_da_classe` e
`atributo_da_classe` em `web/topgear_worker.py` — mova as duas para
`src/wowsim/data/classes.py` e importe de lá nos dois lugares (o pacote `masmorras` não
deve depender de `web`).

**Teste** (`tests/test_masmorras_catalogo.py`): as contagens da tabela acima para Warlock;
nenhum item de couro elegível para tecido; todo berloque tem masmorra resolvida pela
subseção.

**Commit:** `feat(masmorras): catalogo de M+ por masmorra e elegibilidade por classe`

### T6 — Motor do ranking

**Arquivos.** `src/wowsim/masmorras/avaliar.py`, `src/wowsim/masmorras/modelos.py`.

**Regras que não podem ser quebradas aqui:** P4 (uma execução por build; delta contra a
base da **mesma** leitura), P1 (a "chance" é suposição rotulada), A-01 (não passar
`max_time`).

**6.1 Montar os candidatos** — cada item vira um `Conjunto` com uma troca; anel e
berloque em dois slots; slot de tier ganha também o gêmeo catalisado.

```python
from __future__ import annotations

from dataclasses import dataclass

from ..topgear.catalisador import gemeo_catalisado
from ..topgear.models import Candidato, Conjunto
from ..topgear.pools import NIVEL_PARA_BONUS
from .catalogo import ItemDeMasmorra

SLOTS_DUPLOS = {"finger": ("finger1", "finger2"), "trinket": ("trinket1", "trinket2")}


@dataclass(frozen=True)
class Opcao:
    nome: str            # nome do profileset, único no arquivo
    item: ItemDeMasmorra
    slot: str            # slot interno onde foi testado
    catalisado: bool


def montar_opcoes(
    base: Conjunto, itens: list[ItemDeMasmorra], *, ilvl: int, classe: str | None
) -> tuple[dict[str, Conjunto], dict[str, Opcao]]:
    if ilvl not in NIVEL_PARA_BONUS:
        raise ValueError(f"ilvl {ilvl} sem bonus_id conhecido; use {sorted(NIVEL_PARA_BONUS)}.")
    bonus = NIVEL_PARA_BONUS[ilvl]
    conjuntos: dict[str, Conjunto] = {}
    opcoes: dict[str, Opcao] = {}
    for item in itens:
        for slot in SLOTS_DUPLOS.get(item.slot, (item.slot,)):
            if base.item_id(slot) == item.item_id:
                continue
            cru = Candidato(
                slot=slot, item_id=item.item_id, bonus_id=bonus, bonus_ids=[bonus],
                ilvl=ilvl, fonte=f"mplus:{item.masmorra}", nome_pt=item.nome_pt,
            )
            variantes = [(cru, False)]
            gemeo = gemeo_catalisado(cru, classe)
            if gemeo is not None:
                variantes.append((gemeo, True))
            for candidato, catalisado in variantes:
                nome = f"{'k' if catalisado else 'c'}_{item.item_id}_{slot}"
                conjuntos[nome] = base.com_troca(slot, candidato)
                opcoes[nome] = Opcao(nome, item, slot, catalisado)
    return conjuntos, opcoes
```

Antes de mandar ao simc, descarte conjuntos ilegais com
`topgear.constraints.validar(conjunto, contexto)` (ex.: arma de duas mãos com mão
secundária). Dois berloques de uso **não** são descartados: viram aviso no item ("o
cooldown compartilhado não é simulado"), regra R4 do projeto.

**6.2 Ler o resultado** — o delta de cada opção é contra a base **da mesma leitura**.
Quando a referência não é a base do arquivo (camada de builds, T9), passe o nome do
profileset de referência.

```python
from ..topgear.runner import LeituraSim
from ..topgear.search import _limiar_por_erro

LIMIAR_PCT = 0.15


def avaliar(
    leitura: LeituraSim, opcoes: dict[str, Opcao], *, referencia: str | None = None
) -> list["Avaliacao"]:
    if referencia is None:
        base, base_erro = leitura.base_dps, leitura.base_erro
    else:
        base, base_erro = leitura.resultados.get(referencia), leitura.erros.get(referencia)
    if not base or base <= 0:
        raise ValueError("A leitura não trouxe o DPS de referência.")

    melhor: dict[int, dict] = {}  # por item: melhor cru e melhor catalisado entre os slots
    for nome, op in opcoes.items():
        dps = leitura.resultados.get(nome)
        if dps is None:
            continue
        delta = 100.0 * (dps - base) / base
        limiar = _limiar_por_erro(LIMIAR_PCT, base_erro, leitura.erros.get(nome))
        registro = melhor.setdefault(op.item.item_id, {"item": op.item})
        campo = "cat" if op.catalisado else "cru"
        if campo not in registro or delta > registro[campo][0]:
            registro[campo] = (delta, limiar, op.slot)

    saida = []
    for registro in melhor.values():
        if "cru" not in registro:
            continue
        d_cru, l_cru, slot = registro["cru"]
        d_cat, l_cat, _ = registro.get("cat", (None, None, None))
        saida.append(Avaliacao(registro["item"], d_cru, l_cru, d_cat, l_cat, slot))
    return saida
```

`Avaliacao`, `agrupar` e `ordenar` estão em `docs/referencia/masmorras.py` (validados);
acrescente o campo `slot: str` ao final de `Avaliacao`. Etiquetas:

| Etiqueta | Regra |
| :--- | :--- |
| `direto` | ganho cru acima do limiar |
| `catalisar` | ganho cru **não** passa; o catalisado passa |
| `ambos` | os dois passam e o catalisado supera o cru por mais que o limiar |
| `nao_serve` | nenhum passa |

Na tela, `ambos` aparece como "upgrade direto, e ainda melhor catalisado".

**6.3 Executar** — duas execuções, cada uma com base e candidatos no mesmo arquivo:

```python
from ..topgear.runner import criar_simulador, estilo_de_luta
from ..topgear.search import conjunto_do_personagem


def rodar_ranking(personagem, itens, *, cenario, ilvl, it_triagem=300, it_refino=3000,
                  threads=None, cancelar=None, orcamento_restante=None):
    base = conjunto_do_personagem(personagem)
    conjuntos, opcoes = montar_opcoes(base, itens, ilvl=ilvl, classe=personagem.classe)
    simular = criar_simulador(
        personagem, fight_style=estilo_de_luta(cenario), threads=threads,
        cancelar=cancelar, orcamento_restante=orcamento_restante,
    )
    triagem = avaliar(simular(conjuntos, it_triagem), opcoes)        # execução 1
    # Refina tudo que não perdeu claramente; o resto fica como "não serve".
    vivos = {a.item.item_id for a in triagem if a.ganho > -a.limiar_cru}
    nomes = [n for n, op in opcoes.items() if op.item.item_id in vivos]
    refino = avaliar(simular({n: conjuntos[n] for n in nomes}, it_refino),
                     {n: opcoes[n] for n in nomes})                   # execução 2
    refinados = {a.item.item_id for a in refino}
    return refino + [a for a in triagem if a.item.item_id not in refinados]
```

`criar_simulador` grava a base no mesmo arquivo de cada chamada, então cada `avaliar` usa
a base da sua própria execução (P4). Não use `_simular_em_chunks` aqui: com ~150
profilesets cabe num arquivo, e dividir em lotes reintroduz o A-03.

**6.4 Modelos de saída** (`modelos.py`) — contrato da API e da tela:

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from ..topgear.models import Cenario

Etiqueta = Literal["direto", "catalisar", "ambos", "nao_serve"]
PREMISSA_CHANCE = (
    "Chance = itens que servem ÷ itens que sua classe pode receber nesta masmorra. "
    "Supõe que cada item elegível tem a mesma chance de cair; o ganho de cada item é medido."
)


class ItemRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: int
    nome_pt: str | None = None
    nome_en: str | None = None
    slot: str
    ilvl: int
    etiqueta: Etiqueta
    delta_cru_pct: float
    delta_catalisado_pct: float | None = None
    limiar_pct: float
    icone: str | None = None
    stats: dict[str, int] | None = None
    aviso: str | None = None


class MasmorraRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    masmorra: str
    servem: int
    elegiveis: int
    chance_pct: float
    maior_pct: float
    direto: int
    catalisar: int
    explicacao: str
    itens: list[ItemRanking] = Field(default_factory=list)


class RankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    addon: str = Field(max_length=20_000)
    amr: str | None = Field(default=None, max_length=20_000)
    primario: Literal["simc", "amr"] = "simc"
    scenario: Cenario = "dungeon_slice"
    ilvl: Literal[321, 328, 334, 341] = 341
    iteracoes_triagem: int = Field(300, ge=50, le=5_000)
    iteracoes_refino: int = Field(3000, ge=200, le=50_000)
    orcamento_segundos: int = Field(900, ge=30, le=86_400)
    loadouts: list[str] = Field(default_factory=list)          # T9
    pesos_loadouts: dict[str, float] = Field(default_factory=dict)  # T9


class RankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_dps: float
    cenario: str
    ilvl: int
    iteracoes: int
    ordem_padrao: Literal["quantidade"] = "quantidade"
    masmorras: list[MasmorraRanking] = Field(default_factory=list)
    premissa_chance: str = PREMISSA_CHANCE
    avisos: list[str] = Field(default_factory=list)
```

`explicacao` (texto em PT-BR, gerado por função pura e testada): "2 itens são upgrade
direto. 5 servem para catalisar: valem pelo tier, não pelos atributos." — mesma lógica
da prévia publicada para o usuário.

**Testes** (`tests/test_masmorras_ranking.py`, simulador falso como em
`tests/test_topgear_search.py::simulador_falso`):
- etiqueta de cada um dos 4 casos (valores do protótipo: cru +2,4 → `direto`;
  cru +0,1 / cat +1,9 → `catalisar`; cru +1,2 / cat +2,6 → `ambos`; cru −0,3 → `nao_serve`);
- anel testado nos dois slots vira **uma** avaliação com o melhor;
- `ordenar(por="quantidade")` e `ordenar(por="maior")` dão as ordens da prévia
  (Altar das Presas 1º por quantidade; Murder Row 1º por maior item);
- delta calculado contra a base da própria leitura (duas leituras com bases diferentes
  não se misturam);
- `montar_opcoes` com `ilvl=999` levanta `ValueError`.

**Commit:** `feat(masmorras): ranking de masmorras com etiquetas direto/catalisar`

### T7 — API, worker e tela do ranking

**Backend** — copie o padrão do Droptimizer, trocando nomes:

| Copiar de | Para | Trocar |
| :--- | :--- | :--- |
| `web/drop_db.py` | `web/masmorras_db.py` | nome da tabela e do arquivo de banco |
| `web/drop_worker.py` | `web/masmorras_worker.py` | `processar` chama `rodar_ranking` + `agrupar` + `ordenar`; mantém pré-voo (sem DPS, T4), `registrar_inicio_job`/`registrar_fim_job`, guarda de exceção que nunca deixa job em `running` |
| `web/drop_api.py` | `web/masmorras_api.py` | prefixo `/api/masmorras`; rotas `POST ""`, `GET /{id}`, `POST /{id}/cancelar`, `GET /{id}/resultado`, `GET /estimativa` |
| `worker.enfileirar_drop` | `worker.enfileirar_masmorras` | mesmo corpo, chama `masmorras_worker.processar` |
| `web/app.py` | — | `app.include_router(masmorras_api.router)` **antes** de `montar_frontend(app)` |

A estimativa (`GET /estimativa`) conta `len(conjuntos)` de `montar_opcoes` vezes as
iterações e mostra os segundos antes de rodar. Ícone e stats de cada item: preencha com
`catalog.visual_item(item_id)` como em `droptimizer/search.py`.

**Frontend** (`Simulator-WoW/src/`):
- `services/masmorrasService.ts`: interfaces espelhando `RankingRequest`,
  `RankingResult`, `MasmorraRanking`, `ItemRanking` (campos idênticos, `| null` onde o
  Python tem `None`), funções `criarRanking`, `consultarRanking`, `resultadoRanking`,
  `cancelarRanking`, `estimativaRanking` (copie o estilo de `dropService.ts`).
- `components/MasmorrasPanel.tsx`: import SimC + AMR (mesmo bloco do Droptimizer),
  seletor de cenário e de ilvl, botão de estimativa, barra de progresso
  (`SimulationProgressBar`), e o resultado:
  - dois botões de ordem — "Mais itens que servem" / "Maior ganho de um item"
    (`aria-pressed`), ordenando **no cliente** pelos campos `servem` e `maior_pct`;
  - um cartão por masmorra: posição, nome, "N de M itens servem · chance X%", números
    `servem` e `maior item`, lista de itens com ícone (`iconeDoItem`), tooltip
    (`useItemTooltip().showTooltip`), barra proporcional ao %, o % e a etiqueta;
  - a frase `explicacao` no rodapé do cartão;
  - a `premissa_chance` visível abaixo da lista (P1);
  - 5 masmorras abertas; as demais recolhidas.
- Registrar a aba em `App.tsx`/`Navbar.tsx` na área "Simular".

**Aceite.** `tsc --noEmit` limpo; teste de API com o `TestClient` (padrão de
`tests/test_droptimizer_api.py`, isolando os três bancos da §1.7); no Windows, um ranking
real abre com as 8 masmorras e os percentuais.

**Commit:** `feat(masmorras): API, worker e tela do ranking de masmorras` (wow-sim) e
`feat(ui): painel de ranking de masmorras` (Simulator-WoW).

### T8 — Grande Cofre a partir do `.gv`

**Pré-requisito.** T2 (o `.gv` usa o mesmo formato da mochila: `appendItemsToExport`,
`AskMrRobot-Serializer.lua:1069-1078`; captura em `AskMrRobot/Export.lua:219`,
`scanGreatVault`).

**Precisa do usuário:** um export do AMR tirado **com o cofre cheio** (depois do reset,
antes de coletar). O fixture atual tem `.gv` vazio. Grave-o como
`fixtures/pyrogalth-amr-181-cofre.txt` e use-o nos testes.

**Código.** `src/wowsim/masmorras/cofre.py`:

```python
from ..data import catalog
from ..parser.amr import ImportAMR
from ..parser.amr_codec import decodificar_itens


def opcoes_do_cofre(importacao: ImportAMR) -> list[dict]:
    """Itens do Grande Cofre com slot e ilvl resolvidos pelo catálogo."""
    saida = []
    for it in decodificar_itens(importacao.gv):
        slots = catalog.slots_do_item(it.item_id)
        ilvl = next(
            (catalog.bonus_para_ilvl(b).ilvl for b in it.bonus_ids if catalog.bonus_para_ilvl(b).ilvl),
            None,
        )
        saida.append({"item_id": it.item_id, "slots": slots, "ilvl": ilvl,
                      "bonus_ids": list(it.bonus_ids)})
    return saida
```

As opções viram `Candidato` com os **bônus reais** do item (não `NIVEL_PARA_BONUS`) e
passam pelo mesmo `avaliar` do T6, com `fonte="cofre"`. Saída: as opções ordenadas pelo
ganho, com a etiqueta. Na tela, separar "ganho se você pegar" de "ganho se pegar e
catalisar" (são hipóteses: o item ainda não é seu).

**Commit:** `feat(cofre): ranking das opcoes do Grande Cofre a partir do .gv do AMR`

### T9 — Várias builds: matriz, média e montagem

**Fonte das builds.** `Personagem.loadouts` (`nome → import string`), lido do export do
SimC. No fixture: `raid maxroll`, `Diabolist Delves`, `m+ icy`, `delves icy`,
`Diabolist Single`, `single icy`. O AMR **não** serve: os talentos dele não viram import
string (P-012). Para outra spec, o usuário faz `/simc` naquela spec ou cola a string.

**Como trocar a build sem mexer no perfil base.** A base do arquivo usa os talentos
originais. Cada build recebe um profileset de referência `ref` (base com
`talentos=codigo`), e todos os candidatos daquela build levam o mesmo `talentos`. O delta
é contra `ref`, **na mesma leitura** (P4):

```python
def conjuntos_da_build(base, codigo, conjuntos):
    saida = {"ref": base.model_copy(update={"talentos": codigo})}
    for nome, conjunto in conjuntos.items():
        saida[nome] = conjunto.model_copy(update={"talentos": codigo})
    return saida

# avaliar(leitura, opcoes, referencia="ref")
```

`linhas_override` já emite `talents=<codigo>` quando `Conjunto.talentos` está preenchido.

**Cenário de cada build.** Pelo nome, com escolha do usuário prevalecendo:

```python
def cenario_da_build(nome: str) -> str:
    n = nome.lower()
    if any(p in n for p in ("single", "raid", "boss")):
        return "patchwerk"
    return "dungeon_slice"  # m+, delves e o resto
```

Medir a build "single icy" em M+ dá pesos e rankings sem sentido.

**Matriz e média.** Para cada item: um % por build. Média ponderada pelos pesos do
usuário (`pesos_loadouts`, somando 1). Marque **divergência** quando o item é ganho
numa build e perda em outra:

```python
def media_ponderada(deltas: dict[str, float], pesos: dict[str, float]) -> float:
    total = sum(pesos.get(b, 0.0) for b in deltas)
    if total <= 0:
        raise ValueError("Pesos das builds somam zero.")
    return sum(d * pesos.get(b, 0.0) for b, d in deltas.items()) / total


def divergente(deltas: dict[str, float], limiares: dict[str, float]) -> bool:
    return any(d > limiares[b] for b, d in deltas.items()) and any(
        d < -limiares[b] for b, d in deltas.items()
    )
```

**Conjunto completo por build.** Para cada slot, a melhor opção com etiqueta diferente de
`nao_serve` (ou o equipado); monte; `constraints.validar`; **uma execução de
confirmação** comparando `ref` com o conjunto montado, porque tier, dois berloques de uso
e embelezamentos só aparecem na combinação. Mostre o delta medido do conjunto. Não use
beam nem estágios.

**Custo.** Uma execução por build e por fase (triagem + refino). Mostre a estimativa
antes de rodar.

**Commit:** `feat(masmorras): comparacao por build com media ponderada e montagem`

#### T9 — Plano de execução (Claude, 2026-11-08, após a auditoria)

Auditoria em `docs/AUDITORIA-ENTREGAS-IA.md`; defeitos P-041 a P-046 em `PENDENCIAS.md` §11.

1. [ ] **P-041** — `Avaliacao` ganha `nome_cru`/`nome_cat` (profileset vencedor de cada
   versão); `melhores_por_slot` usa a versão de maior `ganho`. Teste: item `catalisar`
   entra catalisado.
2. [ ] **P-042** — escolha por slot físico: anel/berloque disputam os dois slots, sem
   repetir `item_id`; `montar_valido` tira a troca de menor ganho até
   `constraints.validar` aceitar (contexto com catalisador). Testes: dois anéis bons
   ocupam `finger1` e `finger2`; conjunto inválido perde a troca mais fraca.
3. [ ] **P-043** — `rodar_ranking_builds` em `masmorras/builds.py`: por build, triagem e
   refino com `ref` (P4, `referencia="ref"`), cenário da build (escolha do usuário em
   `cenarios_loadouts` prevalece), montagem e **uma execução de confirmação** `ref` ×
   `montado`. Matriz item × build com média ponderada e divergência. O ranking das
   masmorras no modo builds usa a média ponderada dos deltas e dos limiares (decisão:
   assim a contagem "servem" responde à pergunta "serve para o meu conjunto de builds").
4. [ ] Modelos: `BuildResultado`, `LinhaMatriz`; `RankingResult.builds`/`matriz`
   (vazios fora do modo builds). `conjunto_itens` guarda o conjunto montado completo
   (para a string do AMR).
5. [ ] API: `POST /api/masmorras/builds` (lê os loadouts do texto e sugere o cenário);
   estimativa multiplica pelo número de builds e aceita `modo` (fecha **P-045**).
6. [ ] Tela: seleção de builds com peso e cenário; matriz; cartão por build com o delta
   medido do conjunto ± limiar e as trocas.

### T10 — Validação ao vivo no Windows (usuário)

Roteiro em §8. Registre os números reais em `PENDENCIAS.md` (fecha P-031 e P-040).

---

## 6. Fase 3 — levar para o jogo

### T11 — String do Pawn

**Fonte do formato.** `AddOns/Pawn/Pawn.lua:3071` (`PawnParseScaleTag`):
`( Pawn: v1: "Nome": Stat=valor, ... )`. `Class` e `Spec` são **opcionais**; nome sem
aspas nem parênteses. O Pawn mostra várias escalas ao mesmo tempo no tooltip e só troca
sozinho ao mudar de **spec** (`Pawn.lua:164`, `PLAYER_SPECIALIZATION_CHANGED`), não ao
trocar de loadout.

**Código.** `src/wowsim/exportar/pawn.py` ← copie `docs/referencia/pawn.py` (já validado:
as strings geradas passam no porte do regex do Pawn, inclusive a "Mistura" sem spec, e
nome com aspas é recusado).

**Medição dos pesos** — em `data/pesos_medidos.py`, `derivar_pesos_medidos` ganha o
parâmetro `talentos: str | None = None` e passa
`extra_args=("calculate_scale_factors=1", *([f"talents={talentos}"] if talentos else []))`
(opção de linha de comando depois do perfil vale para o personagem). Exigências:
**≥ 5.000 iterações**, cenário da build (`cenario_da_build`), e gravar no arquivo de pesos
`iteracoes`, `fight_style`, `talentos` e o DPS médio da base — sem eles a escala não é
exportada.

**Normalização para misturar specs ou builds:** `pesos_relativos(scale_factors, dps)`
converte DPS por ponto em % do DPS por ponto antes da média; sem isso a build de DPS mais
alto domina a mistura.

**Builds quase iguais.** Se duas escalas diferirem menos que a margem de erro da
medição, diga "use uma só" em vez de exportar duas.

**Tela.** Uma escala por build/spec + "Mistura" com os pesos escolhidos; botão "Copiar"
por escala (`navigator.clipboard.writeText` com fallback para seleção do texto); texto
fixo: "O Pawn soma atributos e não enxerga bônus de tier, procs nem efeitos de berloque.
Use como primeira indicação."

**Commit:** `feat(exportar): string do Pawn por build e mistura ponderada`

#### T11 — Plano de execução (Claude, 2026-11-08)

1. [ ] **P-044** — `data/pesos_medidos.py::medir_escala(personagem, *, talentos,
   fight_style, iterations>=5000, ...)`: arquivo próprio por build (talentos na chave),
   `calculate_scale_factors=1` + `scale_only=Int,Crit,Haste,Mastery,Vers`; lê
   `players[0].scale_factors` (DPS por ponto, **crus**), `collected_data.dps.mean` e
   `mean_std_dev`, `scale_deltas`. Erro do fator ≈ `√2 · erro_dps / delta`
   (scale_factor_control.cpp, sem `center_scale_delta`). Não substitui os pesos curados
   da poda (A-12).
2. [ ] `exportar/pawn.py::escalas_das_builds(medicoes, pesos, classe, spec, nome)` →
   uma string por build + "Mistura"; `quase_iguais(a, b)` compara a diferença relativa
   com o erro somado (`2·√(e₁²+e₂²)`) e devolve "use uma só".
3. [ ] Worker: `medir_pesos` no pedido; resultado em `BuildResultado.pawn` e
   `RankingResult.pawn_mistura`.
4. [ ] Tela: botão Copiar por escala (clipboard com fallback de seleção) e o texto fixo
   sobre os limites do Pawn.

#### T12 — Plano de execução (Claude, 2026-11-08)

1. [ ] `POST /api/exportar/amr` `{modelo, build, itens}` → `linha_importacao` com
   `setup_id="WSIM-<build>"` saneado; erros de modelo viram 400.
2. [ ] Tela: campo único para colar o modelo (BiB do AMR), botão "Gerar string do AMR"
   por build, Copiar, aviso fixo sobre `_bib_` em várias linhas.

### T12 — String do AMR

**Fonte do formato.** `AddOns/AskMrRobot/Import.lua:305-460`. O addon:
- exige que a string comece com `$` e tenha **exatamente dois** `$`;
- valida versão mínima, **nome** e **nível** do personagem (raça e facção estão
  comentadas);
- lê talentos na posição 13, árvore heroica na 14 e itens a partir da 16 (1-based);
- trata como "BiB" (lista à parte) o setup cujo id **não** começa com `AMR`; um id que
  começa com `AMR` substitui o setup de mesmo id do usuário;
- com várias linhas e `_bib_` na primeira, **apaga os BiB importados antes**
  (`Import.lua:323`) — inclusive os que o próprio site do AMR gerou;
- acha os itens por semelhança (`Gear.lua:24`, `countItemDifferences`); o guid é
  opcional.

**Desenho.** O cabeçalho (identidade, spec, talentos, árvore, `.qN`) é **copiado** da
última string de Best in Bags que o AMR gerou para o usuário; o sistema troca só os itens
e o bloco de extras. Assim não há id de spec nem de árvore heroica a adivinhar.

**Código.** `src/wowsim/exportar/amr.py` ← funções `cabecalho_do_modelo`,
`linha_importacao` e `itens_da_linha` de `docs/referencia/amr_codec.py` (o codec em si já
estará em `parser/amr_codec.py` desde o T2; importe de lá). Validado com a string real do
usuário: ida e volta item a item igual; dois `$`; id começando com `AMR` e rótulo com
`;` recusados.

**Conversão Conjunto → ItemAmr.** `slot` pelo inverso de `SLOTS_AMR`; `bonus_ids`,
`gem_ids` (completar até 3 com 0), `enchant_id`; `catalyst_source` = `redirected_base_stats`;
`guid` quando o item veio do AMR (casamento exato no jogo). Tuning: `content_tuning` do
export do SimC.

**Bloco de encantamentos.** Opcional. Cada entrada tem **6 campos**
(`e\id\itemId\spellId\texto\materiais`), materiais pode ser vazio mas a barra final é
obrigatória: o `Import.lua` faz `gsub` no texto e quebra se o campo faltar.

**Comparação de teste.** A ordem das tags dentro do token pode diferir da do site do AMR
sem problema; o aceite compara **valores decodificados**, não bytes.

**Tela.** Botão "Gerar string do AMR" por build, campo para colar o modelo (BiB do AMR),
aviso fixo: "Importar com várias linhas apaga os Best in Bags importados antes, inclusive
os do site do AMR." Id do setup: `WSIM-<build>`.

**Aceite.** Teste de ida e volta; no jogo, `/amr` → importar → o setup aparece e aponta
os itens certos (feito pelo usuário).

**Commit:** `feat(exportar): string de importacao do AMR com o conjunto medido`

---

## 7. Fase 4 — acabamento

| Tarefa | O que fazer | Onde |
| :-: | :--- | :--- |
| **T13** (A-03) | Em `_simular_em_chunks`, guardar `base_dps`/`base_erro` **por lote** e calcular o delta de cada candidato contra a base do seu lote; ou devolver os resultados já em delta. Teste com simulador falso cujas bases diferem por lote. | `topgear/search.py:60` |
| **T14** (A-04) | `raid`, `mplus`, `cleave_aoe`, `delve_rooms` → todos `DungeonSlice`. Mostrar na tela quais são equivalentes, ou reduzir as opções. Não mudar o mapeamento sem decisão do usuário. | `topgear/runner.py:43`, `data/scenarios.ts` |
| **T15** (A-05, A-06) | Sanitizar o nome do `.simc` salvo como em `droptimizer/export.py::nome_do_arquivo`. Decidir com o usuário se `threads` sai da chave de cache. | `web/topgear_api.py`, `simc_runner.py:269` |
| **T16** (A-10) | Ler o bloco `@e\…` da string de BiB do AMR e gravar `dados/derivados/encantos_amr.json` (`enchant_id → item_id, spell_id, nome, materiais`). Fecha P-016 (Arte de Batalha Hash'ey `8730 → 283998 → 1315084`; Magilinha `7935 → 240133 → 1228974`). | novo script em `scripts/` |

---

## 8. Validação final no Windows (roteiro para o usuário)

1. `enviar_github.bat` antes de começar (ponto de retorno).
2. `cd wow-sim && .venv\Scripts\activate && pytest -q` — anotar o total.
3. `wowsim simc-check --forcar` — anotar DungeonSlice e Patchwerk (T1).
4. `iniciar.bat` → Droptimizer com o export do personagem → o ranking mostra ganhos em
   verde (não "empate" em tudo).
5. Ranking de masmorras (T7) com DungeonSlice e ilvl 341 → 8 masmorras, % por item,
   etiquetas, troca de ordem funcionando.
6. Top Gear com `--catalisador` (CLI) → o `.simc` gerado tem
   `redirected_base_stats=` e o bônus de conjunto aparece no relatório.
7. Pawn: colar a string no jogo (`/pawn` → Importar) → a escala aparece no tooltip.
8. AMR: colar a string no addon → o setup `WSIM-…` aparece e aponta os itens.

Registrar cada resultado em `PENDENCIAS.md`.

---

## 8B. Fase 6 — trilhas, brasões e embelezamentos (pedido de 2026-11-09)

> Pedido do usuário: escolher o nível pelo **nome** (Herói/Mítico + rank), saber **quantos brasões**
> custa upar o item que vem do bônus roll/Grande Cofre e, para itens **craftados/embelezados**, o custo
> de craft e o **nome + descrição** do embelezamento. Regra P1 vale aqui: número de brasão só de fonte
> verificada; o que não tiver fonte aparece rotulado "a confirmar".

### Fatos verificados (2026-11-09)

| Fato | Valor | Fonte |
| :--- | :--- | :--- |
| Escada de níveis | Herói 1/6–6/6 = 305, 308, 311, 315, 318, 321 · Mito 1/6–6/6 = 318, 321, 324, 328, 331, 334 | `dados/derivados/bonus_ilvl.json` (Raidbots `bonus-upgrade-sets`, bônus 12841–12846 e 12849–12854) = Method.gg |
| Forja do Veneno | Herói 6/6 + forja = 328 (12848) · Mito 6/6 + forja = 341 (12856) | `bonus_ilvl.json` |
| Custo de upgrade | **20 brasões da trilha por etapa** (Herói usa Hero Mistcrest, Mito usa Myth Mistcrest); de r/6 a 6/6 = `(6 − r) × 20` | Icy Veins, "These Five Mistcrests…" (S2) |
| Craft com Myth Mistcrest | Item sai em 318–331 conforme a qualidade | warcraft.wiki.gg/wiki/Myth_Mistcrest |
| Centelhas de Marés por craft | 2 (armadura/1 mão) · 4 (2 mãos) | warcraft.wiki.gg (Spark of Tides) = `craft_receitas_s2.json` |
| **Brasões por craft** | `craft_receitas_s2.json` diz **80** — **sem fonte primária**: mostrar como "a confirmar" até o usuário confirmar no jogo | — |
| Custo da Forja do Veneno | usa *Ascendant Venomstones*; quantidade **desconhecida** | Method.gg cita, sem número |
| Desconto de slot | existe no jogo; **não modelado** (o cálculo mostra o custo cheio) | — |

**Atenção:** `dados/guia_economia_brasoes_e_upgrades_s2.md` (escrito por IA) erra a escada (diz Herói
305–318, Mito 318–331) e mistura moedas. **Não usar como fonte de números**; a tabela acima prevalece.

### Tarefas

| # | Tarefa | Status | Commit |
| :-: | :--- | :-: | :-- |
| T17 | `data/trilhas.py`: escada (trilha, rank) ↔ bônus ↔ ilvl a partir de `bonus_ilvl.json`; `custo_upgrade(trilha, rank_de, rank_ate=6) -> {"moeda", "brasoes"}`; `trilha_do_item(bonus_ids)` | [x] | `c8d6570` |
| T18 | Ranking aceita **trilha + rank + forja** em vez de só `ilvl` (321/328/334/341 viram atalhos). `RankingRequest`: `trilha: "heroi"\|"mito"`, `rank: 1–6`, `forja: bool`; `ilvl` continua aceito (compatibilidade). `montar_opcoes` recebe o bônus | [x] | `c8d6570` |
| T19 | Custo de upgrade em cada item do resultado: `ItemRanking.trilha`, `rank`, `upgrade` (`{moeda, brasoes, ate: "6/6 (334)"}`); Grande Cofre usa os bônus reais do `.gv`; na tela, coluna "Para 6/6: 60 Mito" | [x] | `c8d6570` |
| T20 ✔ `f1c0a98` | Embelezamentos: `data/embellishments` ganha `descricao` (mover o texto de `Simulator-WoW/src/data/embellishments.ts` para `dados/derivados/embelezamentos.json` por script); item craftado mostra nome, descrição, "Único-equipado: Embelezado (2)" e o custo de craft (Centelhas + brasões "a confirmar") | [ ] | |
| T21 | Tela: seletor "Herói / Mítico" + "Rank 1/6…6/6" + "Forja do Veneno"; rótulo "Mito 4/6 · 328"; resumo do total de brasões das trocas sugeridas por build | [x] | `e91ae2d` (backend T17–T19 em `c8d6570`) |
| T22 | **Modo Craft** na tela de Masmorras (decisão do usuário 2026-11-09) — ver desenho abaixo | [x] | `f1c0a98` (backend), UI no Simulator-WoW; **falta validar no simc real (T10)**: conferir que `ilevel=331,crafted_stats=…,embellishment=…` não gera erro no log |

**Decisões do usuário (2026-11-09):** craft é uma 3ª opção da tela de Masmorras ("Masmorras M+ \| Grande
Cofre \| Craft"); **80 Brasões Míticos por craft está confirmado** (sem rótulo "a confirmar").

**Desenho do T22 (o simc mede tudo, inclusive o embelezamento):**
- simc aceita no item `ilevel=`, `crafted_stats=a/b` (missiva) e `embellishment=<nome tokenizado>`
  (`engine/item/item.cpp:844/855/871`, `item_t::decode_embellishment`); a tabela
  `engine/dbc/generated/embellishment_data.inc` tem os 27 de Midnight com o mesmo `nome_en` de
  `dados/craft_sistemas_s2.json` (Forro de Arcanotrama = "Arcanoweave Lining", bônus 12384).
- `scripts/derivar_embelezamentos.py` → `dados/derivados/embelezamentos.json`: reagente, nome PT/EN,
  token do simc, bônus, descrição PT, onde se aplica (armadura / acessório / arma / qualquer). Os de
  Engenharia e de armas de profissão específicas ficam de fora.
- `Candidato` ganha `ilevel`, `crafted_stats`, `embelezamento_simc`; `_linha_item` emite os três.
- `masmorras/craft.py`: (1) para cada item craftável do tipo de armadura (+ anéis/colar) e cada um dos 6
  pares de secundários (missivas Talassianas), um candidato Mítico Q5 = **331** → triagem/refino →
  melhor par por slot; (2) cada embelezamento aplicável é medido no melhor slot onde cabe, respeitando o
  teto de 2 efeitos (`constraints.validar`); (3) saída com custo: 80 Brasões Míticos + 2 Centelhas de
  Marés (4 em arma de 2 mãos) por item.
- Tela: "Craft" lista os slots (item, missiva, ganho, custo) e os embelezamentos (nome, descrição, ganho,
  "Único-equipado: Embelezado (2)").

**Aceite:** testes da escada (os 12 pares batem com `bonus_ilvl.json`), custo `(6 − r) × 20`, ilvl 318
ambíguo exige a trilha, request antigo com `ilvl=341` continua funcionando; tsc limpo; nenhum número de
brasão de craft sem o rótulo "a confirmar".

---

## 9. Desvios encontrados

*(Quem implementar: anote aqui toda divergência entre este documento e o código real,
com data, arquivo, o que o documento dizia e o que era de fato.)*

| Data | Tarefa | Documento dizia | Código real | O que foi feito |
| :--- | :-: | :--- | :--- | :--- |
| 2026-11-08 | T2 | Aceite: `grep "drop_level\|gem_id2" src/wowsim/parser` vazio | `parser/addon.py` (parser do export SimC, outro formato) e comentários explicativos mantêm esses nomes | Nenhum caminho do AMR os emite; registrado em `PENDENCIAS.md` (A-07). |
| 2026-11-08 | T9 | Montar com a melhor opção por slot | `melhores_por_slot` escolhia sempre a versão crua e um slot por item | P-041/P-042; corrigido no T9 (Claude). |
| 2026-11-08 | T11 | Medição com ≥ 5.000 iterações e talentos na chave | `derivar_pesos_medidos`: 200 iterações, chave sem talentos, só secundários normalizados | P-044; `medir_escala` nova, a antiga continua para a poda. |
| 2026-11-08 | geral | Repositório todo em CRLF | Arquivos criados no Windows ficam LF no blob (git com autocrlf) e CRLF no disco; o git do Linux sem autocrlf grava CRLF no blob | Para arquivos com blob LF use `git -c core.autocrlf=input add`; confira `git diff --stat` = `--ignore-cr-at-eol` antes de enviar. |

---

## 10. Glossário

| Termo | Significado aqui |
| :--- | :--- |
| profileset | Variação de um perfil base dentro do mesmo arquivo `.simc`; o simc mede base e variações na mesma execução. |
| `max_time` | Duração da luta simulada, em segundos. Não é limite de execução. |
| erro da média | `mean_error` (profileset) / `mean_std_dev` (base). Diz se uma diferença é real. |
| dispersão | `stddev` / `std_dev`. Variação entre lutas. **Não** é erro. |
| limiar | `max(0,15%, erro da base, erro do candidato)`. Abaixo disso é empate. |
| scale factor | DPS ganho por ponto de atributo, medido pelo simc com `calculate_scale_factors=1`. |
| diferença acumulada | Compressão do AMR: cada número é a diferença para o anterior da mesma seção. |
| gêmeo catalisado | Cópia de um candidato convertida na peça de tier, com `redirected_base_stats` = item de origem. |
| build / loadout | Árvore de talentos salva com nome no export do SimC. |
| BiB (AMR) | Setup "Best in Bags" importado no addon; id não começa com `AMR`. |
