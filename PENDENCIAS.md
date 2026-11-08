# Pendências — WoW Calculator Sim

**Última atualização:** 2026-11-08
**Fase atual:** Catalisador entregue (offline); Great Vault e talentos AMR pendentes
**Regra:** toda pendência tem identificador, impacto e condição de fechamento. Pendência sem condição de fechamento não entra.

---

## 1. Bloqueantes

Nenhum bloqueio ativo. O binário foi compilado a partir do fonte `12.1.5.70783` e o aceite da Fase 1 foi cumprido.

---

## 2. Resolvidas nesta rodada

### P-001 — Fixture real do Pyrogalth

| Campo | Detalhe |
| :--- | :--- |
| **Situação** | **Recebido do usuário em 2026-11-06.** Export completo colado na conversa, com checksum `70553fc1`. |
| **O que contém** | 6 loadouts salvos, 16 linhas de slot incluindo tabardo, sem `off_hand`, 5 itens na mochila, 17 marcas de ilvl, 5 moedas de Catalisador, 14 entradas de moedas de upgrade. |
| **Ação restante** | **Concluída.** Texto gravado byte a byte em `fixtures/pyrogalth.simc` (97 linhas, idêntico ao bloco de transcrição). |
| **Impacto** | Desbloqueou o golden test da Fase 2 e o `simc-check`; ambos já exercitados com o binário real. |

### P-002 — Binário do simc — **RESOLVIDA em 2026-11-06**

| Campo | Detalhe |
| :--- | :--- |
| **Situação** | O usuário forneceu o **código-fonte** da branch `midnight` em `../simc-midnight`, cujo `client_data_version.inc` declara `CLIENT_DATA_WOW_VERSION "12.1.5.70783"`. |
| **Toolchain** | Instalados via winget: CMake `4.4.4`, Ninja `1.13.2` e VS Build Tools `17.14.44` com carga C++ (MSVC `19.44.35229`). |
| **Build** | `cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_GUI=OFF -DSC_NO_NETWORKING=ON`, alvo `simc`, 19 jobs, 178 passos. |
| **Binário** | `bin/simc.exe`, 121 MB, ignorado pelo Git. `simc-info` reporta versão `1210-01`, build `12.1.5.70783`, situação **compatível**. |
| **Aceite** | 1000 iterações: DungeonSlice **255.601 DPS** (+0,63%) e Patchwerk **199.485 DPS** (−2,21%), ambos dentro de ±3%. |
| **Receita reproduzível** | `scripts/build_simc.ps1 -SourceDir ..\..\simc-midnight` importa o `vcvars64.bat`, configura, compila e copia para `bin/`. |

### P-016 — Poda heurística (Caminho A) — **ENTREGUE em 2026-11-08**

| Campo | Detalhe |
| :--- | :--- |
| **O que** | Pontuação heurística (`heuristic/score.py`, `dados/pesos_secundarios.json`) e poda top-K no Top Gear e no Droptimizer, com modo `verificar_podados`. |
| **Regra** | O score nunca é DPS; o SimC continua sendo a única fonte de número (P1). |
| **Benchmark** | Poda top-6 no perfil do fixture: **180 → 114** profilesets marginais (−36,7%) em 2026-11-08. Pesos medidos validados no SimC real (Demonology: crit 1,0 / mastery 0,905 / haste 0,671). |
| **Pendente** | Nenhum. |
| **Impacto** | Reduz o número de profilesets por rodada e entrega a estimativa instantânea (diferencial frente ao Raidbots). |

---

## 3. Pendências de dados

### P-003 — Natureza de `omnium_talents` e seleção de runas — **RESOLVIDA em 2026-11-06**

