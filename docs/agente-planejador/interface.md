# Interface do Agente Planejador

Contrato de entrada/saída de `PlaninngAgent` (`agents/plannig_agent/`).
Todos os tipos são `dataclasses` da stdlib — o repositório não usa
`pydantic` em nenhum outro lugar (única dependência de terceiros hoje é o
SDK `openai` + `python-dotenv`), então mantivemos zero dependências novas
em vez de introduzir um padrão de validação que não existe no resto do
projeto. `PlannerInput.validate()` faz a validação mínima de campos
obrigatórios manualmente.

## Entrada: `PlannerInput`

Definido em [`agents/plannig_agent/schemas.py`](../../agents/plannig_agent/schemas.py).

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `problem_id` | `str` | sim | Identificador do problema. |
| `statement` | `str` | sim | Enunciado, em texto. |
| `input_spec` | `Optional[str]` | não | Especificação do formato de entrada. |
| `output_spec` | `Optional[str]` | não | Especificação do formato de saída. |
| `examples` | `list[TestCaseExample]` | não (default `[]`) | Pares entrada/saída de exemplo. |
| `images_base64` | `list[str]` | não (default `[]`) | Imagens como *data URI* completa (`data:image/png;base64,...`). |
| `difficulty` | `Optional[str]` | não | Ex.: `"facil"`, `"medio"`, `"dificil"`. Usado por `_infer_depth()`. |
| `time_limit_seconds` | `Optional[float]` | não | Limite de tempo do Judge, se conhecido. |
| `memory_limit_mb` | `Optional[float]` | não | Limite de memória do Judge, se conhecido. |
| `previous_attempts` | `list[JudgeAttemptFeedback]` | não (default `[]`) | Histórico de veredito do Judge, usado no ciclo de `replan()`. |

`TestCaseExample`: `input: str`, `output: str`, `explanation: Optional[str] = None`.

`JudgeAttemptFeedback`: `attempt_number: int`, `verdict: str` (`"AC" | "WA" | "CE" | "RE" | "TLE"`),
`details: Optional[str] = None`, `failing_test_case: Optional[str] = None`.

Validação: `PlannerInput.validate()` levanta `MissingRequiredFieldError`
se `problem_id` ou `statement` estiverem ausentes/vazios. É chamada
automaticamente no início de `PlaninngAgent.plan()`.

> **Formato de imagem**: o pipeline não tinha, antes deste trabalho, um
> formato de imagem estabelecido (o artigo menciona Base64 apenas
> conceitualmente). Definimos aqui que `images_base64` guarda *data URIs*
> completas e autodescritivas (`data:image/<formato>;base64,<dados>`), que
> é o formato que a API multimodal do OpenAI/OpenRouter espera em
> `image_url.url` — ver `LLM._build_user_content()` em
> `services/llm_service.py`.

### Exemplo sem imagem

```python
from agents.plannig_agent import PlannerInput, TestCaseExample

problem = PlannerInput(
    problem_id="obi-exemplo-01",
    statement=(
        "Dada uma lista de N inteiros, determine a soma máxima de um "
        "subvetor contíguo não vazio."
    ),
    input_spec="A primeira linha contém N (1 <= N <= 200000). A segunda linha contém N inteiros.",
    output_spec="Um único inteiro: a soma máxima encontrada.",
    examples=[TestCaseExample(input="4\n-2 1 -3 4", output="4")],
    difficulty="medio",
)
```

### Exemplo com imagem (problema de grafos)

```python
from agents.plannig_agent import PlannerInput, TestCaseExample

problem = PlannerInput(
    problem_id="obi-exemplo-grafo-02",
    statement=(
        "O mapa de uma cidade é representado pelo grafo da figura, onde "
        "vértices são cruzamentos e arestas são ruas com peso igual à "
        "distância em metros. Determine o menor caminho do vértice 1 até o vértice N."
    ),
    input_spec="N (vértices, 1 <= N <= 100000), M (arestas), seguido de M linhas 'u v w'.",
    output_spec="Distância mínima de 1 até N, ou -1 se inalcançável.",
    examples=[TestCaseExample(input="4 4\n1 2 3\n2 4 1\n1 3 5\n3 4 1", output="4")],
    images_base64=["data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB..."],
    difficulty="dificil",
    time_limit_seconds=2.0,
    memory_limit_mb=256,
)
```

