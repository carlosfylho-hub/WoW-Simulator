# Raidbots — o que a página de desenvolvedores oferece e o que serve ao projeto

**Consultado em:** 2026-11-06
**Página:** https://www.raidbots.com/developers
**Natureza:** página SPA; o conteúdo útil não está no HTML, está nos dados estáticos servidos pelo site
**Decisão:** usar como **fonte secundária de validação**, nunca como autoridade sobre o `simc` do usuário

---

## 1. O que a página declara

O HTML entrega apenas o título e a descrição:

- título: `Developers - Raidbots`
- descrição: `Static data, Raidbots hooks, and more`

O HTML tem 4 KB e carrega um único bundle: `/frontend/simbot.<hash>.js`. Todo o conteúdo da página é renderizado no cliente, portanto não há texto útil para raspar sem executar JavaScript.

## 2. O que foi descoberto no bundle

O bundle é público e contém a configuração da aplicação. Os achados relevantes:

| Achado | Valor |
| :--- | :--- |
| Branch do SimC usada em produção | `midnight` |
| Canal | `latest` |
| Realm de dados live | `live` |
| Realm de dados PTR | `ptr` |
| Padrão de URL dos dados estáticos | `https://www.raidbots.com/static/data/<realm>/<arquivo>.json` |
| Versão dos dados | `contentHash: 06e38466fa95ee1416a4331fd72a4a2f` |
| Build em que os dados foram gerados | `12.1.5.70688` |
| Data de geração | `2026-10-31T03:45:07Z` |

**Aviso de build:** o addon do usuário é `12.1.5.70783`; os dados do Raidbots foram gerados em `12.1.5.70688`. É o mesmo patch, mas **não é o mesmo build**. Nada do Raidbots pode ser tratado como número final sem validação no `simc` local.

## 3. Arquivos publicados

`metadata.json` lista 51 arquivos. Os relevantes para este projeto:

| Arquivo | Tamanho aprox. | Uso no projeto | Fase |
| :--- | --: | :--- | :-: |
| `metadata.json` | 1,6 KB | build, hash e lista de arquivos | 3 |
| `bonus-upgrade-sets.json` | 522 KB | **`bonusId` para `itemLevel` por grupo, rank e custo de moeda** | 3 |
| `bonus-id-levels.json` | 37 KB | delta de nível por `bonus_id` | 3 |
| `bonus-id-base-levels.json` | 24 KB | nível base por `bonus_id` | 3 |
| `bonus-level-deltas.json` | 29 KB | tabela de deltas | 3 |
| `item-level-bonus-lookup.json` | 4 KB | item level para lista de bônus | 3 |
| `bonus-upgrade-sets.json` | — | trilhas e ranks | 3 |
| `bonus-sockets.json` | — | encaixes | 3 |
| `bonus-crafted-stats.json` | — | stats de craft | 3 |
| `bonus-effects.json` | — | efeitos por bônus | 3 |
| `omnium-talents.json` | 5 KB | **árvore do Folio Ômnico com as escolhas por nó** | 3 |
| `enchantments.json` | 463 KB | `enchant_id` e nomes | 3 |
| `enchantments-all.json` | — | variante completa | 3 |
| `temp-enchants.json` | — | encantamentos temporários, como óleos | 3 |
| `item-sets.json` | — | conjuntos de tier | 3 |
| `crafting.json` | — | craft e embelezamentos | 3 |
| `item-conversions.json` | — | conversões, como Catalisador | 3 |
| `bonus-roll-sources.json` | — | origens de extra roll | 5 |
| `encounter-items.json` | — | item por encontro | 5 |
| `instances.json`, `encounter-names.json` | — | nomes de instância e chefe | 5 |
| `seasons.json` | — | temporada e faixas | 3 |
| `content-tuning.json` | — | tuning de conteúdo | 3 |
| `currency-types.json` | — | moedas, incluindo Brasões | 3 |
| `gems.json` | — | gemas | 3 |
| `equippable-items.json` | 53 MB | catálogo completo de itens | 3, com cautela |
| `item-names.json` | 65 MB | nomes de todos os itens | 3, com cautela |

**Arquivos grandes:** `equippable-items.json` e `item-names.json` somam mais de 118 MB. Não entram no snapshot por padrão. Se forem necessários, o acesso deve ser por fluxo, filtrando só os IDs do personagem, e o resultado vai para `dados/derivados/`, não para o snapshot.

## 4. Evidência coletada nesta consulta

### 4.1 Folio Ômnico — a tabela `1368xx` está confirmada

`omnium-talents.json` é uma árvore de talentos com nós e escolhas. O nó `110271` tem três entradas:

