# Auditoria 3 — Craft, tooltips e o que falta (2026-11-09)

> **Para a IA que continuar:** este documento é só diagnóstico e plano. **Nada aqui foi
> implementado.** Siga a ordem da §4, uma tarefa por commit, testes antes do código, e marque o
> checklist (§5) com o hash. Regras de sempre: P1 (nenhum número que o simc não mediu), P4 (delta
> sempre contra a base da mesma leitura), fins de linha preservados (ver workflow §9 —
> `git -c core.autocrlf=input add` para arquivos com blob LF) e `dados/*.json` só por script.
> As pendências estão registradas em `PENDENCIAS.md` §12 (P-049 a P-058).

## 1. O que o usuário viu (prints de 2026-11-09 02:32)

1. Tooltip de peça craftada: "Atributos não catalogados", slot cru (`feet`), "Fonte / Drop:
   Catálogo · Drop M+" — errado para craft.
2. Peças para craftar: 8 de 9 "servem", com ganhos altos (+2,94% pés, +2,68% pulsos...). **Vários
   desses números estão inflados** (ver P-049).
3. Embelezamentos: "Nenhum embelezamento pôde ser medido" e 10 avisos "Conjunto tem 3
   embelezamentos; o máximo é 2". Para o usuário, que já usa 2 peças embelezadas, o modo Craft não
   responde à pergunta principal.
4. Aviso âmbar "86 item(ns) do .inv AMR adicionados às bolsas" — informação, não aviso.

## 2. Causas confirmadas (com evidência)

### P-049 — Fase 1 do Craft mede conjuntos com 3 embelezamentos (ALTO: números errados)
- `masmorras/craft.py::rodar_craft` só chama `constraints.validar` na fase 2. A fase 1
  (`montar_opcoes_craft`) não valida nada.
- **O simc não impõe o limite de 2:** `grep -i "embellish" engine/item/item.cpp engine/player/*.cpp`
  não acha regra de contagem; `decode_embellishment` só aplica o efeito. Logo, um 3º efeito é
  simulado como se funcionasse — no jogo ele fica inativo.
- O usuário já usa 244613 (peito) e 244614 (mãos), ambos com embelezamento embutido
  (`embellishments.listar_craftados()` → `embutido: True`). Toda peça craftada **embutida** fora
  desses dois slots (pés 244601 +2,94%, pulsos 244612 +2,68%, cintura 244606 +2,12%, pescoço 241139
  +1,71%, anel 251513 +1,39%) foi medida com 3 efeitos. **Os ganhos dessas linhas não valem**; só as
  peças não embutidas (capa 239656, ombros 244572...) e as que trocam o próprio slot embelezado
  (mãos 244614) estão corretas.

### P-050 — Fase 2 só sabe "adicionar" embelezamento, nunca "trocar" (ALTO: tela inútil para quem já tem 2)
- A fase 2 escolhe o melhor slot onde o embelezamento cabe e soma ao conjunto. Com 2 já equipados,
  sempre vira 3 → `validar` recusa → nada é medido.
- A pergunta certa para quem está no teto é **"trocar o embelezamento X por Y rende quanto?"**:
  medir Y no slot de um embelezamento atual (o total continua 2).

### P-051 — Tooltip de craft sem atributos e com fonte errada (MÉDIO)
- Peça craftada tem secundários definidos pela missiva e valor pelo ilvl; não existe em
  `stats_oficiais_itens.json` (só drops). `ResultadoCraft` também não manda `stats` ao `ItemIcone`.
- O simc **sabe** os atributos: `report_json.cpp::gear_to_json` (linha 382, chamado na 893) escreve
  `players[i].gear.<slot>` com cada atributo do item já com `ilevel`/`crafted_stats` aplicados.
- `itemTooltipService.ts:1069-1070` cai em `'Masmorra M+'`/`'Drop M+'` quando não sabe a fonte, e o
  slot vem cru do backend (`feet`).

### P-052 — Embelezamentos que o usuário já usa não são identificados (MÉDIO, pré-requisito do P-050)
- Não há função que diga "o item equipado no slot S tem o embelezamento E (bônus B)". O
  `embelezamentos.json` tem o `bonus_id` de cada embelezamento (gerado do simc), e o export do SimC
  traz os `bonus_ids` do item: dá para cruzar.

### P-053 — Aviso de ".inv mesclado" aparece como alerta (BAIXO)
- `web/masmorras_worker.py:465` promove o código `combinar_inv_mesclado` (severidade info) para a
  lista de avisos. Deve ir para um campo informativo, não âmbar.