## Saída: `PlannerOutput`

| Campo | Tipo | Descrição |
|---|---|---|
| `problem_id` | `str` | Ecoa `PlannerInput.problem_id`. |
| `understanding` | `ProblemUnderstanding` | Etapa 1 de Pólya. |
| `plan` | `SolutionPlan` | Etapa 2 de Pólya. |
| `execution_sketch` | `ExecutionSketch` | Etapa 3 de Pólya (pseudocódigo). |
| `review` | `PlanReview` | Etapa 4 de Pólya. |
| `metadata` | `TokenUsage` | Custo/tokens/tempo agregados das 4 chamadas de LLM. |
| `iteration` | `int` | 1 na primeira chamada a `plan()`; incrementa a cada `replan()`. |

`ProblemUnderstanding`: `restatement: str`, `inputs_description: str`,
`outputs_description: str`, `constraints: list[str]`,
`visual_elements: Optional[str]`, `ambiguities: list[str]`.

`SolutionPlan`: `algorithmic_pattern: str`, `candidate_strategies: list[str]`,
`chosen_strategy: str`, `strategy_justification: str`,
`complexity: ComplexityEstimate`, `corner_cases: list[str]`.

`ComplexityEstimate`: `time_complexity: str`, `space_complexity: str`, `justification: str`.

`ExecutionSketch`: `pseudocode: str`, `data_structures: list[str]`, `key_steps: list[str]`,
`traced_outputs: list[str]` (simulação manual do pseudocódigo, um item por
`PlannerInput.examples`, na mesma ordem — pedida ao LLM, mas comparada
contra a saída real em código, não confiada cegamente).

`PlanReview`: `risks: list[str]`, `verification_checklist: list[str]`,
`confidence: str` (`"low" | "medium" | "high"`), mais três campos
**calculados em código** (não pelo LLM) por
`PlaninngAgent._apply_deterministic_checks()`:

- `trace_checks: list[TraceCheck]` — um `TraceCheck` por exemplo
  (`example_index`, `expected_output`, `traced_output`, `matches: bool`),
  comparando `execution_sketch.traced_outputs` contra a saída real.
- `complexity_feasible: Optional[bool]` + `complexity_budget_note: Optional[str]`
  — resultado de um cálculo de orçamento de operações (`time_limit_seconds
  × ~10^8 op/s`) vs. a complexidade escolhida para o N detectado no
  enunciado. `None` quando nenhuma escala pôde ser detectada.
- `justification_quality_issues: list[str]` — problemas estruturais
  encontrados na justificativa (curta demais, sem número, sem comparação
  com alternativa descartada); lista vazia = nenhum problema.

