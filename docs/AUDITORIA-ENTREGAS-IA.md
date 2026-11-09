# Auditoria das entregas da outra IA — 2026-11-08

Escopo: tudo o que entrou depois do workflow (`1a66ba7` no wow-sim, `bdb16a4` no
Simulator-WoW): 27 commits no backend e 3 na interface. Cada tarefa foi conferida
contra o critério de aceite de `docs/WORKFLOW-IMPLEMENTACAO.md`, as invariantes P1–P5 e
as proibições. Este doc é o registro; as pendências abertas daqui estão em
`PENDENCIAS.md` §11 (P-041 a P-046).

## 1. Verificações gerais

| Verificação | Resultado |
| :--- | :--- |
| Testes (`-m "not integration_simc"`) | **397 passaram**; 2 falhas + 1 desmarcado são as de ambiente já conhecidas (simc real ausente no Linux: `test_web_sim_api` integração ×2, `test_topgear_worker::test_excecao_generica_marca_erro`). O "400 passed" da outra IA bate (rodou no Windows). |
| `tsc --noEmit` | limpo |
| Fins de linha | `git diff --stat` e `--ignore-cr-at-eol` idênticos nos dois repos (50 arquivos +2812/−258; 5 arquivos +781/−27): nenhum CRLF corrompido |
| Árvore de trabalho | 0 pendentes nos dois repos; `__pycache__` ignorado; nada em `cache/`, `bin/`, `.env`, `wowsim.db` |
| `dados/*.json` e MANIFEST | só mudaram por script (`encantos_amr.json` gerado de BiB real) |

## 2. Conferência por tarefa

| Tarefa | Veredito | Observação |
| :-- | :-: | :--- |
| T1 max_time (A-01) | OK | `max_time` só entra quando pedido; não deriva do timeout; teste presente |
| T2 codec AMR (A-07) | OK | `_linha_item` sem `drop_level`/`gem_id2`/`crafting_quality` vindos do AMR (o parser do SimC ainda lê esses campos, correto) |
| T3 pesos (A-12) | OK | alias `Vers`; poda em `topgear/search.py:853` e `droptimizer/search.py:222` usa `pesos_para` (curado) |
| T4 pré-voo (A-02) | OK | os três workers só publicam a duração |
| T5/T6 masmorras | OK | P4 preservado: triagem e refino avaliados cada um contra a base da própria leitura; `premissa_chance` aparece na tela |
| T7 API/worker/tela | OK com ressalva | ver P-045 (estimativa ignora o modo cofre) |
| T8 Grande Cofre | OK | bônus reais do `.gv`, ilvl por item, tela separa ganho cru e catalisado |
| T9 núcleo | **Com defeitos** | P-041, P-042, P-043 |
| T11 medição de pesos | **Com defeitos** | P-044 |
| T12 biblioteca | OK | `itens_de_conjunto` cobre slot, bônus, gemas (3), encanto e catalisador |
| T13 base por lote (A-03) | OK | teste com bases diferentes por lote |
| T14 cenários (A-04) | OK | `normalizarCenario` mapeia valores antigos; o backend ainda aceita `raid` |
| T15 threads/nome (A-05/A-06) | OK | `threads` fora da chave de cache, ainda vai no comando |
| T16 encantos (A-10) | OK | `dados/derivados/encantos_amr.json`, P-016 fechada |

## 3. Defeitos encontrados

**P-041 — T9 monta o conjunto com a versão errada do item (ALTO).**
`masmorras/builds.py::melhores_por_slot` procura o primeiro profileset com o mesmo
`item_id` e slot. Como a versão crua é inserida antes da catalisada em `montar_opcoes`,
um item cuja etiqueta é `catalisar` (ou `ambos`, com o catalisado maior) entra no
conjunto **cru** — exatamente a peça que o ranking disse para catalisar. O teste atual não
cobre o caso. *Correção:* `Avaliacao` passa a guardar o nome do profileset vencedor
(`nome_cru`/`nome_cat`) e `melhores_por_slot` usa o vencedor de `ganho`.

**P-042 — T9 perde o segundo anel/berloque e não valida o conjunto (MÉDIO).**
Cada item fica com um único slot (o melhor). Dois anéis bons acabam ambos em `finger1` e
o segundo some; também nada impede o mesmo item nos dois slots nem dois berloques de uso.
O workflow manda `constraints.validar` antes da confirmação, e ele não é chamado.
*Correção:* escolher por slot físico considerando os dois lados (anel/berloque), sem
repetir `item_id`, e validar com `construir_contexto` + `contexto_com_catalisador`.

**P-043 — `loadouts`/`pesos_loadouts` aceitos e ignorados (MÉDIO).**
`RankingRequest` tem os campos, o serviço da tela também, mas o worker nunca os lê: o
usuário pede comparação por build e recebe o ranking comum sem aviso. *Correção:*
implementar o fluxo de builds no worker (é o que falta do T9).

**P-044 — Medição de pesos do Pawn mistura builds e descarta Intelecto (ALTO para T11).**
1. `chave_pesos` usa `talents_atual`, não o `talentos` passado: medir a build B grava em
   cima da build A (mesmo arquivo).
2. Padrão de 200 iterações e timeout de 120 s, abaixo dos ≥ 5.000 exigidos.
3. `normalizar_scale_factors` guarda só os 4 secundários com máximo = 1: some o
   Intelecto e some a escala em DPS, então `pesos_relativos` (% do DPS por ponto) não tem
   de onde sair e a "Mistura" fica errada.
*Correção:* função nova `medir_escala` que lê os scale factors **crus** (`Int`, `Crit`,
`Haste`, `Mastery`, `Vers`) de `players[0].scale_factors`, o DPS e o erro da base
(`collected_data.dps.mean_std_dev`) e os deltas (`scale_deltas`), com `scale_only` para
não medir atributos inúteis; `talentos` entra na chave. A poda continua usando só os
pesos curados (A-12).

**P-045 — Estimativa de custo ignora o modo cofre (BAIXO).**
`GET /api/masmorras/estimativa` conta as masmorras mesmo quando o pedido é do Grande
Cofre. *Correção:* parâmetro `modo` e, no cofre, contar as opções do `.gv`.

**P-046 — Telas do T9, T11 e T12 não existem (esperado).** É o que a própria IA listou
como faltando.

## 4. O que não é defeito

- O parser do SimC continuar lendo `drop_level`/`crafting_quality`: o veto do A-07 vale
  para o que vem do AMR.
- `rodar_ranking` juntar itens refinados com os que caíram na triagem: os que não foram
  refinados são, por construção, `nao_serve`.
- Valores antigos de cenário (`raid`, `cleave_aoe`) ainda aceitos pela API: é a
  compatibilidade pedida no T14.