| Entrada | Nome EN | `spellId` | Código esperado |
| :-: | :--- | :-: | :-: |
| `136814` | Rune of Overload | 1279614 | `5A` |
| `136824` | Rune of Residual Energy | 1279615 | `5B` |
| `136826` | Rune of Echoes | 1279616 | `5C` |

O export do Pyrogalth traz `136814`. Isso prova que:

1. Os IDs `1368xx` são **entradas de escolha**, não nós de desbloqueio.
2. `omnium_talents` carrega, sim, a **seleção** de cada linha.
3. A seleção do fixture é `1A-2B-3A-4A-5A`, e não `C14` (`5B`) como diz [`pendencias.md`](../../WoW%20Calculator/pendencias.md:264).
4. A afirmação de [`import_e_interpretacao_s2.md`](../../WoW%20Calculator/import_e_interpretacao_s2.md:529), de que o campo não contém a escolha, está **incorreta** para este build.

A resolução final ainda depende de ligar cada entrada ao nome PT-BR de [`rune_ids_s2.json`](../../WoW%20Calculator/rune_ids_s2.json:47). O caminho é pelo `spellId` da entrada, não pelo nome EN.

### 4.2 `bonus-upgrade-sets.json` — a tabela de rank que faltava

Estrutura observada, grupo `163`:

```json
{
  "163": [
    {"group": 163, "level": 1, "max": 7, "bonusId": 7195, "itemLevel": 36},
    {"group": 163, "level": 2, "max": 7, "bonusId": 7196, "itemLevel": 38, "costs": [...]}
  ]
}
```

O arquivo tem 68 grupos e cada entrada traz `bonusId`, `level`, `max` e `itemLevel`. É exatamente o dado que o projeto não tinha para rank 1/6 a 5/6.

**Ação da Fase 3:** localizar os grupos que contêm `12817–12822`, `12825–12830`, `12833–12838`, `12841–12846` e `12849–12854` e conferir se o `itemLevel` bate com os tetos já confirmados (`321` para Herói 6/6 e `334` para Mítico 6/6). Se bater, a tabela é aceita com `fonte=raidbots:bonus-upgrade-sets`; se não bater, vale o `simc` e a divergência vira pendência.

## 5. Como isso entra no projeto

| Regra | Detalhe |
| :--- | :--- |
| Precedência | saída do `simc` > catálogo do projeto > Raidbots. O Raidbots **não** substitui execução. |
| Proveniência | cada valor carrega `fonte=raidbots:<arquivo>` e a versão `contentHash` do metadata. |
| Snapshot | só arquivos pequenos e necessários entram em `dados/raidbots/`, com sha256. |
| Build | `metadata.wowBuild` é gravado em todos os relatórios que usarem essa fonte. Divergência de build é avisada, não escondida. |
| Atualização | download sob demanda, nunca automático. O conteúdo pode mudar sem aviso. |
| Uso | pessoal e local. Não redistribuir os arquivos nem publicar catálogo derivado deles. |

## 6. O que **não** foi encontrado

- Não há indicação de API pública de simulação no bundle; o serviço de simulação é interno.
- Não há documentação textual da página além de "Static data, Raidbots hooks, and more".
- Não foram encontrados "hooks" documentados publicamente no HTML; qualquer integração desse tipo exigiria conta e não é necessária para o projeto.
- Não há garantia de estabilidade de schema ou de URL. Qualquer uso deve falhar de forma explícita.

## 7. Próximos passos concretos (Fase 3)

1. Criar `scripts/baixar_dados_raidbots.py` com lista fechada de arquivos pequenos, `metadata.json`, sha256 e `--check`.
2. Criar `data/raidbots.py` que lê `bonus-upgrade-sets.json` e devolve `BonusUpgrade(bonus_id, grupo, rank, max, item_level, custo, fonte)`.
3. Validar os cinco grupos `128xx` e os dois forjados contra o `simc`.
4. Criar `data/omnium_map.py` que lê `omnium-talents.json`, extrai as 13 entradas e liga `entry.id` ao `spellId` de `rune_ids_s2.json`.
5. Teste de contrato que falha se um dos 5 IDs do fixture não estiver na árvore.

## 8. Reprodução da consulta

```bash
# metadata e arquivos pequenos
curl -L -sS -o metadata.json https://www.raidbots.com/static/data/live/metadata.json
curl -L -sS -o omnium-talents.json https://www.raidbots.com/static/data/live/omnium-talents.json
curl -L -sS -o bonus-upgrade-sets.json https://www.raidbots.com/static/data/live/bonus-upgrade-sets.json
```

Ferramentas locais usadas para ler sem poluir o chat: `scripts/extrair_texto_html.py`, `scripts/buscar_texto.py` e `scripts/inspecionar_json.py`.
