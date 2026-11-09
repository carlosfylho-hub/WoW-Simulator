# Auditoria 3 — Execução (2026-11-09)

> Registro do que foi feito a partir de `docs/AUDITORIA-3-CRAFT.md`. Cada pauta
> virou um commit (ou dois, quando tocou backend e frontend, que são repositórios
> separados). Testes escritos antes da correção; suíte completa ao final.

## Resumo

- 8 pautas tratadas: **7 concluídas** (A1, A2, A3, A4, A5, A6, A7) e **1 parcial** (A8:
  ícone e texto completos; materiais/usado-em vazios por extração instável da página).
- Suíte backend: `python -m pytest -q -m "not integration_simc"` → **472 passed, 2 deselected**.
- Frontend: `npx tsc --noEmit -p tsconfig.json` → **sem erros**.
- Repositórios: backend `wow-sim`, frontend `Simulator-WoW`. Árvores limpas ao final.

## Tabela de pautas

| # | O que era | O que foi feito | Arquivos | Testes | Commit | Status |
| :-: | :--- | :--- | :--- | :--- | :-- | :-: |
| A1/P-052 | Não se sabia quais embelezamentos o personagem já usa | `Embelezamento` ganhou `bonus_id`; novo `masmorras/embelezados.py` cruza `bonus_ids` do equipado com `dados/derivados/embelezamentos.json` e marca embutidos | `src/wowsim/masmorras/craft.py`, `src/wowsim/masmorras/embelezados.py`, `tests/test_embelezados.py` | `test_embelezados.py` (4) | `92ed854` | Concluído |
| A2/P-049 | Fase 1 media conjuntos com 3 embelezamentos (simc não impõe o teto) | `rodar_craft` valida cada conjunto ANTES de simular; peças que estouram o teto saem do ranking e viram `bloqueados` (com motivo na tela em texto-3) | `src/wowsim/masmorras/craft.py`, `src/wowsim/web/masmorras_worker.py`, `Simulator-WoW/.../ResultadoCraft.tsx`, `.../masmorrasService.ts`; `tests/test_craft.py` | `test_craft.py` (2 novos) | `9106017` / `3c9abc7` | Concluído |
| A3/P-050 | Fase 2 só sabia adicionar embelezamento; no teto nada era medido | No teto, mede **trocar** o reagente aplicado (contagem não sobe) ou a peça embutida inteira; escolhe a melhor peça **não embutida** por slot; resultado traz `tipo` (adicionar/troca/peca) e `troca_de` | `src/wowsim/masmorras/craft.py`, `Simulator-WoW/.../ResultadoCraft.tsx`, `.../masmorrasService.ts`; `tests/test_craft.py`, `tests/test_masmorras_builds_worker.py` | `test_craft.py` (2 novos), worker atualizado | `7d16755` / `dc74db1` | Concluído |
| A4/P-051 | Tooltip de craft sem atributos (peça não está no snapshot) | Novo `masmorras/sonda.py`: cópia do personagem por candidato (`copy=`), `iterations=1`, `max_time=1`, lê `players[i].gear` (mapeia `crit_rating`→`crit` etc. e `shoulders`/`wrists`); `rodar_craft` anexa `stats` via callback opcional | `src/wowsim/masmorras/sonda.py`, `src/wowsim/masmorras/craft.py`, `src/wowsim/web/masmorras_worker.py`; `tests/test_sonda.py` | `test_sonda.py` (4); **validado no simc real**: item 239675 → `crit=74, haste=74, intellect=138, stamina=2832` | `8f1baff` + `2af0f46` | Concluído |
| A5/P-051 | Tooltip com fonte errada ("Drop M+") e slot cru | `ItemIcone` aceita `fonte`/`roleTag`; Craft envia `Craft (Mítico qualidade 5)`/`Craftado`, slot em PT-BR e `stats`; sem fonte a tooltip diz "Fonte não informada" (P1) | `Simulator-WoW/src/ui/ItemIcone.tsx`, `.../services/itemTooltipService.ts`, `.../components/masmorras/ResultadoCraft.tsx` | `npx tsc --noEmit` | `56e424d` | Concluído |
| A8/P-055 | Embelezamentos sem ícone nem texto completo | Novo `scripts/raspar_embelezamentos.py` (tooltip JSON PT/EN + crawl4ai best-effort, cache, falha de rede não quebra); `embellishments.mesclar_wowhead` funde em `embelezamentos.json`; tela mostra ícone, texto e materiais recolhíveis | `scripts/raspar_embelezamentos.py`, `scripts/derivar_embelezamentos.py`, `src/wowsim/data/embellishments.py`, `src/wowsim/masmorras/craft.py`, `dados/derivados/*`; `tests/test_embelezamentos_wowhead.py`; front `ResultadoCraft.tsx`/`masmorrasService.ts` | `test_embelezamentos_wowhead.py` (4); 21/21 reagentes com ícone e texto PT-BR | `b091603` / `0e7e377` | **Parcial** (materiais/usado-em vazios — ver desvios) |
| A6/P-053 | Aviso âmbar "86 item(ns) do .inv AMR adicionados" | `RankingResult.informacoes` separado de `avisos`; worker deixa de promover `combinar_inv_mesclado` a aviso; tela mostra em texto-3 | `src/wowsim/masmorras/modelos.py`, `src/wowsim/web/masmorras_worker.py`, `Simulator-WoW/.../ResultadoRanking.tsx`, `.../masmorrasService.ts` | `tests/test_masmorras_*` (41) | `28004b9` / `ac731ba` | Concluído |
| A7/T10 | `embellishment=` nunca tinha rodado no simc real | Novo `scripts/validar_embellishment.py`: perfil do fixture + profileset craftado com `embellishment=<token>`; log anexado | `scripts/validar_embellishment.py`, `docs/log-craft-windows-2026-11-09.txt` | Execução real em Windows (log) | `4e26d5e` | Concluído |