### P-054 — Pendências antigas ainda abertas (lista para não perder)
| Item | Onde | Situação |
| :--- | :--- | :--- |
| T10 validação ao vivo | jogo | Pawn e string do AMR importados no jogo; Craft com embelezamento (o token `embellishment=` ainda não rodou de verdade, porque a fase 2 nunca mediu nada) |
| U6/U7 do redesign | `Simulator-WoW/docs/PLANO-REDESIGN-UI.md` | Top Gear/Droptimizer com fundo violeta próprio; capturas "antes" não feitas |
| Desconto de slot nos brasões | `data/trilhas.py::custo_upgrade` | custo mostrado é o cheio (rotulado) |
| Craft Herói (305–318) | `masmorras/craft.py` | só Mítico Q5 = 331; sem opção de qualidade |
| Armas no Craft | `masmorras/craft.py::_LISTAS_ARMADURA` | não monta armas nem mão secundária |
| Custo da Forja do Veneno | `data/trilhas.py` | desconhecido (Ascendant Venomstones) |
| Cargas do Catalisador | modo Craft e Masmorras | não mostra quantas cargas a sugestão gasta |

## 3. O que NÃO é problema
- `ilevel=331,crafted_stats=…` funcionou no simc real (a fase 1 rodou e devolveu números). Só o
  `embellishment=` ainda não foi exercitado.
- O par de missiva escolhido por slot é coerente (Aceleração aparece na maioria, como esperado
  para o usuário).
- O Pawn da build "Atual" saiu e passa no formato do addon.

## 4. Plano, em ordem (o que fazer, com o começo do código)

### 4.1 P-052 — Saber quais embelezamentos o personagem já usa
Arquivo novo `src/wowsim/masmorras/embelezados.py`. Teste primeiro com o fixture do druida
(`fixtures/ngmmexe-amr-cofre.txt` + um /simc do usuário, se houver) ou um `Conjunto` sintético.

```python
"""Quais slots do conjunto já gastam um dos 2 efeitos de embelezamento, e qual."""
from __future__ import annotations
from dataclasses import dataclass
from ..data import catalog, embellishments
from ..topgear.models import Conjunto
from .craft import Embelezamento, embelezamentos

@dataclass(frozen=True)
class EmbelezadoAtual:
    slot: str
    item_id: int
    embutido: bool                    # vem do próprio item (não dá para trocar)
    aplicado: Embelezamento | None    # reagente aplicado (dá para trocar)

def embelezados_do_conjunto(conjunto: Conjunto) -> list[EmbelezadoAtual]:
    por_bonus = {e.bonus_id: e for e in _com_bonus()}          # ver nota abaixo
    saida = []
    for slot, c in conjunto.itens.items():
        if c.item_id is None:
            continue
        aplicado = next((por_bonus[b] for b in (c.bonus_ids or []) if b in por_bonus), None)
        embutido = embellishments.info(c.item_id).embutido   # campo existe em models.EmbelezamentoInfo
        if aplicado or embutido or c.embelezamento_simc:
            saida.append(EmbelezadoAtual(slot, c.item_id, embutido, aplicado))
    return saida
```
Nota: `Embelezamento` (em `craft.py`) ainda não guarda `bonus_id`; acrescente o campo lendo
`dados/derivados/embelezamentos.json` (já tem `bonus_id`). **Aceite:** um item com o bônus 12384 é
reconhecido como "Forro de Arcanotrama"; 244613/244614 aparecem como embutidos.

### 4.2 P-049 — Fase 1 respeita o teto de 2
Em `rodar_craft`, antes de simular, valide cada conjunto. Uma peça embutida que estoura o teto
**não entra no ranking como se fosse válida**: ou é medida no lugar de um embelezado atual (se o
slot for o mesmo, a contagem não sobe), ou vira uma linha "exige abrir mão de um embelezamento".

```python
# craft.py, depois de montar_opcoes_craft(...)
validos, bloqueados = {}, {}
for nome, conj in conjuntos.items():
    ok, motivos = validar(conj, ctx)
    (validos if ok else bloqueados)[nome] = motivos if not ok else conj
conjuntos = {n: conjuntos[n] for n in validos}
opcoes = {n: opcoes[n] for n in validos}
# devolver `bloqueados` agrupados por item para a tela: "Pés · Ataduras de Raiz… — embutido;
# para usar, troque um dos seus embelezados (Peito ou Mãos)".
```
**Aceite (teste):** base com 2 embutidos + candidato embutido em outro slot → não aparece em
`pecas` com ganho; aparece em `bloqueados`. Base com 1 embutido → o mesmo candidato é medido.

### 4.3 P-050 — Fase 2: "trocar" quando já está no teto
Para cada embelezamento E aplicável e cada `EmbelezadoAtual` **aplicado** (não embutido) no slot S:
candidato = o item equipado em S com o bônus do embelezamento atual removido e `E` aplicado. Medir
todos numa leitura só, contra a base (P4). Resultado por linha: "Trocar Forro de Arcanotrama
(Ombros) por Presa Adornada: +0,4%".

