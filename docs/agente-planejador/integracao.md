# Integração com o Orquestrador, o Agente Codificador e o Judge

## Estado atual do repositório

Hoje não existe um Orquestrador dedicado, nem Judge, nem Agente
Codificador implementados — o mais próximo de um "Orquestrador" é
[`main.py`](../../main.py), que hoje serve como script de demonstração do
pipeline. É nele que a integração está demonstrada concretamente:

```python
from agents import PlaninngAgent
from agents.plannig_agent import PlannerInput, TestCaseExample
from prompt_templates import build_coder_prompt

planning = PlaninngAgent()

problem = PlannerInput(
    problem_id="obi-exemplo-01",
    statement="...",
    input_spec="...",
    output_spec="...",
    examples=[TestCaseExample(input="4\n-2 1 -3 4", output="4")],
    difficulty="medio",
)

plan = planning.plan(problem)                       # Problema -> Agente Planejador
coder_prompt = build_coder_prompt(problem.statement, plan)  # Plano -> prompt do Codificador

# TODO quando o Agente Codificador existir:
# code = coding_agent.generate(coder_prompt)
# verdict = judge.evaluate(code, problem)
```

Quando um Orquestrador mais completo existir (carregando problemas do
banco da OBI, iterando sobre modelos, etc.), o ponto de integração é o
mesmo: chamar `PlaninngAgent().plan(planner_input)` entre a seleção do
problema e a chamada ao Agente Codificador.

## Como o plano é injetado no prompt do Agente Codificador

`PlannerOutput.to_prompt_section()` (em
[`agents/plannig_agent/schemas.py`](../../agents/plannig_agent/schemas.py))
renderiza as 4 seções de Pólya como um bloco Markdown único, começando com
`## Plano de Resolução (...)`. `build_coder_prompt()` (em
[`prompt_templates/coder_prompt.py`](../../prompt_templates/coder_prompt.py))
concatena: enunciado → plano → instrução final de gerar código, exatamente
nessa ordem, para que o modelo veja o raciocínio estruturado antes da
instrução final:

```python
def build_coder_prompt(statement: str, plan: PlannerOutput) -> str:
    return (
        f"## Enunciado\n{statement}\n\n"
        f"{plan.to_prompt_section()}\n\n"
        f"## Instrução final\n{CODER_INSTRUCTIONS}"
    )
```

Quando o `ExecutationAgent` (futuro Agente Executor/Codificador, ver
[`docs/agentes/agente-execucao.md`](../agentes/agente-execucao.md)) for
implementado, ele deve receber essa string pronta e passá-la para
`LLM.send_prompt()` (ou `send_prompt_with_usage()`, se também quiser
reportar custo/tokens) — sem nenhum reprocessamento manual do plano.

## Ciclo de feedback com o Judge

O contrato já suporta o ciclo iterativo descrito no artigo como trabalho
futuro, mesmo sem um Judge implementado ainda:

1. O Judge (quando existir) devolve um veredito por tentativa: `AC`,
   `WA`, `CE`, `RE` ou `TLE`.
2. Um veredito negativo vira um `JudgeAttemptFeedback` (
   `agents/plannig_agent/schemas.py`):
   ```python
   feedback = JudgeAttemptFeedback(
       attempt_number=1,
       verdict="TLE",
       details="excedeu o tempo limite no caso de teste 7 (N = 10^5)",
       failing_test_case="caso_07.txt",
   )
   ```
3. O Orquestrador chama `PlaninngAgent.replan(planner_input, feedback)` em
   vez de `.plan(...)`. Isso anexa o feedback a
   `planner_input.previous_attempts` e roda o ciclo de Pólya de novo — cada
   um dos 4 prompts (`prompts.py::_feedback_block()`) recebe o histórico de
   tentativas, então o modelo é explicitamente instruído a: se houve TLE,
   priorizar uma estratégia de complexidade menor na etapa 2; se houve WA,
   revisar corner cases e a interpretação do enunciado; se houve CE/RE,
   revisar suposições sobre tipos e limites.
4. `PlannerOutput.iteration` é incrementado a cada rodada
   (`len(previous_attempts) + 1`), permitindo ao Orquestrador limitar o
   número de iterações (ex.: parar após 3 tentativas).

```python
verdict = judge.evaluate(code, problem)  # quando o Judge existir
if verdict.status != "AC" and iteration < MAX_ITERATIONS:
    plan = planning.replan(planner_input, JudgeAttemptFeedback(
        attempt_number=iteration, verdict=verdict.status, details=verdict.message,
    ))
```

A v1 sempre replaneja o ciclo inteiro (as 4 etapas), o que é
deliberadamente simples: é o ponto de extensão natural para uma política
mais fina por tipo de veredito (ex.: TLE → reexecutar só a etapa 2 e 3,
sem gastar uma chamada de LLM reformulando a etapa 1, que não mudou).

## Variáveis de ambiente

O repositório usava, antes deste componente, apenas `API_KEY`, `BASE_URL`
e `MODEL` sem prefixo (ver [`.env.example`](../../.env.example)) — não
havia um padrão `NOME__*` nem variáveis de preço estabelecidas. Para o
Agente Planejador, introduzimos um prefixo `PLANNER__` seguindo o padrão
`NOME__API_KEY` / `NOME__BASE_URL` / `NOME__MODEL_NAME` /
`NOME__INPUT_PRICE` / `NOME__OUTPUT_PRICE`, com fallback para as variáveis
sem prefixo quando as `PLANNER__*` não estiverem definidas — isso permite
usar o mesmo provedor/modelo do resto do pipeline por padrão, ou apontar o
estágio de planejamento para um modelo diferente (ex.: mais barato, já que
ele faz 4 chamadas por problema) sem mexer em código:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `PLANNER__API_KEY` | não (fallback `API_KEY`) | Chave da API do provedor usado pelo Agente Planejador. |
| `PLANNER__BASE_URL` | não (fallback `BASE_URL`) | Endpoint compatível com a API OpenAI (ex.: OpenRouter). |
| `PLANNER__MODEL_NAME` | não (fallback `MODEL`) | Identificador do modelo. |
| `PLANNER__INPUT_PRICE` | não (default `0.0`) | Preço em USD por 1 milhão de tokens de entrada, usado em `TokenUsage.input_cost_usd`. |
| `PLANNER__OUTPUT_PRICE` | não (default `0.0`) | Preço em USD por 1 milhão de tokens de saída, usado em `TokenUsage.output_cost_usd`. |

Essas variáveis (com fallback para as versões sem prefixo) só passam a
valer a partir do momento em que alguém instancia `PlaninngAgent()` sem
passar um `LLM` explícito — quem já tem um cliente `LLM` configurado pode
continuar injetando-o via `PlaninngAgent(llm=meu_llm)`, ignorando
totalmente as variáveis de ambiente (é assim que os testes em
`tests/conftest.py` funcionam, com um `FakeLLM`).

Sugerimos que outros agentes futuros sigam a mesma convenção
`<AGENTE>__*` — ver [`docs/agentes/visao-geral.md`](../agentes/visao-geral.md).
