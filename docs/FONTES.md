# Fontes de dados — inventário e regras de uso

**Projeto:** WoW Calculator Sim
**Patch:** cliente 12.1.5 — build do addon `12.1.5.70783`. Conteúdo 12.1 (*The Curse of Ula'tek*) mais atualização 12.1.5 (*The Promise of Tomorrow*). Ver [`VERIFICACAO-EXTERNA.md`](VERIFICACAO-EXTERNA.md).
**Fase:** 0
**Repositório de origem dos dados:** [`WoW Calculator`](../../WoW%20Calculator)

> Este documento responde a uma pergunta só: **de onde vem cada dado e quanto se pode confiar nele.**
> Regra herdada do projeto: todo dado consumido carrega `fonte="<arquivo>"` na saída. Se o dado não estiver aqui, ele não entra no cálculo.

---

## 1. Precedência

Do mais forte para o mais fraco:

1. **Saída do SimulationCraft** — DPS, erro, item level efetivo, comportamento do APL.
2. **Tooltip oficial gravado nos JSON do projeto** — `stats_oficiais_itens.json`, `encantamentos_e_gemas_s2.json`, `craft_sistemas_s2.json`, `craft_armas_s2.json`.
3. **Fichas de spec** — `demonology_warlock.json`, `affliction_warlock.json`, `destruction_warlock.json`, `shadow_priest.json`, `balance_druid.json` e seus `.md`.
4. **Regras da temporada** — `season2_context.json`.
5. **Guias de terceiros** já citados pelos arquivos acima.
6. **Texto do prompt do usuário** — usado apenas como pista de investigação, nunca como número final.
7. **Memória do modelo** — proibida.

Quando duas fontes 1–4 divergirem, vale a mais forte, e a divergência entra em [`../PENDENCIAS.md`](../PENDENCIAS.md) com o nome dos dois arquivos.

---

## 2. Arquivos usados e o que cada um entrega

Caminho relativo à raiz de [`WoW Calculator`](../../WoW%20Calculator). Todos serão copiados para `wow-sim/dados/` com hash registrado em `dados/MANIFEST.json`.

| Arquivo | O que entrega | Consumido por | Confiança | Cuidados |
| :--- | :--- | :--- | :-: | :--- |
| [`00-INSTRUCOES-IA.md`](../../WoW%20Calculator/00-INSTRUCOES-IA.md) | método, formato PT-BR, precedência, os cinco tetos, regra bilíngue | todos | alta | é regra editorial, não dado de jogo |
| [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md) | gramática do export, campos por slot, regras R1–R12, casos de borda | `parser/addon.py` | alta | afirma que `omnium_talents` não traz a escolha; ver conflito C1 |
| [`pendencias.md`](../../WoW%20Calculator/pendencias.md) | erratas, o que já foi corrigido, o que não repetir | todos | alta | referência do prompt a `3.16-A` não existe no arquivo; ver C5 |
| [`auditoria_ptbr.md`](../../WoW%20Calculator/auditoria_ptbr.md) | histórico de correções de nome PT-BR com evidência | `data/catalog.py` | média | é registro histórico, não catálogo |
| [`season2_context.json`](../../WoW%20Calculator/season2_context.json) | trilhas, Catalisador, tier, forja, afixos, slots de tier | `catalog`, `report` | alta | só traz ilvl de 6/6 e dos dois forjados; ver C4 |
| [`bonus_ids_s2.json`](../../WoW%20Calculator/bonus_ids_s2.json) | séries `128xx` e `1369x`, faixas de trilha, bônus soltos | `catalog.bonus_para_ilvl` | alta para faixas, média para rank | não contém ilvl por rank 1/6 a 5/6 |
| [`encantamentos_e_gemas_s2.json`](../../WoW%20Calculator/encantamentos_e_gemas_s2.json) | 38 encantamentos em 76 IDs, 72 gemas, 6 aprimoramentos de perna em 12 IDs, mira de arma | `data/enchants`, `catalog` | alta | tooltip PT imprime `Atributo não utilizado` em 64 itens; usar campos parseados |
| [`enchant_ids_s2.json`](../../WoW%20Calculator/enchant_ids_s2.json) | 97 `enchant_id` → nome PT/EN, tier, `item_id` | `data/enchants` | alta | inclui 8 óleos, 1 tinker e 12 de ferramenta fora do cálculo |
| [`rune_ids_s2.json`](../../WoW%20Calculator/rune_ids_s2.json) | 13 runas, linha, escolha, `id_base`, `id_buff`, efeito PT | `gen/omnium` | alta | não contém a família `1368xx`; ver C1 |
| [`consumiveis_e_sistemas_s2.md`](../../WoW%20Calculator/consumiveis_e_sistemas_s2.md) | matriz do Folio C01–C72 e regra de localização do Códice | `gen/omnium`, `report` | alta para Folio, média para Códice | nomes do Códice têm erros conhecidos; não usar para cálculo |
| [`talent_builds_season2.json`](../../WoW%20Calculator/talent_builds_season2.json) | builds por spec e cenário, import strings, `warlock_outras_specs`, dossiê de Delves | `gen/profilesets`, `report` | alta | import string não é decodificada; comparar por loadout |
| [`mplus_loot_database.json`](../../WoW%20Calculator/mplus_loot_database.json) | loot de M+ por masmorra e slot, pesos de atributo, `tabela_ilvl_mplus` | `catalog.itens_mplus`, `report` | alta | usar `usavel_por_conjurador` para excluir berloques de Força/Agilidade |
| [`armaduras_malha_placa.json`](armaduras_malha_placa.json) | peças de Malha e Placa por slot (ilvl, atributo adaptativo `[X ou Intelecto]`) raspadas do Wowhead | `catalog.itens_da_secao` (pools de Top Gear) | média | gerado por [`scripts/raspar_armaduras.py`](../scripts/raspar_armaduras.py) via crawl4ai (`listviewitems`, lista completa) + tooltip; usa `--min-id` para focar na temporada; fica fora do MANIFEST e deve ser regerado quando a temporada mudar |
| [`amr_mapa.json`](amr_mapa.json) | mapa **versionado** autoritativo do AskMrRobot: `ClassIds`, `RaceIds`, `FactionIds`, `SpecIds` (spec Blizzard → índice AMR) e `SlotIds` | `wowsim.parser.amr.classe_do_import` / `raca_da_import` | alta | gerado por [`scripts/extrair_mapa_addon_amr.py`](../scripts/extrair_mapa_addon_amr.py) a partir do addon local instalado (`.toc` + `AskMrRobot-Serializer.lua`); [`scripts/raspar_mapa_amr.py`](../scripts/raspar_mapa_amr.py) complementa versões antigas via fórum. Fica fora do MANIFEST |
| [`delve_loot_kindojan.json`](../../WoW%20Calculator/delve_loot_kindojan.json) | conjunto Pisa-piras, itens de Delve, tokens do Labirinto | `report` — seção Onde dropa | média | `_meta.nome` diz "Banco de Dados M+"; o conteúdo é de Delve; ver C6 |
| [`craft_sistemas_s2.json`](../../WoW%20Calculator/craft_sistemas_s2.json) | 91 IDs de embelezamento, missiva e reagente, com "Usável com" | `gen/profilesets` | alta | limite é de **2 efeitos**, não de peças |
| [`craft_armas_s2.json`](../../WoW%20Calculator/craft_armas_s2.json) | 29 armas craftáveis, família PT-BR confirmada | `catalog`, `report` | alta | craft de entrada 165–263 não é o craft com Centelha |
| [`craft_receitas_s2.json`](../../WoW%20Calculator/craft_receitas_s2.json) | receitas por profissão, runas e consumíveis | `catalog`, `report` | média | inventário é consulta, não prosa |
| [`stats_oficiais_itens.json`](../../WoW%20Calculator/stats_oficiais_itens.json) | nome PT/EN, `ilvl_referencia`, track, stats oficiais, efeito, ícone | `catalog.nome_item` | alta | valores são do **track máximo**, não do ilvl atual do jogador |
| [`monitor_upgrades_s2.json`](../../WoW%20Calculator/monitor_upgrades_s2.json) | armas, pescoços, mãos secundárias e berloques nos tetos 341 e 328 | `catalog.berloques`, `report` | alta | mesmo item aparece nos dois tetos mudando só o `bonus_id` |
| [`guia_economia_brasoes_e_upgrades_s2.md`](../../WoW%20Calculator/guia_economia_brasoes_e_upgrades_s2.md) | custo de Brasões por slot, rendimento de M+ e Delve | `report` — seção Limites | média | economia não é simulada |
| [`guia_masmorras_e_delves_s2.md`](../../WoW%20Calculator/guia_masmorras_e_delves_s2.md) | contexto por masmorra e por Tier de Delve | `report` | baixa | recomendações de Folio divergem da matriz; ver C8 |
| [`demonology_warlock.json`](../../WoW%20Calculator/demonology_warlock.json) | tier, BiS, berloques, talentos e Murlok do Demo | `catalog`, `report` | alta | ficha é recomendação, não resultado de simulação |
| [`affliction_warlock.json`](../../WoW%20Calculator/affliction_warlock.json) | ficha do Suplício, incluindo `bis_sem_raide` e arma sem raide | `catalog`, `report` | alta | Ceifador de Almas roda mal no APL padrão; ver R9 da arquitetura |
| [`destruction_warlock.json`](../../WoW%20Calculator/destruction_warlock.json) | ficha da Destruição | `catalog`, `report` | alta | — |
| [`shadow_priest.json`](../../WoW%20Calculator/shadow_priest.json) | BiS, tier e talentos do Sacerdote Sombra | `catalog`, `report` | alta | — |
| [`balance_druid.json`](../../WoW%20Calculator/balance_druid.json) | BiS, tier e talentos do Druida do Equilíbrio | `catalog`, `report` | alta | usa adaga de uma mão mais mão secundária |

**Pares `.md`:** copiados junto quando existem, porque são a camada de leitura e frequentemente explicam uma errata que o JSON não registra. O código lê o JSON; o `.md` serve ao humano e ao relatório.

---

## 3. Fatos que existem só no prompt e ainda não foram verificados

Estes itens **não** entram como dado de cálculo até serem confirmados contra o simc ou contra um arquivo do projeto.

| Fato declarado no prompt | Situação | O que fazer |
| :--- | :--- | :--- |
| Tabela `1368xx` do Folio: 1A 136822, 1B 136825, 2A 136816, 2B 136819, 2C 136823, 3A 136817, 4A 136815, 4B 136821, 4C 136818, 4D 136820, 5A 136814, 5B 136824, 5C 136826 | Não existe em arquivo do projeto, mas o export real traz exatamente esses 5 IDs, um por linha, formando uma combinação válida | Implementar como tabela marcada `fonte=prompt`; ver C1 |
| Exemplo `omnium_talents=136814/136815/136817/136819/136822` = `1A-2B-3A-4A-5A` | **Confirmado como o fixture real.** Contradiz [`pendencias.md`](../../WoW%20Calculator/pendencias.md:264), que registra `1A-2B-3A-4A-5B` | Usar o export como padrão, confiança média; `--runas` prevalece; ver C1 e C2 |
| `12846` = Herói 6/6 em 321, `12854` = Mítico 6/6 em 334, `12856` = Mítico forjado em 341 | Confirmado em [`bonus_ids_s2.json`](../../WoW%20Calculator/bonus_ids_s2.json:29) | Usar normalmente |
| DPS esperado de 254 mil em DungeonSlice e 204 mil em Patchwerk para o Pyrogalth | Não há registro no projeto | Serve só como valor de conferência da Fase 1; se divergir mais de 3%, investigar build e binário |
| `enchant_id` 7967 = Olhos da Águia, 7981 = Precisão de Jan'alai, 7987 = Marca da Alma do Mundo | `7981` aparece em [`enchant_ids_s2.json`](../../WoW%20Calculator/enchant_ids_s2.json:1); os outros dois não foram conferidos | Resolver pelo arquivo; não assumir pelo prompt |
| Peça Mítica 1/6 vale 318 e é menor que Herói 6/6 em 321 | O projeto só confirma os tetos 6/6 e os forjados | Tratar como pendência até derivar o rank com o simc |
| `engine/dbc/generated/item_data.inc` e `permanent_enchant.inc` como fonte de nomes | Caminho existe no repositório do simc, não no projeto | Usar como **secundário**; o primário é o catálogo local |
| Embelezamento conta por efeito, limite 2 | Confirmado em [`00-INSTRUCOES-IA.md`](../../WoW%20Calculator/00-INSTRUCOES-IA.md:91) | Modelar por efeito, nunca por peça |

---

## 4. Conflitos conhecidos

| # | Assunto | Fonte A | Fonte B | Resolução adotada |
| :-: | :--- | :--- | :--- | :--- |
| C1 | Natureza e conteúdo de `omnium_talents` | Prompt: são as runas escolhidas, com IDs `1368xx` | [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:529): são nós de desbloqueio | **Resolvido em 2026-11-06.** O export traz 5 IDs, um por linha, e o [`omnium-talents.json`](https://www.raidbots.com/static/data/live/omnium-talents.json) do Raidbots mostra que `1368xx` são **entradas de escolha** do nó `110271`, não nós. O campo carrega a seleção. Ver [`RAIDBOTS-REFERENCIA.md`](RAIDBOTS-REFERENCIA.md) |
| C2 | Seleção do personagem | Prompt: `1A-2B-3A-4A-5A` | [`pendencias.md`](../../WoW%20Calculator/pendencias.md:264): `1A-2B-3A-4A-5B` = C14 | **Resolvido em 2026-11-06.** O export traz `136814`, não `136824`; [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:683) lista `136824`, o que é erro de leitura. Seleção do fixture = `1A-2B-3A-4A-5A`; `pendencias.md` está errado nesse ponto |
| C3 | Origem do nome do encantamento | Prompt: `permanent_enchant.inc` | `enchant_ids_s2.json` já auditado contra o DB2 | Arquivo do projeto é primário; `.inc` é verificação |
| C4 | ilvl por rank de trilha | Prompt cita 318 para Mítico 1/6 | Projeto só tem 6/6 e forjados | Derivar com simc; `ilvl=null` + pendência enquanto não derivado |
| C5 | Seção `3.16-A` de pendências | Prompt manda consultar | Não existe em [`pendencias.md`](../../WoW%20Calculator/pendencias.md:239); a 3.16 trata do monitor de upgrades | Não citar `3.16-A`; registrar erratas do Códice como pendência própria |
| C6 | Nome do arquivo de Delve | `delve_loot_kindojan.json` se declara "Banco de Dados M+" | Conteúdo é conjunto Pisa-piras e tokens do Labirinto | Ignorar `_meta.nome`; o conteúdo é válido |
| C7 | Nomes do Códice Corrosivo | Prompt avisa que têm erros | [`talent_builds_season2.md`](../../WoW%20Calculator/talent_builds_season2.md:297) e fichas listam `P01` a `P39` | Códice não entra no cálculo; no relatório, tratar como não simulado |
| C8 | Folio por cenário em Delve | [`guia_masmorras_e_delves_s2.md`](../../WoW%20Calculator/guia_masmorras_e_delves_s2.md:261) recomenda `C23` | [`pendencias.md`](../../WoW%20Calculator/pendencias.md:235) afirma correção para `C29` | Usar a matriz de `consumiveis_e_sistemas_s2.md` como fonte de código; divergência fica registrada |
| C9 | Marca do Magíster × Marca da Alma do Mundo no torso | Prompt alerta para o erro | [`pendencias.md`](../../WoW%20Calculator/pendencias.md:180) trata de `enchant_id` e não fecha o nome do torso | Não afirmar qual é o encantamento de torso sem conferir `enchant_ids_s2.json` |
| C10 | Berloques do Pyrogalth | Prompt: par Dazar mais Ampola | [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:687) descreve `273649` e `273796` | **Resolvido pelo fixture:** `trinket1=273649` e `trinket2=273796`, ambos on-use, o que ativa a regra R4 e torna o par um caso de conflito a sinalizar |
| C11 | Build dos dados do Raidbots | `metadata.wowBuild` = `12.1.5.70688` | Addon do usuário = `12.1.5.70783` | Raidbots é fonte secundária e de validação; todo uso registra o build e é conferido contra o simc local |
| C12 | Contagem de chefes do Abismo Peçonhento | Snapshot `season2_context.json`: 9 chefes | Wowhead: 8 chefes, final Ula'tek; Kith'ix é raid separada do 12.1.5 | Vale o Wowhead; o campo `num_bosses` do snapshot não é usado pelo código. Ver P-022 |
| C13 | Nome do patch 12.1.5 | Snapshot e prompt: *A Maldição de Ula'tek* | Blizzard/Wowhead: 12.1 é *The Curse of Ula'tek*; 12.1.5 é *The Promise of Tomorrow* | Usar o rótulo correto nos documentos; o build 70783 continua a âncora técnica |

---

## 5. Arquivos deliberadamente **não** copiados

| Item | Motivo |
| :--- | :--- |
| `base_conhecimento_ai_studio/`, `base conhecimento ai studio/` | duplicatas da raiz, com risco de divergência silenciosa |
| `auditoria_itens.json`, `auditoria_ptbr.json`, `varredura_itens.json`, `dados_wowhead_scraping.json` | caches de raspagem; o dado útil já está nos JSON normalizados |
| `dados_enchant_ids.csv` | cache do DB2, já convertido em `enchant_ids_s2.json` |
| `tools/` | scripts Node do projeto de dados; o simulador é Python e não deve depender deles |
| `PROTOCOLO_FIRECRAWL_WOWHEAD.md` | protocolo de coleta, fora do escopo de simulação |
| `*.zip` | artefatos de backup |

Se algum dado faltar, a resposta é **pendência**, não cópia de cache não auditado.

---

## 6. Atualização do snapshot

1. `python scripts/sincronizar_dados.py --origem "../../WoW Calculator"` — recalcula hash, atualiza `dados/MANIFEST.json` e mostra diff de tamanho. Sem `--origem`, o script procura o repositório em `../../WoW Calculator` e em `../WoW Calculator`.
2. Se o hash mudou, o script avisa e **não** sobrescreve sem `--aceitar`.
3. Depois de aceitar, rodar `pytest -m "unit or schema"` e revisar `PENDENCIAS.md`, porque uma errata pode ter alterado semântica.
4. Commit do snapshot separado do commit de código: `chore(dados): sincronizar snapshot da temporada`.

---

## 7. Fatos que o código pode assumir hoje

Confirmados por arquivo do projeto:

- Trilhas de upgrade: Aventureiro `12817–12822`, Veterano `12825–12830`, Campeão `12833–12838`, Herói `12841–12846`, Mito `12849–12854`; forjados `12848` e `12856`.
- Ilvl dos tetos: Herói 6/6 = 321; Mítico 6/6 = 334; forjado Herói = 328; forjado Mítico = 341; cantrip de raide = 344.
- Slots de tier: Cabeça, Ombros, Peitoral, Mãos e Pernas; a marca é por item, não pela série `1369x` sozinha.
- Catalisador preserva stats e cantrip, mas **não** sobe de track.
- Encantamento clássico existe para cabeça, ombros, peitoral, pés, dois anéis e arma; não existe para pulsos e capa. Pernas usam Magilinha ou Kit. Mãos podem receber Arte de Batalha Hash'ey, que é camada própria e não encantamento.
- `enchant_id` é linha de `SpellItemEnchantment`, uma por qualidade; não é ID de pergaminho.
- Gema prismática é única equipada; o limite de embelezamento é de 2 efeitos.
- `slot_high_watermarks` só tem o índice 14 autorizado para leitura; os demais são informativos.
- Berloques on-use compartilham recarga; par on-use mais on-use é proibido pela R4.
- Códice Corrosivo só funciona em mundo aberto e Delve; não é simulado pelo SimC.
- Diferença abaixo de 0,15% é ruído e nunca vira recomendação.

---

## 8. Evidência do fixture recebido em 2026-11-06

Fonte: export colado pelo usuário, a ser salvo em `fixtures/pyrogalth.simc` na Fase 1.

**Cabeçalho**
- `# Pyrogalth - Demonology - 2026-11-06 20:04 - US/Azralon`
- `# SimC Addon 12.1.5-04`, `# WoW 12.1.5.70783, TOC 120105`
- `warlock="Pyrogalth"`, nível 90, dracthyr, `role=spell`, `alchemy=100/enchanting=100`

**Estrutura observada**
- **6 loadouts salvos**, todos comentados: `raid maxroll`, `Diabolist Delves`, `m+ icy`, `delves icy`, `Diabolist Single`, `single icy`.
- `omnium_talents=136814:1/136815:1/136817:1/136819:1/136822:1`.
- **16 linhas de slot** no bloco principal, incluindo `tabard`; **sem `off_hand`**.
- **5 itens** em `### Gear from Bags`.
- **17 marcas** em `slot_high_watermarks`, com o índice 14 em `259:305`.
- `catalyst_currencies` com 5 entradas; `upgrade_currencies` com 14; `bonus_roll_items` presente.

**Encantamentos resolvidos por `enchant_ids_s2.json`**

| Slot | `enchant_id` | Nome EN | Situação |
| :--- | :-: | :--- | :--- |
| head | 8017 | Enchant Helm - Empowered Rune of Avoidance | confirmado no mapa |
| shoulder | 8001 | Enchant Shoulders - Amirdrassil's Grace | confirmado no mapa |
| chest | 7987 | Enchant Chest - Mark of the Worldsoul | confirmado no mapa |
| feet | 7963 | Enchant Boots - Lynx's Dexterity | confirmado no mapa |
| finger1 e finger2 | 7967 | Enchant Ring - Eyes of the Eagle | confirmado no mapa, nos dois anéis |
| main_hand | 7981 | Enchant Weapon - Jan'alai's Precision | confirmado no mapa |
| legs | 7935 | `+k1 Intellect & +k2 Stamina` Tier 2 | **não está no mapa de 97 IDs**; é Magilinha, camada de pernas |
| hands | 8730 | Ancient Hash'ey Battle Art: Eye of the Lynx | **não está no mapa de 97 IDs**; é Arte de Batalha Hash'ey, não encantamento clássico |

**Gemas**

| Item | Gema | Nome PT-BR | Regra |
| :--- | :-: | :--- | :--- |
| head | 240983 | Diamante do Canto Eterno Indecifrável | único-equipado, +32 de atributo primário |
| neck, waist, finger1, finger2 | 240908 | Granada Primorosa Impecável | +16 de Crítico e +7 de Maestria |

**Tier e bônus**
- 5 peças de tier: `head` 13692, `shoulder` 13694, `chest` 13690, `hands` 13691, `legs` 13693.
- `legs` traz `bonus_id=41` (Sorver) e `13440` (procedência M+).
- `trinket2` traz `12699` (downscale de craft).
- `chest` traz `redirected_base_stats=272231` (Perponte do Pisa-piras), indicando item catalisado; `waist` 251185, `legs` 273786, `feet` 156350.

**Divergências entre o export e a documentação do projeto**

| # | Documentação | Export real | Ação |
| :-: | :--- | :--- | :--- |
| D1 | [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:720) prevê 7 loadouts | há 6 | usar 6; registrar errata |
| D2 | [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:683) lista runa `136824` | o export traz `136814` | usar o export; registrar errata |
| D3 | Documento descreve addon `12.1.5-03` | o addon é `12.1.5-04` | parser aceita ambos; comparar apenas o build `70783` |
| D4 | Regra de que mãos não têm encantamento | `hands` traz `enchant_id=8730` | classificar como Arte de Batalha Hash'ey, camada própria |
| D5 | Regra de que pernas usam Magilinha, fora do DB2 | `legs` traz `enchant_id=7935` | resolver Magilinha por spell ou item; nunca tratar como encantamento |

---

## 9. Fonte secundária — dados estáticos do Raidbots

**Página:** https://www.raidbots.com/developers (SPA; o conteúdo útil está nos dados, não no HTML).
**Padrão:** `https://www.raidbots.com/static/data/live/<arquivo>.json`.
**Build observado:** `12.1.5.70688`, gerado em `2026-10-31`; o addon do usuário é `12.1.5.70783`.
**Papel:** validação e preenchimento de lacunas. Nunca substitui a saída do simc.

| Recurso | Uso no projeto | Confiança |
| :--- | :--- | :-: |
| `metadata.json` | build, `contentHash` e lista de 51 arquivos | alta |
| `omnium-talents.json` | árvore do Folio; prova que `1368xx` são entradas de escolha | alta para estrutura, média para build |
| `bonus-upgrade-sets.json` | `bonusId → itemLevel` por grupo e rank | alta após conferir os tetos 321 e 334 |
| `bonus-id-levels.json`, `bonus-id-base-levels.json`, `bonus-level-deltas.json` | matemática de nível de item | média |
| `item-level-bonus-lookup.json` | nível por lista de bônus | média |
| `enchantments.json`, `temp-enchants.json` | `enchant_id`, incluindo camadas temporárias | alta para identificação |
| `bonus-roll-sources.json`, `encounter-items.json`, `instances.json` | origem de drop e extra roll | média |
| `item-sets.json`, `crafting.json`, `item-conversions.json`, `seasons.json` | tier, craft, Catalisador e temporada | alta |
| `equippable-items.json` (53 MB), `item-names.json` (65 MB) | catálogo completo | não versionar; acesso filtrado por ID |

**Regras:** registrar `fonte=raidbots:<arquivo>` e o `contentHash` em todo uso; divergência de build vira aviso; nada é baixado automaticamente; uso pessoal, sem redistribuição dos arquivos.

Detalhes, endpoints e evidência completa em [`RAIDBOTS-REFERENCIA.md`](RAIDBOTS-REFERENCIA.md).