## Desvios e decisões (código real × documento)

1. **A3 — teste do worker atualizado.** O fixture `fixtures/pyrogalth.simc` já usa
   **Forro de Arcanotrama aplicado em duas peças** (costas 239656 e pulsos 239648, bônus
   12384). Com o teto respeitado, o comportamento correto passou a ser *trocar* o reagente,
   não *adicionar*; o teste `test_modo_craft_no_worker` foi ajustado para exigir linhas
   `tipo="troca"` com `troca_de="Forro de Arcanotrama"`. Isso é a correção pedida (P-050),
   não uma regressão.
2. **A4 — formato real do `gear`.** O simc grava as chaves `shoulders` e `wrists` (plural),
   enquanto o slot interno é `shoulder`/`wrist`; foi adicionado `GEAR_SLOT`. Os atributos são
   planos (`intellect`, `crit_rating`, …), não aninhados; a sonda aceita os dois formatos.
3. **A8 — materiais e "onde usar" ficaram vazios.** A página renderizada do Wowhead mistura
   tabela, menu e comentários no texto; a extração não é estável. Seguindo o documento
   ("se a página não trouxer isso de forma estável, deixe o campo vazio — não adivinhe"),
   `materiais`/`usado_em` foram deixados vazios (o script registra a falha em `_falhas`).
   **Ícone e texto completo em PT-BR: 21/21 reagentes** (validado no JSON derivado).
4. **A4 — sonda é opcional e visual.** Roda só se houver folga de orçamento (`> 20 s`) e
   qualquer falha do simc não derruba o ranking; a tooltip apenas fica sem atributos. Nenhum
   número dela entra em cálculo de DPS (P1).

## Resultado final da suíte

```
python -m pytest -q -m "not integration_simc"
472 passed, 2 deselected in 25.41s

npx tsc --noEmit -p tsconfig.json
(sem saída = sem erros)
```

## O que continua em aberto (fora do escopo desta auditoria)

- P-054 (pendências antigas): T10 com o export **vivo** do usuário (aqui validado com o
  fixture `pyrogalth.simc`), U6/U7 do redesign, desconto de slot nos brasões, Craft Herói
  (305–318), armas no Craft, custo da Forja do Veneno, cargas do Catalisador.
- A8: materiais da receita e "onde o reagente pode ser usado" dependem de uma extração
  estável da página do Wowhead; o script está pronto para preencher quando isso ocorrer.