Se qualquer uma dessas três checagens falhar, `confidence` é forçado para
`"low"` em código, mesmo que o LLM tenha reportado `"high"` na etapa 4 —
ver [`visao-geral.md`](visao-geral.md#checagens-determinísticas-código-não-llm).

`TokenUsage`: `model: str`, `prompt_tokens: int`, `completion_tokens: int`,
`total_tokens: int`, `input_cost_usd: Optional[float]`,
`output_cost_usd: Optional[float]`, `total_cost_usd: Optional[float]`,
`elapsed_seconds: float`.

### Exemplo de payload de resposta

```python
PlannerOutput(
    problem_id="obi-exemplo-01",
    understanding=ProblemUnderstanding(
        restatement="Encontrar o subvetor contíguo de soma máxima em um vetor de N inteiros.",
        inputs_description="N inteiros, podendo incluir negativos.",
        outputs_description="Um único inteiro: a soma máxima encontrada.",
        constraints=["1 <= N <= 200000"],
        visual_elements=None,
        ambiguities=[],
    ),
    plan=SolutionPlan(
        algorithmic_pattern="programação dinâmica (Kadane)",
        candidate_strategies=["força bruta O(N^2)", "kadane O(N)"],
        chosen_strategy="kadane",
        strategy_justification="O(N) atende folgadamente ao limite de N <= 200000",
        complexity=ComplexityEstimate(
            time_complexity="O(N)", space_complexity="O(1)",
            justification="uma única passada pelo vetor, sem estruturas auxiliares",
        ),
        corner_cases=["todos os elementos negativos", "N = 1"],
    ),
    execution_sketch=ExecutionSketch(
        pseudocode="best = arr[0]; cur = arr[0]\nfor x in arr[1:]:\n  cur = max(x, cur + x)\n  best = max(best, cur)",
        data_structures=[],
        key_steps=["inicializar best e cur com arr[0]", "iterar e atualizar cur", "atualizar best"],
        traced_outputs=["4"],
    ),
    review=PlanReview(
        risks=["overflow em linguagens com inteiro de tamanho fixo"],
        verification_checklist=["testar vetor com todos negativos", "testar N=1"],
        confidence="high",
        trace_checks=[TraceCheck(example_index=0, expected_output="4", traced_output="4", matches=True)],
        complexity_feasible=True,
        complexity_budget_note=(
            "Orçamento de complexidade: N~2e+05, limite de tempo assumido (não informado) de 1.0s "
            "-> orçamento ~1e+08 operações; complexidade 'O(N)' estimada em ~2e+05 operações "
            "(dentro do orçamento)."
        ),
        justification_quality_issues=[],
    ),
    metadata=TokenUsage(
        model="gpt-4o-mini", prompt_tokens=1840, completion_tokens=620, total_tokens=2460,
        input_cost_usd=0.000276, output_cost_usd=0.000372, total_cost_usd=0.000648,
        elapsed_seconds=6.42,
    ),
    iteration=1,
)
```

`PlannerOutput.to_prompt_section()` renderiza esse objeto como um bloco
Markdown `## Plano de Resolução (...)` pronto para ser injetado no prompt
do Agente Codificador — ver [`integracao.md`](integracao.md).

## Erros

Definidos em [`agents/plannig_agent/errors.py`](../../agents/plannig_agent/errors.py),
todos derivam de `PlannerError`:

| Exceção | Quando ocorre | O que o chamador deve fazer |
|---|---|---|
| `MissingRequiredFieldError` | `problem_id` ou `statement` ausentes/vazios em `PlannerInput.validate()`. | Erro do chamador (Orquestrador) — corrigir o payload antes de chamar `plan()`. Não adianta tentar de novo sem mudar a entrada. |
| `PlannerTimeoutError` | A chamada ao LLM em alguma das 4 etapas excede `timeout` (padrão 60s, configurável no construtor de `PlaninngAgent`). | Pode tentar novamente (transiente) ou aumentar o timeout. A etapa que falhou está na mensagem da exceção. |
| `PlannerMalformedResponseError` | O LLM não devolveu um JSON válido, ou o JSON não tinha as chaves obrigatórias daquela etapa. Expõe `.stage` (nome da etapa) e `.raw_response` (texto bruto recebido, truncado em 300 chars na mensagem). | Logar `.stage` e `.raw_response` para depuração de prompt; normalmente resolve com um retry (o modelo às vezes ignora a instrução de "só JSON"). |
| `PlannerError` | Erro genérico na chamada ao LLM (`openai.APIError`) que não é timeout. | Tratar como falha de infraestrutura/provedor; logar e decidir retry conforme política do Orquestrador. |

Nenhuma etapa é reexecutada automaticamente dentro do Agente Planejador —
toda política de retry fica a critério do chamador (Orquestrador), que tem
mais contexto sobre orçamento de tempo/custo da execução em lote.
