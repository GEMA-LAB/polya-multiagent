# Agente Planejador

> **Status**: implementado (`PlaninngAgent`, `agents/plannig_agent/`). Este
> arquivo é um resumo curto; a documentação completa vive em
> [`docs/agente-planejador/`](../agente-planejador/) e não é duplicada
> aqui.

## Papel

Corresponde às etapas 2, 3 e 4 de Pólya — *devise a plan*, *carry out the
plan* (como pseudocódigo, não código final) e *look back* (revisão do
plano, antes de qualquer código existir). Também absorve, internamente, a
etapa 1 (*understand*) — ver
[`agente-compreensao.md`](agente-compreensao.md#mapeamento-com-o-código-atual)
para o porquê dessa fusão.

## Entrada e saída

- **Entrada**: `PlannerInput` — enunciado, specs, exemplos, imagens,
  dificuldade, histórico de tentativas do Judge.
- **Saída**: `PlannerOutput` — as quatro seções de Pólya
  (`understanding`, `plan`, `execution_sketch`, `review`), metadados de
  custo (`TokenUsage`), e as checagens determinísticas descritas abaixo.

Contrato completo, com exemplos reais de payload, em
[`docs/agente-planejador/interface.md`](../agente-planejador/interface.md).

## Documentos

| Documento | Conteúdo |
|---|---|
| [`visao-geral.md`](../agente-planejador/visao-geral.md) | O que é, diagrama do pipeline, mapeamento das 4 etapas de Pólya e das características de agente inteligente para código. |
| [`interface.md`](../agente-planejador/interface.md) | Schema completo de entrada/saída, com tipos e exemplos. |
| [`exemplos.md`](../agente-planejador/exemplos.md) | Dois exemplos ponta a ponta (fácil sem imagem, grafos com imagem) rodados contra o código real. |
| [`integracao.md`](../agente-planejador/integracao.md) | Como o Orquestrador chama o agente, como o plano é injetado no prompt do Agente Executor, e o ciclo de feedback com o Judge (`replan()`). |

## As quatro métricas de "Planejar"

| Métrica | Como é sustentada hoje |
|---|---|
| Algoritmo correto | `PlanReview.trace_checks` — o modelo simula o pseudocódigo manualmente contra cada exemplo, e o código compara isso com a saída real esperada (não é o modelo se autodeclarando certo). Não substitui rodar no Judge, mas pega erros óbvios antes disso. |
| Complexidade correta | `PlanReview.complexity_feasible` / `.complexity_budget_note` — orçamento de operações calculado a partir de `time_limit_seconds` e do N detectado no enunciado, comparado com a complexidade escolhida. |
| Qualidade da justificativa | `PlanReview.justification_quality_issues` — checagem estrutural determinística (cita valor numérico do limite? compara com alternativa descartada?). |
| Taxa de soluções aceitas | **Não sustentada pelo Planejador isoladamente** — depende do código gerado pelo Agente Executor rodar no Judge. É uma métrica de sistema, não de agente; ver [`visao-geral.md`](visao-geral.md#métricas-do-sistema-completo). |

Se qualquer uma das três primeiras checagens falha, `review.confidence` é
forçado para `"low"` em código, mesmo que o LLM tenha reportado `"high"`
— ver
[`docs/agente-planejador/visao-geral.md#checagens-determinísticas-código-não-llm`](../agente-planejador/visao-geral.md#checagens-determinísticas-código-não-llm).
Esse padrão — nunca confiar só na autoavaliação do LLM, sempre cruzar com
um cálculo determinístico quando possível — é o mesmo que
[`agente-revisao.md`](agente-revisao.md) recomenda para o futuro Agente
Revisor.
