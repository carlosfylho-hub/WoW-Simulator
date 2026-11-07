# Pendências — WoW Calculator Sim

**Última atualização:** 2026-11-06
**Fase atual:** 1 concluída — Fase 2 autorizada
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