```python
def trocar_embelezamento(base: Conjunto, atual: EmbelezadoAtual, novo: Embelezamento) -> Conjunto:
    c = base.itens[atual.slot]
    bonus = [b for b in (c.bonus_ids or []) if b != atual.aplicado.bonus_id]
    novo_item = c.model_copy(update={"bonus_ids": bonus, "embelezamento_simc": novo.token_simc,
                                     "embelezamento": True})
    return base.com_troca(atual.slot, novo_item)
```
Se os 2 atuais forem **embutidos** (caso do usuário hoje: peito e mãos), não há o que trocar sem
trocar a peça: então meça "peça craftada não embutida + E" no slot de um dos embutidos (substitui a
peça embutida inteira) e mostre como "trocar a peça embutida X por <peça> com E". Teste com o
simulador falso de `tests/test_craft.py` (`_Sim`), que já soma valor por `embelezamento_simc`.

### 4.4 P-051 — Atributos reais das peças craftadas (sonda no simc)
Uma execução curta com **uma cópia do personagem por candidato** (`copy=`), `iterations=1`, e ler
`players[i].gear`. Conferido: `gear_to_json` é chamado **fora** do bloco `if report_details`
(`report_json.cpp:893`), então sai com o `report_details=0` que o runner já passa.

```python
# masmorras/sonda.py
def sondar_atributos(personagem, candidatos: dict[str, Candidato], *, fight_style, simc_path=None) -> dict[str, dict[str, int]]:
    """nome -> {"crit": 812, "haste": 640, "intellect": 1404, ...} do item no ilvl/missiva pedidos."""
    linhas = [serializar_texto(personagem, incluir_checksum=False)]
    nomes = list(candidatos)
    for i, nome in enumerate(nomes):
        linhas += [f'copy=sonda_{i}', _linha_item(candidatos[nome])]
    arquivo = sr.CACHE_DIR / "sonda" / f"{hashlib.sha1(''.join(linhas).encode()).hexdigest()[:16]}.simc"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text("\n".join(linhas), encoding="utf-8")
    execucao = sr.run_simc(arquivo, iterations=1, fight_style=fight_style, extra_args=["max_time=1"])
    jogadores = sr.read_results(execucao.json_path).bruto["sim"]["players"]
    # jogadores[0] é o original; jogadores[i+1] é a sonda i. O slot é o do candidato.
    ...
```
Mapear as chaves do simc (`util::stat_type_string`: `crit_rating`, `haste_rating`,
`mastery_rating`, `versatility_rating`, `intellect`, `stamina`…) para as do projeto (`crit`,
`haste`, …) e mandar em `pecas[i].stats`. Na tela, `ResultadoCraft` passa `stats={p.stats}` ao
`ItemIcone`. **Aceite:** tooltip da peça craftada mostra Intelecto + os dois secundários da missiva.

### 4.5 P-051 (UI) — Fonte e slot na tooltip
- `ItemIcone` aceita `fonte?: string` e repassa ao `showTooltip` (`sourceLocation`, `roleTag`):
  craft → `"Craft (Mítico Q5)"` / `roleTag: "Craftado"`; cofre → `"Grande Cofre"`.
- `itemTooltipService.ts:1069-1070`: sem fonte conhecida, mostrar `"Fonte não informada"`, nunca
  `"Masmorra M+"` por padrão (é um palpite apresentado como fato — P1).
- Slot: passar `slotPt(slot)` (de `components/masmorras/rotulos.ts`) em vez do valor cru.

### 4.6 P-053 — Aviso do .inv
```python
# masmorras_worker.py: separar informação de aviso
informacoes = [a.detalhe for a in combo.avisos if a.codigo == "combinar_inv_mesclado"]
avisos = [a.detalhe for a in combo.avisos if a.severidade != "info"]
# RankingResult ganha `informacoes: list[str]`; a tela mostra em texto-3, não em âmbar.
```

## 5. Checklist

| # | Tarefa | Status | Commit |
| :-: | :--- | :-: | :-- |
| A1 | P-052 embelezados do conjunto (+ `bonus_id` em `Embelezamento`) | [ ] | |
| A2 | P-049 fase 1 valida o teto; bloqueados na saída e na tela | [ ] | |
| A3 | P-050 fase 2 "trocar" (aplicado → troca o reagente; embutido → troca a peça) | [ ] | |
| A4 | P-051 sonda de atributos no simc + `stats` nas peças | [ ] | |
| A5 | P-051 tooltip: fonte/slot corretos, sem "Masmorra M+" de palpite | [ ] | |
| A6 | P-053 informação do .inv fora dos avisos | [ ] | |
| A7 | Rodar o Craft no Windows com o perfil do usuário e anexar o log (T10): conferir que `embellishment=` não gera "unknown embellishment" | [ ] | |

**Ordem:** A1 → A2 → A3 (mudam os números; são o que importa) → A4 → A5 → A6 → A7.
