# Exemplos ponta a ponta

Os dois exemplos abaixo foram gerados executando o pipeline real
(`PlaninngAgent.plan()`, exatamente o código de produção) contra um
LLM "roteirizado" (respostas JSON fixas por chamada), já que este
ambiente de desenvolvimento não tem uma chave de API configurada. Tudo o
que aparece abaixo — parsing de JSON, construção dos dataclasses,
`_infer_depth()`, as três checagens determinísticas
(`_verify_trace_against_examples()`, `_estimate_complexity_budget()`,
`_assess_justification_quality()`) e `to_prompt_section()` — é o
comportamento real do agente; só o *conteúdo* das respostas do modelo é
simulado. O script usado está descrito no fim deste documento para
reprodutibilidade.

## Exemplo 1 — problema fácil, sem imagem

### Entrada (`PlannerInput`)

```python
PlannerInput(
    problem_id="obi-facil-01",
    statement="Leia dois inteiros A e B e imprima a soma A + B.",
    input_spec="Uma linha contendo dois inteiros A e B (-10^9 <= A, B <= 10^9).",
    output_spec="Um único inteiro: o valor de A + B.",
    examples=[TestCaseExample(input="3 5", output="8"), TestCaseExample(input="-4 10", output="6")],
    difficulty="facil",
)
```

`_infer_depth()` classificou este problema como **`concise`** (sem
imagens, dificuldade "facil", sem palavras-chave de grafo/DP no
enunciado).

### Saída (`PlannerOutput.to_prompt_section()`)

```
## Plano de Resolução (gerado pelo Agente Planejador, método de Pólya)

### 1. Compreensão do problema
Ler dois inteiros A e B e imprimir a soma A + B.

**Entrada:** Uma linha com dois inteiros A e B, separados por espaço.

**Saída:** Um único inteiro: a soma A + B.

### 2. Estratégia escolhida
**Padrão algorítmico:** leitura e aritmética direta

**Estratégia:** ler A e B e imprimir A + B -- Problema de complexidade trivial (O(1)): mesmo com A, B em até 10^9 em módulo, a soma cabe em um inteiro de 64 bits, então não há decisão algorítmica real a fazer.

**Complexidade estimada:** tempo O(1), espaço O(1) (apenas leitura e uma soma, sem laços)

**Corner cases a tratar:**
- A e/ou B negativos
- A + B ultrapassando 32 bits (usar tipo de 64 bits)

### 3. Pseudocódigo
```
ler A, B
imprimir A + B
```

### 4. Riscos e checklist de verificação
**Riscos:**
- nenhum risco relevante dado o tamanho do problema

**Checklist de verificação:**
- [ ] testar com A e B negativos
- [ ] testar com A + B próximo do limite de 32 bits
```

`metadata`: `TokenUsage(model='gpt-4o-mini', prompt_tokens=1330,
completion_tokens=314, total_tokens=1644, elapsed_seconds=7.2, ...)`

### Checagens determinísticas (não aparecem no texto acima, mas ficam em `review`)

```python
review.trace_checks = [
    TraceCheck(example_index=0, expected_output="8", traced_output="8", matches=True),
    TraceCheck(example_index=1, expected_output="6", traced_output="6", matches=True),
]
review.complexity_feasible = None       # nenhuma escala de N detectada -- ver nota abaixo
review.complexity_budget_note = None
review.justification_quality_issues = []
```

> **Por que `complexity_feasible` é `None` aqui, e não um risco:**
> `-10^9 <= A, B <= 10^9` é um limite de **valor**, não de **tamanho de
> entrada** — não existe "N" neste problema (a entrada tem sempre
> exatamente dois números). `_extract_scale()` ancora a busca em
> variáveis de tamanho canônicas (`N`, `M`, `Q`, `K`, `T` seguidas de
> `<=`) exatamente para não confundir os dois. Numa versão anterior deste
> mecanismo (baseada em casar qualquer número grande no texto, sem essa
> âncora), este exemplo gerava um falso positivo — um risco de
> "complexidade" para um problema O(1) trivial. O comportamento atual
> (`None` = "não há base pra julgar", em vez de arriscar um palpite errado)
> é o resultado de corrigir esse problema.