| Campo | Detalhe |
| :--- | :--- |
| **Evidência do export** | `136814:1/136815:1/136817:1/136819:1/136822:1`, um ID por linha. Pela tabela do prompt: `5A-4A-3A-2B-1A`, ou seja, `1A-2B-3A-4A-5A`. |
| **Evidência do Raidbots** | [`omnium-talents.json`](https://www.raidbots.com/static/data/live/omnium-talents.json) mostra o nó `110271` com três **entradas de escolha**: `136814` Rune of Overload, `136824` Rune of Residual Energy e `136826` Rune of Echoes. Os IDs `1368xx` são escolhas, não nós de desbloqueio. |
| **Conclusão** | `omnium_talents` carrega a seleção. A seleção do fixture é `1A-2B-3A-4A-5A`. A afirmação de [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:529) está errada para este build, e [`pendencias.md`](../../WoW%20Calculator/pendencias.md:264) registra `C14` por erro de leitura de `136824` em vez de `136814`. |
| **Ressalva** | A ligação entre entrada `1368xx` e nome PT-BR depende do `spellId` de [`rune_ids_s2.json`](../../WoW%20Calculator/rune_ids_s2.json:47); a tabela do Raidbots é de build `12.1.5.70688`. |
| **Ação da Fase 3** | `data/omnium_map.py` resolve as 13 entradas por `spellId` e falha explicitamente se um ID do export não existir na árvore. |
| **Detalhe completo** | [`docs/RAIDBOTS-REFERENCIA.md`](docs/RAIDBOTS-REFERENCIA.md). |

### P-004 — ilvl por rank de trilha — **RESOLVIDA em 2026-11-06**

O projeto confirma Herói 6/6 = 321, Mítico 6/6 = 334, forjados 328 e 341 e cantrip 344. O Raidbots publica [`bonus-upgrade-sets.json`](https://www.raidbots.com/static/data/live/bonus-upgrade-sets.json) com os grupos 614 a 618, um por trilha. O script `scripts/derivar_bonus_ilvl.py` extrai os 30 ranks e valida seis âncoras: 12817 = 266, 12849 = 318, 12846 = 321, 12854 = 334, 12848 = 328 e 12856 = 341. Todas passaram. A tabela está em `dados/derivados/bonus_ilvl.json`, com `wow_build=12.1.5.70688` e `content_hash`, e `catalog.bonus_para_ilvl` a consome com `fonte=raidbots:bonus-upgrade-sets`. O 318 do prompt para Mítico 1/6 foi confirmado.

### P-005 — `slot_high_watermarks` com índices não identificados

17 entradas sem ordenação conhecida; só o índice 14 tem leitura autorizada (`259` contra teto `305`), e o export confirma esse par. Os demais saem como `informativo`. Fecha com três exports de composições de slot diferentes.

### P-006 — Nomes PT-BR fora do catálogo

Itens presentes no banco do simc mas ausentes de `stats_oficiais_itens.json` e das fichas. `catalog.nome_item` devolve `nome_en` do `item_data.inc` e marca `nome_pt=null` com "PT a confirmar". Tradução de cabeça é proibida. Fecha com inclusão do item em arquivo auditado.

### P-007 — Nome do encantamento de torso

O prompt alerta para a disputa Marca do Magíster × Marca da Alma do Mundo. O export traz `enchant_id=7987`, que [`enchant_ids_s2.json`](../../WoW%20Calculator/enchant_ids_s2.json:299) resolve como `Enchant Chest - Mark of the Worldsoul`. O nome PT-BR e o `item_id` saem do arquivo, nunca do prompt. Fecha com conferência do tooltip PT-BR do torso.

### P-008 — Erratas do Códice Corrosivo

O prompt aponta erros de nome e remete a `pendencias.md` seção `3.16-A`, que **não existe** no arquivo atual. Códice não entra em cálculo nem em variação; aparece apenas na seção Limites. Fecha com lista oficial dos 12 poderes conferida no tooltip.

### P-009 — Arquivo de Delve com metadado incorreto

[`delve_loot_kindojan.json`](../../WoW%20Calculator/delve_loot_kindojan.json:2) se declara "Banco de Dados M+", mas o conteúdo é de Delve. Ignorar `_meta.nome`; ler `labyrinth_kindojan_delves` e o conjunto Pisa-piras. Fecha com correção no repositório de dados.

### P-010 — Divergência de Folio em guia de Delve

[`guia_masmorras_e_delves_s2.md`](../../WoW%20Calculator/guia_masmorras_e_delves_s2.md:261) recomenda `C23`; [`pendencias.md`](../../WoW%20Calculator/pendencias.md:235) afirma correção para `C29`. Recomendação de código vem da matriz de `consumiveis_e_sistemas_s2.md`. Fecha com revisão do guia.

### P-020 — Expectativa de berloques do prompt não se confirmou no simc

| Campo | Detalhe |
| :--- | :--- |
| **O que o prompt supõe** | Trocar Dazar mais Ampola por qualquer outro berloque piora. |
| **O que o simc mediu** | Em 500 iterações, DungeonSlice, alguns candidatos de 341 melhoram **um** dos slots: `270167` +2,14%, `270170` +1,98%, `250214` +1,90%, `270164` +1,25% e `250224` +0,99%. |
| **O que não foi testado** | Trocar os dois berloques ao mesmo tempo. A regra R4 também impede avaliar dois on-use como independentes. |
| **Decisão** | Vale o simc. O relatório reporta os números medidos e marca empate por erro; a expectativa do prompt fica registrada como não sustentada. |
| **Ressalva** | Candidatos vêm de `monitor_upgrades_s2.json` no nível alvo; bônus forjado só é aplicado quando o monitor marca Peçonha. Item fora desse conjunto não entra. |

### P-016 — Camadas de aprimoramento que não são encantamento clássico

| Campo | Detalhe |
| :--- | :--- |
| **Evidência** | O export traz `hands=,enchant_id=8730` e `legs=,enchant_id=7935`. |
| **8730** | No DB2 bruto ([`dados_enchant_ids.csv`](../../WoW%20Calculator/dados_enchant_ids.csv:4708)) aparece como `Ancient Hash'ey Battle Art: Eye of the Lynx`, spell `1315099`. É **Arte de Batalha Hash'ey**, não encantamento de mãos. |
| **7935** | No DB2 bruto ([`dados_enchant_ids.csv`](../../WoW%20Calculator/dados_enchant_ids.csv:4461)) aparece como `+k1 Intellect & +k2 Stamina` Tier 2, spell `1229450`. É **Magilinha** de pernas, fora do mapa de 97 IDs, como já registrado em [`pendencias.md`](../../WoW%20Calculator/pendencias.md:181). |
| **Impacto** | Se o gerador tratar esses IDs como encantamento comum, gera variação inválida ou remove a camada errada. |
| **Mitigação** | Modelar três camadas por slot: encantamento permanente, arte de batalha ou tinker, e Magilinha ou Kit. `data/enchants.py` classifica o ID e devolve a camada. |
| **Fecha com** | Mapa explícito das Artes de Batalha Hash'ey e das Magilinhas, com `item_id` e tier, e teste que impede trocar camada de tipo diferente. |

### P-017 — Erratas no documento de importação

| Campo | Documentação | Export real | Ação |
| :--- | :--- | :--- | :--- |
| D1 | 7 loadouts em [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:720) | 6 loadouts | usar 6; registrar errata no projeto de dados |
| D2 | runa `136824` em [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:683) | `136814` | usar o export |
| D3 | addon `12.1.5-03` | `12.1.5-04` | parser aceita os dois; comparar só o build `70783` |
| D4 | mãos sem encantamento | `enchant_id=8730` | ver P-016 |
| D5 | pernas usam Magilinha fora do DB2 | `enchant_id=7935` | ver P-016 |

---

## 4. Pendências de engenharia

### P-011 — Schema do JSON do simc — **RESOLVIDA parcialmente em 2026-11-06**

A primeira execução real confirmou o schema do build `12.1.5.70783`:

- topo: `version`, `report_version`, `build_date`, `build_time`, `timestamp`, `git_revision`, `git_branch`, `sim`, `logs`;
- `sim`: `options`, `overrides`, `players`, `statistics`;
- `players[0].collected_data.dps`: `sum`, `count`, `mean`, `min`, `max`, `median`, `variance`, `std_dev`, `mean_variance`, `mean_std_dev`;
- **`sim.profilesets` é uma lista**, não um dicionário com `results`. O adaptador agora aceita as duas formas e há teste para a forma em lista.

Resta confirmar os campos internos de uma entrada de profileset quando houver variação simulada; isso fecha na Fase 4.

### P-012 — Comparação de talentos por arquétipo

Import string não é decodificada. Variações de talento usam apenas loadouts nomeados do addon ou códigos de `talent_builds_season2.json`. Fora de escopo decodificar nó.

### P-013 — Berloques on-use e regra R4

O SimC simula o berloque isoladamente, mas a recarga compartilhada é regra de jogo. O gerador marca par on-use mais on-use como `nao_simulavel`. O export atual tem `273649` e `273796`, ambos ativos, o que é exatamente o caso de conflito. Fecha com teste de regra no gerador.

### P-014 — APL do Ceifador de Almas

Loadouts de Soul Harvester podem rodar abaixo do real. Relatório inclui aviso fixo na categoria de talentos. Fecha com atualização do APL no repositório do simc.

### P-021 — Resumo DeepSeek validado apenas com cliente falso

A validação numérica foi testada com cliente fake: texto com número do contexto passa, número inventado é descartado e o fallback determinístico entra. **Nenhuma chamada real ao DeepSeek foi feita**, porque não há `DEEPSEEK_API_KEY` configurada. Fecha com uma execução real e revisão do texto gerado.

### P-015 — Versão do addon e build do cliente

`12.1.5-04` no export e `12.1.5.70783` no cliente. `check_version` compara o build numérico e avisa quando divergir; não bloqueia, mas o relatório marca `build_divergente=true`.

---

## 5. Verificação externa — 2026-11-07

Detalhes, método e evidências em [`docs/VERIFICACAO-EXTERNA.md`](docs/VERIFICACAO-EXTERNA.md).

| # | Assunto | Situação | Ação |
| :-: | :--- | :--- | :--- |
| P-022 | Abismo Peçonhento: snapshot diz 9 chefes | **REFUTADO** — Wowhead lista 8, final Ula'tek; Kith'ix é raid de um chefe no 12.1.5 | Corrigir o projeto de dados; o código não usa `num_bosses` |
| P-023 | 12.1.5 rotulado como *A Maldição de Ula'tek* | **REFUTADO** — 12.1 é *The Curse of Ula'tek*; 12.1.5 é *The Promise of Tomorrow* | Rótulos corrigidos no README, arquitetura e fontes |
| P-024 | Temporada 2 tratada como lançamento do 12.1.5 | **REFUTADO** — 12.1.5 é atualização de meio de temporada, com Keystone Myth | Não usar 12.1.5 como início da temporada |
| P-025 | Versão interna do SimC `1210-01` | **ESCLARECIDO** — é versão do SimC, não do cliente; o build `12.1.5.70783` é a âncora | `simc-info` compara o build do cliente |
| P-026 | Limite de 2 embelezamentos | **INDETERMINADO** nesta rodada | Manter evidência atual e não ampliar a afirmação |
| P-027 | Códice Corrosivo e pool de masmorras | **INDETERMINADO** nesta rodada | Não usar em cálculo; declarar limite |
| P-028 | APL do Ceifador de Almas | **INDETERMINADO** | Manter o aviso como precaução, não como fato |

### O que foi confirmado

- Build live `12.1.5.70783` no endpoint da Blizzard.
- SimC `midnight` com `client_data_version.inc` em `12.1.5.70783`; commit `c20e2ad` `[live] Build 70783`.
- 42 itens e 13 runas sem divergência de nome; ilvl igual onde o projeto declara referência.
- Seis faixas de `bonus_id` conferidas no Wowhead: 266, 282, 318, 321, 334 e 341.
- Catalisador preserva secundários e cantrip desde o 12.1.

---

## 6. Registro de decisões que fecharam pendências

| Data | Pendência | Resolução |
| :--- | :--- | :--- |
| 2026-11-06 | Estratégia de dados | Snapshot versionado em `wow-sim/dados/` com `MANIFEST.json`, override por `WOWSIM_DADOS` |
| 2026-11-06 | Resolução de `enchant_id` | `enchant_ids_s2.json` como primário; `.inc` do simc como verificação |
| 2026-11-06 | Empate técnico | Piso de 0,15% e uso do maior erro disponível |
| 2026-11-06 | Fixture do Pyrogalth | Export recebido com checksum `70553fc1`; falta gravar em `fixtures/pyrogalth.simc` |
| 2026-11-06 | Seleção de runas do fixture | `1A-2B-3A-4A-5A` pelos IDs `136814/136815/136817/136819/136822`, confiança média |
| 2026-11-07 | Build do cliente e do SimC | Blizzard confirma `12.1.5.70783`; SimC `midnight` tem dados desse build |
| 2026-11-07 | Nomes e ilvl dos itens | 42 itens no Wowhead sem divergência |
| 2026-11-07 | Runas do Folio | 13 nomes iguais no tooltip de feitiço |
| 2026-11-07 | Faixas de upgrade | 6 casos de `bonus_id` iguais no Wowhead |
| 2026-11-07 | Catalisador | confirmado que preserva secundários e cantrip desde o 12.1 |
| 2026-11-08 | Import AskMrRobot (v181) | Parser `parser/amr.py`, detecção em `parse_texto`, `POST /api/import/amr` |
| 2026-11-08 | Enumeração AMR de specs/raças | Mapa autoritativo extraído do addon (`scripts/extrair_mapa_addon_amr.py` → `dados/amr_mapa.json`) |
| 2026-11-08 | Slot de item do `.inv` AMR | Resolvido offline via `InventoryType` de `item_data.inc` (`catalog.slots_do_item`) |
| 2026-11-08 | Droptimizer (upgrade/best/worst in bags) | `droptimizer/*` + `web/drop_*` + aba UI; tudo medido pelo SimC |

---

## 7. Suporte AMR + Droptimizer — entrega 2026-11-08

Implementa o [`plans/adr-002-suporte-amr.md`](../plans/adr-002-suporte-amr.md) (Fases 1–8).

**Entregue:**
- Parser puro do export AMR v181 (`wowsim/parser/amr.py`) com fixture real `fixtures/pyrogalth-amr-181.txt`.
- `parse_texto` roteia automaticamente exports AMR (prefixo `$`); `Personagem.raca` populado pelo mapa.
- Mapa autoritativo (40 specs, 26 raças, facções, slots) do addon `AskMrRobot-Serializer.lua`.
- Droptimizer com 3 modos (`upgrade`, `best_in_bags`, `worst_in_bags`) — ranking single-slot medido, limiar por erro e chunking reutilizados do Top Gear.
- Possuídos de duas fontes: `Gear from Bags` (SimC) e `.inv` AMR (resolvido por `InventoryType`), deduplicados com proveniência.
- API `/api/droptimizer` (criar/consultar/resultado/cancelar/listar) + worker com guarda de exceção (nunca deixa job zumbi).
- UI: aba **Droptimizer** (`DroptimizerPanel`) com import AMR/SimC, seletor de modo, tabela de ranking e export CSV.

**Limitações conhecidas (não bloqueiam):**
- Talentos AMR não são convertidos para import string do SimC; mantém-se o loadout atual e emite aviso (`amr_talentos_nao_convertidos`).
- `slot_high_watermarks` do AMR (índices como `P-005`) seguem `informativo`; não usados no ranking.
- Best in Slot continua no Top Gear existente (`/api/topgear`), sem mudança de contrato.

### P-029 — Combinação de exports (SimC + AMR) — **ENTREGUE em 2026-11-08**

| Campo | Detalhe |
| :--- | :--- |
| **Motivação** | Cada formato tem dados exclusivos; juntos se complementam (SimC: talentos/omnium/bolsas; AMR: raça, `.inv`, `.hlv`, tuning de item). |
| **Implementação** | [`parser/combinar.py`](src/wowsim/parser/combinar.py): `combinar_textos`/`mesclar_personagens` com `primario = simc \| amr`. |
| **Política** | Equipado+talentos do primário; talentos sempre do SimC; metadados AMR enriquecem item só quando é o mesmo item; bolsas = união deduplicada; conflitos agregados em um aviso. |
| **API** | `POST /api/import/combinar`; `DropRequest`/`TopGearRequest` aceitam `amr?` + `primario`. |
| **UI** | Campo **AskMrRobot (opcional)** + seletor de **primário** no Droptimizer e no Top Gear; persistido em `localStorage`. |
| **Fechamento** | Testes `tests/test_combinar.py` + endpoint em `tests/test_web_api.py`; suíte verde. Limite: talentos AMR seguem não convertidos. |

---

## 8. Auditoria pós-merge — correções 2026-11-08

Revisão de [`plans/auditoria-pos-merge.md`](../plans/auditoria-pos-merge.md). Todos os P0/P1 aplicados; P2/P3 conforme abaixo.

| ID | Correção | Local |
| :--- | :--- | :--- |
| **P0-01** | Find Upgrade compara por `(slot, item_id, ilvl/bônus)`; mesmo `item_id` com trilha superior deixa de ser descartado. | [`drop_worker.py`](src/wowsim/web/drop_worker.py) |
| **P0-02** | `best_in_bags` monta o conjunto final (guloso + beam) e devolve `conjunto`/`conjunto_dps`/`delta_conjunto_pct`; `worst_in_bags` não soma perdas. | [`droptimizer/search.py`](src/wowsim/droptimizer/search.py) |
| **P0-03** | Worker legado ganhou `except Exception` final; nenhuma exceção inesperada deixa job em `running`. | [`web/worker.py`](src/wowsim/web/worker.py) |
| **P1-01** | Dois AMR distintos no mesmo request são rejeitados; `fontes` sem duplicata. | [`parser/combinar.py`](src/wowsim/parser/combinar.py) |
| **P1-02** | `addon`/`amr` limitados a 20 000 caracteres (`DropRequest`, `TopGearRequest`, `CombinarRequest`) → 422. | modelos + [`web/app.py`](src/wowsim/web/app.py) |
| **P1-03** | Possuídos deixam de incluir itens iguais ao equipado; possuídos distintos não-equipados. | [`drop_worker.py`](src/wowsim/web/drop_worker.py) |
| **P1-04** | `primario="amr"` sem export AMR → 422 no backend; rádio AMR desabilitado na UI sem string. | modelos + painéis |
| **P1-05** | `.simc` combinado regenerado por `serializar_texto` a partir do modelo mesclado; limitações documentadas em aviso. | [`parser/combinar.py`](src/wowsim/parser/combinar.py) |
| **P2-01** | AMR compartilhado entre abas via evento (`assinarAmrLocal`) + evento `storage`. | [`amrStorage.ts`](../Simulator-WoW/src/services/amrStorage.ts) |
| **P2-02** | Botão **Validar combinação** nos painéis Droptimizer e Top Gear (usa `/api/import/combinar`). | painéis + [`combinarService.ts`](../Simulator-WoW/src/services/combinarService.ts) |
| **P2-03** | Tokens do `.inv` sem slot são contabilizados (`inv_ignorados`) e avisados (`amr_inv_ignorado`). | [`droptimizer/pools.py`](src/wowsim/droptimizer/pools.py) |
| **P2-04** | `pool_por_slot` exposto no `DropRequest` e usado no modo upgrade. | [`droptimizer/models.py`](src/wowsim/droptimizer/models.py) |
| **P2-05** | Removidos `type: ignore` frouxos em `_eh_amr` e `_veredito`. | [`combinar.py`](src/wowsim/parser/combinar.py), [`search.py`](src/wowsim/droptimizer/search.py) |
| **P2-06** | `bonus_roll_items` incluído no merge de campos escalares. | [`parser/combinar.py`](src/wowsim/parser/combinar.py) |
| **P3-03** | ADR-002 §5 sincronizado com a montagem de conjunto e o filtro de upgrade. | [`adr-002-suporte-amr.md`](../plans/adr-002-suporte-amr.md) |
| **P3-02** | Aviso `amr_inv_inventario` do `.inv` já alinhado à combinação de exports (sem comentários obsoletos). | [`parser/amr.py`](src/wowsim/parser/amr.py) |

**Testes adicionados:** P0-01, P0-02, P0-03, P1-01, P1-02, P1-03, P1-04, P1-05 e P2-03 (cobertos em `tests/test_droptimizer.py`, `tests/test_combinar.py`, `tests/test_web_importacao.py` e `tests/test_web_worker_error.py`).

---

## 9. Catalisador — entrega 2026-11-08

Implementa o primeiro item do [`docs/PLANO-CONTINUIDADE.md`](docs/PLANO-CONTINUIDADE.md):
converter item de slot de tier na peça de tier da classe para ganhar o bônus de 2/4 peças.

### P-030 — Catalisador no Top Gear — **ENTREGUE em 2026-11-08 (offline)**

| Campo | Detalhe |
| :--- | :--- |
| **Motivação** | Nem o Raidbots nem o AMR consideram o Catalisador. A regra da S2 torna **todo** drop de cabeça, ombros, torso, mãos ou pernas um drop potencial de tier. |
| **Regra aplicada** | Preserva trilha, nível de aprimoramento e stats base (`dados/season2_context.json`). No SimC: peça de tier + `redirected_base_stats=<item de origem>`. |
| **Evidência na fonte** | `redirected_base_stats` é opção de item em [`item.cpp:875`](../simc-midnight/engine/item/item.cpp) e entra como `redirect_item` em [`sc_item_data.cpp:1076`](../simc-midnight/engine/dbc/sc_item_data.cpp). O bônus de conjunto vem do `id_set`, calculado pelo SimC. |
| **Dados** | [`scripts/derivar_tier_sets.py`](scripts/derivar_tier_sets.py:1) → `dados/derivados/tier_sets.json`: **13 classes**, conjuntos 2055–2067. Warlock = 2066 (271546/271544/271549/271547/271545), idêntico ao fixture do Pyrogalth. |
| **Implementação** | [`data/tier.py`](src/wowsim/data/tier.py:1) (leitor), [`topgear/catalisador.py`](src/wowsim/topgear/catalisador.py:1) (gêmeos + pacotes de 2/4 peças), etapa `otimizar_catalisador` em [`topgear/search.py`](src/wowsim/topgear/search.py:1), teto de cargas em [`topgear/constraints.py`](src/wowsim/topgear/constraints.py:1), flags `--catalisador` e `--max-catalisados` na CLI. |
| **Desligado por padrão** | `TopGearRequest.catalisador = False`. Sem o arquivo de tier, o recurso não liga e o relatório diz o motivo. |
| **Testes** | [`tests/test_topgear_catalisador.py`](tests/test_topgear_catalisador.py:1) — 29 testes. Suíte: **322 passed**; as 5 falhas restantes são `Exec format error` do `simc.exe` (binário Windows) em ambiente Linux. |
| **Pendente** | Validação ao vivo com o simc real (P-031) e exposição na UI (P-032). |

### P-031 — Validar o Catalisador no simc real

Só roda no Windows, com `bin/simc.exe`. Comando e critérios de aceite na seção 6.3 do
[`docs/PLANO-CONTINUIDADE.md`](docs/PLANO-CONTINUIDADE.md).
Controle de comparação: o fixture do Pyrogalth já traz peças catalisadas reais
(`chest=` com `redirected_base_stats=272231` e `legs=` com `273786`).
**Fecha com** um `.simc` gerado contendo `id=2715xx,...,redirected_base_stats=<origem>`,
aceito pelo simc, e o bônus de conjunto visível no relatório quando há 2 ou 4 peças.

### P-032 — Catalisador na API de estimativa e na UI

`GET /api/topgear/estimativa` ([`web/topgear_api.py`](src/wowsim/web/topgear_api.py:110))
ainda não conta os gêmeos nem os pacotes, então o custo mostrado fica abaixo do real quando
o recurso está ligado. Falta também o controle no
[`TopGearPanel.tsx`](../Simulator-WoW/src/components/TopGearPanel.tsx) e os campos em
[`topGearService.ts`](../Simulator-WoW/src/services/topGearService.ts).
**Fecha com** estimativa coerente, `tsc --noEmit` limpo e job criado pela UI retornando o
estágio `catalisador` no histórico de rodadas.

### P-033 — Teste de determinismo comparava cronometragem — **RESOLVIDA em 2026-11-08**

`tests/test_topgear_search.py::test_busca_e_deterministica` falhava de forma intermitente
porque comparava o `model_dump()` inteiro, incluindo `Rodada.duracao_s` (tempo de parede,
que nunca se repete). Os conjuntos e o DPS sempre batiam. A comparação agora ignora a
duração. Falha **anterior** a esta entrega.

### P-034 — Peça já catalisada perdia os stats base — **RESOLVIDA em 2026-11-08**

`conjunto_do_personagem` ([`topgear/search.py`](src/wowsim/topgear/search.py:1)) montava o
conjunto base sem copiar `redirected_base_stats`. Toda peça **já catalisada** do personagem
era reescrita sem o campo, perdendo os stats base do item de origem e falseando o DPS da
base — no Top Gear **e** no Droptimizer, que importa a mesma função. O campo agora é
preservado e entra nas chaves de deduplicação e de cache
([`pools.py`](src/wowsim/topgear/pools.py:1), [`heuristic/score.py`](src/wowsim/heuristic/score.py:1)).
Regressão coberta em `tests/test_topgear_catalisador.py`.
