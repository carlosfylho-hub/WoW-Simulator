# ⚠️ AUDITORIA CONSOLIDADA — fonte canônica desta varredura

> **STATUS:** DOCUMENTO DESTACADO — leia este antes das auditorias antigas.
> **Data:** 2026-11-09
> **Escopo:** `wow-sim` + `Simulator-WoW` (Simulador WoW Midnight S2)
> **Regra:** erros já corrigidos ficam aqui com sintoma → causa → correção → evidência.
> Pendências abertas e o registro do que esta sessão fechou estão em [`PENDENCIAS.md`](../PENDENCIAS.md).

Os arquivos `AUDITORIA-3-CRAFT.md`, `AUDITORIA-3-EXECUCAO.md`, `AUDITORIA-ENTREGAS-IA.md`,
`PLANO-CONTINUIDADE.md` §6.A e `plans/auditoria-*.md` viram **histórico**. Se conflitar
com este documento, **este documento e o `PENDENCIAS.md` vencem**.

---

## 1. Estado do produto (agora)

| Área | Situação |
| :--- | :--- |
| SimC local (`12.1.5.70783`) | Binário e aceite Fase 1 ok |
| Import SimC + AMR + combinação | Codec por diferença (A-07); spec ativa (P-047) |
| Top Gear / Droptimizer | Limiar por `mean_error` (P-035); catalisador no motor (offline) |
| Ranking de masmorras / Cofre / Craft | Entregues; Craft A1–A7 fechados |
| Catalisador na UI / estimativa | **Fechado — P-032** (2026-11-09; falta validação ao vivo T10) |
| Craft Herói, armas, cargas, Forja | **Aberto — P-054** |
| Materiais / “onde usar” dos embelezamentos | **Parcial — P-055** (ícone/texto ok) |
| Validação no jogo (export vivo) | **Aberto — T10 / P-031 / P-040** (Windows + usuário) |

---

## 2. Erros já corrigidos (forma → correção)

### 2.1 Corretude numérica e cache

| ID | Sintoma | Causa | Como foi corrigido | Evidência |
| :--- | :--- | :--- | :--- | :--- |
| **A-01** | DPS Patchwerk mudava 2,4× entre rodadas | `timeout` virava `max_time` (duração da luta) | `max_time` constante; timeout só mata o processo | `tests/test_max_time_fight_length.py` |
| **A-03** | Deltas inflados/reduzidos em pools grandes | Base só do 1º lote | Cada lote usa a própria base; reescala para comparar | `tests/test_chunks_base.py` |
| **A-12** | Poda ignorava Vers e usava pesos ruins | Alias `Vers` ausente; pesos de luta curta | Alias + poda só com pesos curados | `tests/test_pesos_alias.py` |
| **P-035** | Ranking “empate” em tudo (+4% virava empate) | Limiar usava `std_dev` (dispersão) | Só `mean_error` / `mean_std_dev` | `tests/test_droptimizer_ranking.py` |
| **T13** | (mesmo A-03 no fluxo de chunks) | — | — | — |
| **P-034** | Peça já catalisada perdia stats base | `conjunto_do_personagem` omitia `redirected_base_stats` | Campo preservado + chave de dedupe | `tests/test_topgear_catalisador.py` |

### 2.2 Parser AMR e importação

| ID | Sintoma | Causa | Como foi corrigido | Evidência |
| :--- | :--- | :--- | :--- | :--- |
| **A-07** | 1/15 itens corretos; ids absurdos | Leitura absoluta onde o AMR usa diferença | Codec `amr_codec.py` + parser reescrito | `tests/test_amr_codec.py` 15/15 |
| **P-047** | Equipado da spec errada | Sempre lia `.q2` | Usa `spec_ativa` / ActiveSpec | `tests/test_amr_spec_ativa.py` |
| **T16 / P-016** | Hash'ey / Magilinha fora do mapa | Camadas não modeladas | Bloco `@e` do AMR → `encantos_amr.json` | `tests/test_encantos_amr.py` |

### 2.3 Craft e tooltips (Auditoria 3)

