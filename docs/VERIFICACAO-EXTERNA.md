# Verificação externa — o que é fato, o que foi corrigido e o que segue incerto

**Data:** 2026-11-07
**Escopo:** confrontar as afirmações do projeto e do simulador com Blizzard, SimulationCraft oficial, Wowhead e Raidbots.
**Regra:** quando a fonte externa primária contradiz o snapshot, vale a fonte externa e a divergência vira pendência. Nenhum número do simulador foi alterado por esta rodada; o que muda é a documentação e o entendimento do patch.

---

## 1. Resumo executivo

| Situação | Quantidade | Exemplos |
| :--- | :-: | :--- |
| Confirmado com fonte externa | 8 | build 70783, nomes/ilvl de 42 itens, 13 runas, 6 faixas de upgrade, tier 2066, Catalisador |
| Corrigido na documentação | 3 | 9 chefes → 8; 12.1.5 não é o patch de Ula'tek; 12.1.5 não é o lançamento da Temporada 2 |
| Ainda indeterminado | 4 | limite de 2 embelezamentos, Códice Corrosivo, pool de masmorras, APL do Ceifador |

---

## 2. Método e reprodutibilidade

| Fonte | Uso | Arquivo gerado |
| :--- | :--- | :--- |
| `http://us.patch.battle.net:1119/wow/versions` | build live do cliente | `dados/verificacao/wowhead.json` → `evidencia.blizzard` |
| GitHub API + raw da branch `midnight` | commit, versão de dados e arquivo `client_data_version.inc` | idem → `evidencia.simc_branch` e `evidencia.simc_version_file` |
| `nether.wowhead.com/tooltip/item` e `/tooltip/spell` | nomes, ilvl e runas, sem créditos Firecrawl | `dados/verificacao/wowhead.json` |
| `nether.wowhead.com/tooltip/item` com `bonus=` | ilvl por `bonus_id` | `dados/verificacao/bonus.json` |
| `www.raidbots.com/static/data/live/metadata.json` | build e hash dos dados estáticos | `dados/verificacao/wowhead.json` → `evidencia.raidbots_metadata` |

Scripts: [`scripts/verificar_externo.py`](../scripts/verificar_externo.py) e [`scripts/verificar_bonus.py`](../scripts/verificar_bonus.py).

---

## 3. Veredito por afirmação

| # | Afirmação | Veredito | Evidência |
| :-: | :--- | :-: | :--- |
| 1 | O cliente live é `12.1.5.70783` | **Confirmado** | Blizzard: `us\|...\|70783\|12.1.5.70783` |
| 2 | O fonte do SimC usado é o build `70783` | **Confirmado** | Branch `midnight`, commit `c20e2ad` é `[live] Game data update (Build 70783)`; arquivo `client_data_version.inc` declara `12.1.5.70783` |
| 3 | O binário local está alinhado ao cliente | **Confirmado** | `simc --version`: `SimulationCraft 1210-01 for World of Warcraft 12.1.5.70783 Live` |
| 4 | Nomes PT-BR e ilvl dos itens do fixture/catálogo | **Confirmado** | 42 itens no Wowhead, 0 nomes diferentes, 0 ilvl diferentes |
| 5 | Nomes das 13 runas do Folio | **Confirmado** | 13/13 iguais no tooltip de feitiço |
| 6 | `bonus_id` → ilvl das trilhas | **Confirmado** | 6/6 casos iguais: 266, 282, 318, 321, 334, 341 |
| 7 | Conjunto 2066 e 4 peças de Demonologia em 350%/315% | **Confirmado** | Tooltip do `271546` lista o conjunto 2066 e o 4pc com 350/315 |
| 8 | Catalisador preserva secundários e cantrip | **Confirmado** | Wowhead Matrix Catalyst: "In Patch 12.1, Catalyzed Class set armor now inherits the secondary stats and any cantrip effects" |
| 9 | Abismo Peçonhento tem **9** chefes | **REFUTADO** | Wowhead: "The Venomous Abyss features eight bosses, the final boss being Ula'tek" |
| 10 | O patch `12.1.5` é "A Maldição de Ula'tek" | **REFUTADO** | 12.1 é "The Curse of Ula'tek"; 12.1.5 é a atualização "The Promise of Tomorrow" |
| 11 | A Temporada 2 começa no 12.1.5 | **REFUTADO** | 12.1.5 é a atualização de meio de temporada, com Keystone Myth; a Temporada 2 já está ativa |
| 12 | A raid de 12.1.5 é o Abismo Peçonhento | **REFUTADO** | 12.1.5 adiciona a raid de um chefe "The Unbinding of Kith'ix" |
| 13 | Limite de 2 efeitos de embelezamento | **Indeterminado** | não revalidado nesta rodada; evidência atual é tooltip do projeto |
| 14 | Códice Corrosivo / Altar da Corrosão | **Indeterminado** | nomes e poderes não conferidos nesta rodada |
| 15 | Pool de 8 masmorras na Temporada 2 | **Indeterminado** | não extraído da fonte oficial nesta rodada |
| 16 | APL do SimC subestima Ceifador de Almas | **Indeterminado** | não há issue/documento oficial localizado nesta rodada |

