# Exemplos ponta a ponta

Os dois exemplos abaixo foram gerados executando o pipeline real
(`PlaninngAgent.plan()`, exatamente o código de produção) contra um
LLM "roteirizado" (respostas JSON fixas por chamada), já que este
ambiente de desenvolvimento não tem uma chave de API configurada. Tudo o
que aparece abaixo — parsing de JSON, construção dos dataclasses,
`_infer_depth()`, `_detect_scale_hints()`/`_cross_check_complexity()` e
`to_prompt_section()` — é o comportamento real do agente; só o *conteúdo*
das respostas do modelo é simulado. O script usado está descrito no fim
deste documento para reprodutibilidade.

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

**Estratégia:** ler A e B e imprimir A + B -- Problema de complexidade trivial; não há decisão algorítmica a fazer.

**Complexidade estimada:** tempo O(1), espaço O(1) (apenas leitura e uma soma)

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
- Limites sugerem escala ~1e+09; soluções O(N log N) ou melhores provavelmente são necessárias.

**Checklist de verificação:**
- [ ] testar com A e B negativos
- [ ] testar com A + B próximo do limite de 32 bits
```

`metadata`: `TokenUsage(model='gpt-4o-mini', prompt_tokens=982,
completion_tokens=277, total_tokens=1259, elapsed_seconds=7.2, ...)`

> **Limitação conhecida da heurística proativa:** o segundo risco acima
> ("Limites sugerem escala ~1e+09...") é um **falso positivo** de
> `_detect_scale_hints()` (`agents/plannig_agent/main.py`). A heurística
> pega qualquer número grande no enunciado/especificação de entrada, sem
> distinguir "N" (tamanho da entrada, relevante para complexidade) de "A,
> B" (valores dos dados, irrelevantes para complexidade de um O(1)). É uma
> limitação real da v1, deixada assim de propósito em vez de uma regra
> mais frágil tentando adivinhar nomes de variáveis — documentamos aqui em
> vez de mascarar.

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
- Limites sugerem escala ~2e+05; evite complexidade O(N^2) ou pior sem justificativa explícita.

**Checklist de verificação:**
- [ ] testar N=1
- [ ] testar destino inalcançável (grafo desconexo)
- [ ] testar arestas paralelas
- [ ] testar peso 0
- [ ] confirmar se o grafo é direcionado ou não com um caso de teste específico
```

`metadata`: `TokenUsage(model='gpt-4o-mini', prompt_tokens=1354,
completion_tokens=773, total_tokens=2127, elapsed_seconds=7.2, ...)`

Note que, diferente do exemplo 1, aqui a etapa 1 (`understanding`)
detectou uma **ambiguidade real** (grafo direcionado ou não) que a etapa 4
(`review`) trouxe de volta como risco concreto — exatamente o tipo de
armadilha que o pipeline zero-shot original deixava passar direto para o
código.

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

## Reprodutibilidade

Os dois exemplos acima foram gerados com um `ScriptedLLM` de teste (mesma
ideia do `FakeLLM` em `tests/conftest.py`, mas com respostas mais ricas)
injetado em `PlaninngAgent(llm=...)`. Isso é possível porque `PlaninngAgent`
recebe o cliente `LLM` por injeção de dependência — nenhuma chamada de
rede real foi feita. Para gerar plantas reais, basta configurar
`PLANNER__API_KEY`/`PLANNER__BASE_URL`/`PLANNER__MODEL_NAME` (ou as
variáveis `API_KEY`/`BASE_URL`/`MODEL` já existentes) em `.env` e chamar
`PlaninngAgent().plan(problem)` normalmente, como em `main.py`.
