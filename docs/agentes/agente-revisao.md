# Agente Revisor

> **Status**: não implementado (stub `ReviewAgent` em
> `agents/review_agent/`, só com `print()` no `__init__`).

## Papel

Corresponde à etapa 4 de Pólya — *look back* — mas aplicada **depois** da
execução, sobre o código gerado e o veredito do Judge (quando existir), ou
sobre os testes locais do Agente Executor (na ausência de Judge). **Não
confundir** com `PlaninngAgent._look_back()`, que já existe e revisa o
*plano*, antes de qualquer código ser escrito — ver a distinção completa
em
[`visao-geral.md`](visao-geral.md#os-quatro-agentes-e-o-orquestrador).

A responsabilidade central deste agente é **tentar provar que a solução
está errada antes de aceitá-la** — não confirmar que parece certa.

## Entrada

| Campo | Tipo | Descrição |
|---|---|---|
| `problem` | `PlannerInput` | Problema original. |
| `plan` | `PlannerOutput` | Plano que originou o código — em particular `plan.review.risks` e `plan.plan.corner_cases`, para cruzar com o que de fato deu errado. |
| `solution` | `CandidateSolution` | Código gerado e resultado dos testes locais (ver [`agente-execucao.md`](agente-execucao.md#saída-candidatesolution)). |
| `judge_verdict` | `Optional[JudgeAttemptFeedback]` | Veredito do Judge, se já houver submissão real (`AC`/`WA`/`CE`/`RE`/`TLE`). |

## Saída: `ReviewResult`

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | `str` | `"PASSED"` \| `"FAILED"`. |
| `confidence` | `float` | Confiança do próprio Agente Revisor no diagnóstico (não confundir com a confiança do plano, que é do Planejador). |
| `errors` | `list[ReviewError]` | Problemas encontrados, cada um com `type` (`"logical"` \| `"complexity"` \| `"edge_case"` \| `"implementation"`) e `description`. |
| `counterexample` | `Optional[Counterexample]` | Uma entrada concreta (`input`, `expected`, `actual`) em que a solução falha, se encontrada. |
| `recommended_action` | `str` | `"ACCEPT"` \| `"REPLAN"` \| `"REEXECUTE"` \| `"ESCALATE_HUMAN"` — consumido pelo Orquestrador (ver [`visao-geral.md`](visao-geral.md#o-orquestrador)). |

## As quatro funções deste agente

1. **Verificação lógica** — o algoritmo, como implementado, realmente
   resolve o problema descrito em `ProblemSpecification`/`PlannerInput`?
2. **Análise de complexidade** — a solução passa dentro dos limites de
   tempo/memória reais (não a estimativa do Planejador, mas o resultado
   observado)?
3. **Edge cases** — a solução foi testada contra N=1, valores máximos e
   mínimos, duplicatas, entradas vazias, casos degenerados, overflow —
   cruzando com `plan.plan.corner_cases`, que já lista o que o Planejador
   esperava que fosse tratado?
4. **Teste adversarial (busca de contraexemplo)** — em vez de só rodar os
   exemplos dados, o agente tenta ativamente gerar uma entrada que quebre
   a solução (fuzzing dirigido pelos corner cases do plano, ou comparação
   contra uma solução de força bruta/oráculo para entradas pequenas).

## Por que a revisão não pode ser só outro LLM dizendo "OK"

Este é o risco central deste agente. Se o Planejador diz "a estratégia é
greedy e está correta" e o Revisor (outro LLM) diz "parece consistente",
o sistema tem **dois LLMs concordando**, não uma solução verificada — os
dois podem estar errados pelo mesmo motivo (o mesmo tipo de raciocínio
falho que gerou o plano).

Por isso, o Agente Revisor precisa combinar julgamento do LLM com
verificação **determinística**, sempre que uma estiver disponível:

| Sinal | Tipo | Fonte |
|---|---|---|
| "O raciocínio é consistente" | Neural (LLM) | O próprio Agente Revisor. |
| Compila | Determinístico | `CandidateSolution.compiled`. |
| Passa nos exemplos/testes ocultos | Determinístico | `CandidateSolution.local_test_results` / veredito do Judge. |
| Complexidade dentro do orçamento | Determinístico | Mesmo cálculo de orçamento de operações que `PlaninngAgent._estimate_complexity_budget()` já faz para o plano — aqui reaplicado ao tempo de execução *observado*, não estimado. |
| Solução coincide com um oráculo/força bruta para entradas pequenas | Determinístico | Requer implementar (ou gerar) uma solução de referência mais simples, mesmo que ineficiente, só para N pequeno. |
| Fuzzer não encontrou contraexemplo | Determinístico (mas não é prova) | Geração aleatória de entradas dentro dos limites, comparando com o oráculo. |

Esse é exatamente o mesmo princípio já aplicado no Agente Planejador —
`PlanReview.trace_checks`/`complexity_feasible`/`justification_quality_issues`
existem precisamente para não deixar a única fonte de verdade ser o LLM
se autoavaliando (ver
[`docs/agente-planejador/visao-geral.md#checagens-determinísticas-código-não-llm`](../agente-planejador/visao-geral.md#checagens-determinísticas-código-não-llm)).
O Agente Revisor é onde esse princípio importa mais, porque é a última
verificação antes de aceitar a solução.

## Decisão de próxima ação

`recommended_action` é o que permite ao Orquestrador diferenciar dois
tipos de falha bem diferentes, em vez de sempre "tentar de novo do zero":

- **`REPLAN`** — o plano em si estava errado (estratégia incompatível com
  os limites, corner case não previsto). Alimenta
  `PlaninngAgent.replan()` com um `JudgeAttemptFeedback` — mecanismo que
  já existe hoje, mesmo sem Agente Revisor implementado (ver
  [`docs/agente-planejador/integracao.md`](../agente-planejador/integracao.md#ciclo-de-feedback-com-o-judge)).
- **`REEXECUTE`** — o plano estava certo, mas a implementação tem um bug
  (ex.: erro de índice fora dos limites). Volta para o Agente Executor
  com o mesmo `PlannerOutput`, sem gastar uma chamada de replanejamento.
- **`ACCEPT`** — nenhum erro encontrado; `status = "PASSED"`.
- **`ESCALATE_HUMAN`** — o Orquestrador já esgotou o limite de iterações
  (ver [`visao-geral.md`](visao-geral.md#o-orquestrador)) sem chegar a
  `ACCEPT`.

## Métricas

Correspondem aos quatro critérios de avaliação da etapa "Revisar":

| Métrica | Definição | Como medir |
|---|---|---|
| Taxa de detecção de bugs | Fração de soluções realmente incorretas que o Revisor classifica como `FAILED`. | Requer gabarito (veredito real do Judge) para comparar contra o diagnóstico do Revisor. |
| Taxa de falsos positivos | Fração de soluções realmente corretas que o Revisor classifica como `FAILED`. | Idem — soluções `AC` no Judge que o Revisor rejeitou por engano. |
| Capacidade de encontrar contraexemplos | Fração de soluções incorretas em que `counterexample` não é nulo (o Revisor não só disse "está errado", mas mostrou uma entrada concreta). | Contagem direta sobre `ReviewResult.counterexample`. |
| Precisão da análise de complexidade | Diferença entre a complexidade que o Revisor reporta como observada e o tempo de execução real medido pelo sandbox. | Comparar `errors` do tipo `"complexity"` com o tempo/memória reais de `CandidateSolution`. |

Assim como as demais, essas métricas não têm coleta automatizada hoje —
dependem de um banco de problemas com gabarito e de um Judge real
existirem no pipeline.