| ID | Sintoma | Causa | Como foi corrigido | Evidência |
| :--- | :--- | :--- | :--- | :--- |
| **P-049** | Ganhos inflados no Craft | Fase 1 media 3 embelezamentos (jogo limita 2) | Validar teto antes de simular; `bloqueados` | `tests/test_craft.py`; commits `9106017` / `3c9abc7` |
| **P-050** | “Nenhum embelezamento pôde ser medido” no teto | Só sabia *adicionar* | Mede *trocar* reagente ou peça embutida | `7d16755` / `dc74db1` |
| **P-051** | Tooltip sem attrs / “Drop M+” / slot cru | Craft fora do snapshot; fallback errado | Sonda no simc + fonte/slot PT-BR | `8f1baff`+`2af0f46` / `56e424d` |
| **P-052** | Não sabia quais embelezamentos já usa | Sem cruzamento `bonus_id` | `masmorras/embelezados.py` | `92ed854` |
| **P-053** | “.inv mesclado” em âmbar | Info promovida a aviso | Campo `informacoes` | `28004b9` / `ac731ba` |
| **P-048** | Tooltip inventava attrs; Aceleração sumia | Alias PT sem acento + inventário na UI | Mapa de stats + sem inventar (P1) | `07472b0` / `38873ff` |
| **A7/T10** | `embellishment=` nunca no simc real | Fase 2 nunca media | Script + log Windows | `4e26d5e` |

### 2.4 Ranking UI / Droptimizer / higiene

| ID | Sintoma | Causa | Como foi corrigido | Evidência |
| :--- | :--- | :--- | :--- | :--- |
| **P-036** | Download CSV/.simc sem efeito | WebView2 sem download manager | Backend grava em `saida/` e devolve caminho | drop/topgear API |
| **P-037** | Sem ícone/tooltip no Drop | Payload sem visual | `catalog.visual_item` no ranking | DroptimizerPanel |
| **P-038** | Item repetido (anel/trinket) | Dois slots → duas linhas | `_agrupar_equivalentes` | `test_droptimizer_ranking` |
| **A-02** | Pré-voo publicava DPS de 5 iter | Progresso com `dps` | Só `duracao_s` | workers |
| **A-04 / T14** | “Raid” = “M+” na prática | Vários rótulos → mesmo fight style | UI: M+ e Chefe; resto em “Mais” | `normalizarCenario` |
| **A-05 / A-06** | Nome `.simc` / cache por threads | Sem sanitizar; threads na chave | Sanitizar; threads fora da chave | testes dedicados |
| **Pós-merge P0–P2** | Upgrade descartava trilha melhor; jobs zumbi; etc. | Ver `plans/auditoria-pos-merge.md` | Aplicado (PENDENCIAS §8) | suíte droptimizer/combinar |

### 2.5 Builds / Pawn / Cofre (P-041…P-046)

Fechados em 2026-11-08 (`551f15b`, `32b9888`, `03221d7` + UI): profileset vencedor ao catalisar, anel/berloque sem perder slot, `loadouts` no worker, pesos Pawn com talentos, estimativa do modo cofre, telas T9/T11/T12. Detalhe em `PENDENCIAS.md` §11.

---

## 3. Aberto agora (ordem desta sessão)

1. ~~**P-032** — Catalisador na estimativa + checkbox/cargas no Top Gear.~~ **Fechado em 2026-11-09.**
2. **P-054** — Craft Herói (305–318), armas, cargas do Catalisador nas sugestões, brasões/Forja (só com fonte; senão “desconhecido”).
3. **P-055** — Materiais da receita e “onde usar” via Crawl4AI → `embelezamentos.json`.
4. **T10 / P-031 / P-040** — Validação ao vivo no Windows (export do usuário); fora do código automático.
5. **U0–U7** — Redesign UI (`Simulator-WoW/docs/PLANO-REDESIGN-UI.md`); fora desta rodada de correção.

---

## 4. Como continuar (IA / humano)

1. Abrir este arquivo + `PENDENCIAS.md`.
2. Não reabrir A1–A7 / P-049…P-053 — já entregues (`AUDITORIA-3-EXECUCAO.md`).
3. Uma pendência por vez; teste que falha antes da correção; atualizar `PENDENCIAS` ao fechar.
4. P1: só o SimC produz DPS; P2: não inventar dado de jogo; CRLF preservado.

---

## 5. Índice do histórico (não editar como plano vivo)

| Documento | Papel agora |
| :--- | :--- |
| [`AUDITORIA-3-CRAFT.md`](AUDITORIA-3-CRAFT.md) | Diagnóstico original Craft (checklist desatualizado) |
| [`AUDITORIA-3-EXECUCAO.md`](AUDITORIA-3-EXECUCAO.md) | Log de commits A1–A8 |
| [`AUDITORIA-ENTREGAS-IA.md`](AUDITORIA-ENTREGAS-IA.md) | Auditoria pós-workflow |
| [`PLANO-CONTINUIDADE.md`](PLANO-CONTINUIDADE.md) | Visão + A-01…A-14 (muitos já corrigidos) |
| [`WORKFLOW-IMPLEMENTACAO.md`](WORKFLOW-IMPLEMENTACAO.md) | Como implementar; checklist sincronizado |
| `plans/auditoria-*.md` | Auditorias antigas (histórico) |