---

## 4. Detalhes das confirmações

### 4.1 Build do cliente

```text
us|bc493ecb2898766c0f8947a99b4b3d65|6aee492112bf17a47b7aae8e30447df2|...|70783|12.1.5.70783|...
```

### 4.2 Branch do SimC

- HEAD da `midnight` em 2026-11-05: `d38855b`, mensagem `[test] Game data update (Build 70740)`.
- O commit anterior, `c20e2ad` (2026-11-04), é `[live] Game data update (Build 70783)`.
- O arquivo `engine/dbc/generated/client_data_version.inc` no HEAD continua dizendo `12.1.5.70783`; o commit de teste não alterou a versão do cliente.
- Conclusão: o `1210-01` é a versão interna do SimC, não o patch do cliente. A âncora correta é o build do cliente.

### 4.3 Wowhead — 42 itens e 13 runas

- 0 divergências de nome; 0 divergências de ilvl quando o projeto declara `ilvl_referencia`.
- Itens de craft aparecem no Wowhead com o ilvl-base (246), enquanto o export usa bônus de craft; a comparação de ilvl não se aplica a eles.
- `240984` não existe; era um ID de teste do script, não um item do catálogo.

### 4.4 Bônus de upgrade

| Caso | `bonus_id` | Ilvl esperado | Ilvl Wowhead |
| :--- | :--- | --: | --: |
| Aventureiro 1/6 | 12817 | 266 | 266 |
| Aventureiro 6/6 | 12822 | 282 | 282 |
| Herói 6/6 | 12846 | 321 | 321 |
| Mítico 1/6 | 12849 | 318 | 318 |
| Mítico 6/6 | 12854 | 334 | 334 |
| Forjado Mítico | 12856 | 341 | 341 |

Isso valida a tabela derivada do Raidbots com uma segunda fonte independente.

---

## 5. Correções factuais

### 5.1 O Abismo Peçonhento tem 8 chefes, não 9

O snapshot [`season2_context.json`](../dados/season2_context.json:37) e o `.md` dizem 9. O Wowhead lista oito chefes, com Ula'tek como final:

1. Nek'zali, a Encouraçadora de Almas
2. Sentinelas Entombed
3. Os Exploradores Perdidos
4. Vashnik, o Maligno
5. Sszorak, as Presas Gêmeas
6. O Altar Enrolado
7. (sétimo chefe da asa final)
8. Ula'tek

Kith'ix **não** é o nono chefe do Abismo Peçonhento: é a raid de um chefe adicionada no 12.1.5.

### 5.2 O patch 12.1.5 não é "A Maldição de Ula'tek"

| Patch | Nome | Conteúdo |
| :--- | :--- | :--- |
| 12.1 | *The Curse of Ula'tek* | Ilha Enrolada, raid Abismo Peçonhento (8 chefes), masmorra Altar das Presas, Temporada 2 |
| 12.1.5 | *The Promise of Tomorrow* | campanha final, raid de um chefe Kith'ix, Labirinto de Kindo'jan, Invasão Aqir, Pedras de Peçonha Ascendentes, Keystone Myth |

O build `70783` é 12.1.5 e contém os dois conteúdos; o simulador não muda. O rótulo nos documentos é que estava errado.

### 5.3 A Temporada 2 não começa no 12.1.5

O 12.1.5 é uma atualização de meio de temporada: retorno do Keystone Myth, nova raid e novo Labirinto. A Temporada 2 já estava ativa desde o 12.1.

---

## 6. O que permanece indeterminado

1. **Limite de 2 efeitos de embelezamento.** A evidência atual vem dos tooltips catalogados no projeto. Não foi feita uma varredura nova de todos os embelezamentos nesta rodada.
2. **Códice Corrosivo / Altar da Corrosão.** Os 12 poderes e os nomes PT-BR não foram revalidados. Continua fora do cálculo.
3. **Pool de masmorras da Temporada 2.** O número 8 não foi extraído de fonte oficial nesta rodada.
4. **APL do Ceifador de Almas.** Não foi localizada uma issue ou nota oficial do SimC confirmando a subestimação. O aviso do relatório continua sendo precaução, não fato verificado.

---

## 7. Impacto no simulador

- Nenhum número de DPS muda.
- A tabela `bonus_id → ilvl` fica com duas fontes independentes: Raidbots e Wowhead.
- As runas e os nomes de item ficam confirmados contra o tooltip oficial.
- O relatório deve continuar tratando "9 chefes" como texto do snapshot, não como fato; a correção no arquivo de origem é responsabilidade do projeto de dados.