## Exemplo 2 — problema de grafos, com imagem

### Entrada (`PlannerInput`)

```python
PlannerInput(
    problem_id="obi-grafo-02",
    statement=(
        "O mapa de uma cidade é representado pelo grafo da figura, onde vértices "
        "são cruzamentos e arestas são ruas com peso igual à distância em metros. "
        "Determine a menor distância entre o cruzamento 1 e o cruzamento N."
    ),
    input_spec="N (1 <= N <= 100000), M (1 <= M <= 200000), seguido de M linhas 'u v w' (0 <= w <= 10^4).",
    output_spec="Um inteiro: a menor distância de 1 até N, ou -1 se inalcançável.",
    examples=[TestCaseExample(input="4 4\n1 2 3\n2 4 1\n1 3 5\n3 4 1", output="4",
                               explanation="Caminho 1-2-4 com custo 3+1=4.")],
    images_base64=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB..."],
    difficulty="dificil",
    time_limit_seconds=2.0,
    memory_limit_mb=256,
)
```

`_infer_depth()` classificou este problema como **`detailed`** (imagem
presente + dificuldade "dificil" + palavra-chave "grafo" no enunciado —
qualquer um dos três já bastaria).

### Saída (`PlannerOutput.to_prompt_section()`)

```
## Plano de Resolução (gerado pelo Agente Planejador, método de Pólya)

### 1. Compreensão do problema
Dado um grafo ponderado com N cruzamentos e M ruas (arestas), representado na figura, determinar a menor distância total do cruzamento 1 até o cruzamento N.

**Entrada:** N, M, seguidos de M linhas 'u v w' descrevendo uma rua entre u e v com distância w.

**Saída:** A menor distância de 1 até N, ou -1 se N for inalcançável a partir de 1.

### 2. Estratégia escolhida
**Padrão algorítmico:** grafos -- caminho mínimo (Dijkstra)

**Estratégia:** Dijkstra com heap binária -- Pesos não negativos (0 <= w <= 10^4) permitem Dijkstra; com N, M até 10^5/2*10^5, O((N+M) log N) é a única opção que cabe no limite de 2s -- Floyd-Warshall é inviável e Bellman-Ford é folgado demais para o limite de tempo.

**Complexidade estimada:** tempo O((N + M) log N), espaço O(N + M) (lista de adjacência + heap binária padrão de Dijkstra)

**Corner cases a tratar:**
- N = 1 (origem == destino, distância 0)
- vértice N inalcançável a partir de 1 (retornar -1)
- arestas paralelas entre o mesmo par de vértices (manter a de menor peso)
- grafo desconexo
- peso 0 em alguma aresta

### 3. Pseudocódigo
```
ler N, M
construir lista de adjacencia adj[1..N]
para cada uma das M linhas: ler u, v, w; adj[u].append((v,w)); adj[v].append((u,w))
dist[1..N] = infinito; dist[1] = 0
heap = [(0, 1)]
enquanto heap não vazio:
  (d, u) = pop_min(heap)
  se d > dist[u]: continue
  para (v, w) em adj[u]:
    se dist[u] + w < dist[v]:
      dist[v] = dist[u] + w
      heap.push((dist[v], v))
imprimir dist[N] se dist[N] != infinito senao -1
```

### 4. Riscos e checklist de verificação
**Riscos:**
- se o grafo for direcionado (ambiguidade detectada na etapa 1), a lista de adjacência precisa ser construída só no sentido u->v
- overflow se a soma de pesos ao longo do caminho for acumulada em tipo de 32 bits

**Checklist de verificação:**
- [ ] testar N=1
- [ ] testar destino inalcançável (grafo desconexo)
- [ ] testar arestas paralelas
- [ ] testar peso 0
- [ ] confirmar se o grafo é direcionado ou não com um caso de teste específico
```

`metadata`: `TokenUsage(model='gpt-4o-mini', prompt_tokens=1711,
completion_tokens=780, total_tokens=2491, elapsed_seconds=7.2, ...)`

### Checagens determinísticas

```python
review.trace_checks = [
    TraceCheck(example_index=0, expected_output="4", traced_output="4", matches=True),
]
review.complexity_feasible = True
review.complexity_budget_note = (
    "Orçamento de complexidade: N~2e+05, limite de tempo informado de 2.0s "
    "-> orçamento ~2e+08 operações; complexidade 'O((N + M) log N)' "
    "estimada em ~4e+06 operações (dentro do orçamento)."
)
review.justification_quality_issues = []
```

Todas as três checagens passaram, e por isso `confidence` permaneceu
`"high"` (o valor que o próprio modelo reportou na etapa 4 não foi
sobrescrito). Note que `_approx_operations()` precisou tratar
`"O((N + M) log N)"` como um fator multiplicativo (`N * log2(N)`, não
`log2(N)` sozinho) — é justamente o tipo de notação com parênteses e soma
de duas variáveis que quebraria um casamento de substring mais ingênuo.

Note também que, diferente do exemplo 1, aqui a etapa 1
(`understanding`) detectou uma **ambiguidade real** (grafo direcionado ou
não) que a etapa 4 (`review`) trouxe de volta como risco concreto —
exatamente o tipo de armadilha que o pipeline zero-shot original deixava
passar direto para o código.

### Prompt final enviado ao Agente Codificador

`build_coder_prompt(problem.statement, plan)` produz:

```
## Enunciado
O mapa de uma cidade é representado pelo grafo da figura, onde vértices são cruzamentos e arestas são ruas com peso igual à distância em metros. Determine a menor distância entre o cruzamento 1 e o cruzamento N.

## Plano de Resolução (gerado pelo Agente Planejador, método de Pólya)
[... mesmo conteúdo do bloco acima ...]

## Instrução final
Você é um agente de programação competitiva. Escreva a solução final em Python 3, pronta para submissão, lendo da entrada padrão e escrevendo na saída padrão. Siga o plano de resolução acima, incluindo o tratamento dos corner cases listados. Responda apenas com o código, sem explicações adicionais.
```

## Um terceiro caso: quando as checagens determinísticas discordam do modelo

Os dois exemplos acima são "caminho feliz" — todas as checagens
concordaram com o que o modelo já tinha dito. O caso realmente
interessante é quando elas discordam; isso está coberto por testes
dedicados em vez de duplicado aqui (`tests/test_planning_agent.py`):

- `test_verify_trace_against_examples_detects_mismatch_and_downgrades_confidence`
  — o modelo simula o pseudocódigo e erra o exemplo; `trace_checks[i].matches`
  vira `False`, um risco descrevendo o esperado-vs-obtido é adicionado, e
  `confidence` é forçado para `"low"`.
- `test_complexity_budget_flags_infeasible_plan_and_downgrades_confidence`
  — o modelo escolhe `O(N^2)` para `N <= 10^6`; `complexity_feasible` vira
  `False`, com uma nota explicando o orçamento estourado.
- `test_justification_quality_gate_flags_generic_justification_and_downgrades_confidence`
  — o modelo justifica com "parece uma boa ideia" (sem número, sem
  comparação); `justification_quality_issues` lista os problemas
  estruturais encontrados.

Em todos os três casos, `review.confidence` é sobrescrito para `"low"`
em código — o valor que o LLM reportou na etapa 4 não é a última palavra.

## Reprodutibilidade

Os dois exemplos acima foram gerados com um `ScriptedLLM` de teste (mesma
ideia do `FakeLLM` em `tests/conftest.py`, mas com respostas mais ricas)
injetado em `PlaninngAgent(llm=...)`. Isso é possível porque `PlaninngAgent`
recebe o cliente `LLM` por injeção de dependência — nenhuma chamada de
rede real foi feita. Para gerar plantas reais, basta configurar
`PLANNER__API_KEY`/`PLANNER__BASE_URL`/`PLANNER__MODEL_NAME` (ou as
variáveis `API_KEY`/`BASE_URL`/`MODEL` já existentes) em `.env` e chamar
`PlaninngAgent().plan(problem)` normalmente, como em `main.py`.
