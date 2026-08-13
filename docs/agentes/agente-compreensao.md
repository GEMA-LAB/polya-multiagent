# Agente de Compreensão

> **Status**: não implementado como agente standalone. A responsabilidade
> semântica desta etapa (formalizar o enunciado) já é coberta hoje pela
> etapa 1 de Pólya *dentro* do Agente Planejador
> (`PlaninngAgent._understand()`) — ver
> [mapeamento com o código atual](#mapeamento-com-o-código-atual) antes de
> implementar isso como um agente separado, para não duplicar trabalho.

## Papel

Corresponde à etapa 1 de Pólya — *Understand the problem*. A
responsabilidade deste agente é **formalizar o problema, nunca resolvê-lo**.
Essa restrição é deliberada: um agente de compreensão que já começa a
pensar em algoritmo tende a fixar prematuramente uma estratégia (viés de
ancoragem), contaminando a etapa de planejamento. Seu único objetivo é
produzir uma representação estruturada boa o suficiente para que **outro
agente resolva o problema sem precisar reler o enunciado original**.

## Entrada

O problema bruto, como vem do banco de problemas da OBI:

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `problem_id` | `str` | sim | Identificador do problema. |
| `statement` | `str` | sim | Enunciado em texto. |
| `input_spec` / `output_spec` | `Optional[str]` | não | Especificação de entrada/saída, se vier separada do enunciado. |
| `examples` | `list[TestCaseExample]` | não | Pares entrada/saída de exemplo. |
| `images_base64` | `list[str]` | não | Imagens associadas (figuras de grafo, geometria, diagramas), como data URI. |

Este formato já existe em código como `PlannerInput` (ver
[`docs/agente-planejador/interface.md`](../agente-planejador/interface.md#entrada-plannerinput))
— um `ComprehensionAgent` standalone receberia exatamente o mesmo formato
de entrada, só que **antes** dos campos que dependem de compreensão já
terem sido preenchidos.

## Saída: `ProblemSpecification`

| Campo | Tipo | Descrição |
|---|---|---|
| `objective` | `str` | O que precisa ser calculado/decidido, em uma frase. |
| `inputs` | `list[str]` | O que a entrada contém, estruturado (não o texto cru da especificação). |
| `outputs` | `list[str]` | O que a saída precisa conter. |
| `constraints` | `list[str]` | Restrições numéricas (limites de N, tempo, memória) e não numéricas. |
| `examples_interpreted` | `list[str]` | Explicação, em texto, de *por que* cada exemplo dá a saída que dá — não só ecoar o par entrada/saída. |
| `hidden_requirements` | `list[str]` | Requisitos implícitos no enunciado, não ditos explicitamente (ex.: "a resposta cabe em 64 bits" quando o enunciado só dá os limites de N). |
| `special_cases` | `list[str]` | Casos especiais sugeridos pelo próprio enunciado (não confundir com corner cases algorítmicos, que são responsabilidade do Planejador). |
| `visual_elements` | `Optional[str]` | Descrição do conteúdo relevante de imagens anexadas. |
| `problem_type_hypotheses` | `list[str]` | Hipóteses preliminares sobre a família do problema (grafos, DP, geometria...) — hipóteses, não uma escolha; a escolha é do Planejador. |
| `ambiguities` | `list[str]` | Trechos do enunciado que admitem mais de uma interpretação razoável. |

Isso é uma versão mais rica do que já existe como `ProblemUnderstanding`
(`agents/plannig_agent/schemas.py`) — ver a comparação campo a campo
abaixo.

## Funcionamento

1. Ler o enunciado (e imagens, se houver) uma única vez.
2. Identificar, separadamente: o que é dado (entrada), o que é pedido
   (saída), e sob que restrições.
3. Para cada exemplo fornecido, explicar o raciocínio que leva da entrada
   à saída — isso frequentemente revela requisitos implícitos que o
   enunciado não deixou explícitos.
4. Levantar hipóteses sobre a família do problema **sem se comprometer**
   com nenhuma — isso é insumo para o Planejador, não uma decisão deste
   agente.
5. Marcar explicitamente qualquer trecho ambíguo, em vez de resolver a
   ambiguidade silenciosamente escolhendo uma interpretação.

## Critério de sucesso

> Se esta representação for entregue a outro agente (ou a outra pessoa),
> ele consegue entender exatamente o que precisa ser resolvido, sem
> consultar o enunciado original de novo?

Esse é o teste prático para saber se a formalização está completa.

## Métricas

Correspondem aos quatro critérios de avaliação da etapa "Compreender":

| Métrica | Definição | Como medir |
|---|---|---|
| Precisão na extração das restrições | Restrições extraídas que realmente existem no enunciado, sobre o total extraído. | Comparação contra gabarito humano (requer banco de problemas anotado, que não existe no repositório ainda). |
| Precisão na identificação de input/output | Idem, para `inputs`/`outputs`. | Idem. |
| Taxa de interpretação correta | Fração de problemas em que `objective` e `examples_interpreted` batem com a interpretação de referência. | Idem — ou, na ausência de gabarito, checando se a solução final gerada a partir dessa compreensão é aceita pelo Judge (proxy indireto). |
| Detecção de ambiguidades | Fração de ambiguidades reais do enunciado (conhecidas de antemão) que aparecem em `ambiguities`. | Requer um conjunto de problemas com ambiguidades conhecidas, curado manualmente. |

Nenhuma dessas métricas tem coleta automatizada hoje — depende de um
banco de problemas com gabarito, que está fora do escopo atual do
repositório.

## Mapeamento com o código atual

`PlaninngAgent._understand()` já implementa a maior parte desta
responsabilidade, produzindo `ProblemUnderstanding`:

| `ProblemSpecification` (este documento) | `ProblemUnderstanding` (código atual) | Coberto hoje? |
|---|---|---|
| `objective` | `restatement` | sim, embora menos estruturado (frase única vs. reformulação livre) |
| `inputs` | `inputs_description` | sim |
| `outputs` | `outputs_description` | sim |
| `constraints` | `constraints` | sim |
| `visual_elements` | `visual_elements` | sim |
| `ambiguities` | `ambiguities` | sim |
| `examples_interpreted` | — | não |
| `hidden_requirements` | — | não |
| `special_cases` | — | não (fica implícito em `constraints`/`ambiguities`) |
| `problem_type_hypotheses` | — | não (o Planejador já decide o padrão algorítmico diretamente na etapa 2, sem uma etapa intermediária de hipóteses) |

Ou seja: a maior parte do valor de um Agente de Compreensão já existe,
só que como uma etapa interna do Planejador em vez de um agente
independente. Antes de extrair isso para um `ComprehensionAgent`
standalone, vale considerar se o ganho (reuso da compreensão por múltiplos
agentes, auditoria isolada) compensa a chamada de LLM extra — hoje, manter
fundido evita uma chamada a mais por problema.

Se `ComprehensionAgent` for implementado, duas responsabilidades fazem
mais sentido para ele do que duplicar a compreensão semântica:

- **Pré-processamento de entrada bruta**: OCR/parsing dos PDFs dos
  cadernos da OBI, extração de imagens embutidas no enunciado,
  normalização de texto (encoding, remoção de cabeçalho/rodapé).
- **Enriquecimento do `PlannerInput`** a partir de metadados do banco de
  problemas (ex.: popular `time_limit_seconds`/`memory_limit_mb`, que hoje
  existem no schema mas nada os preenche automaticamente).

Nesse desenho, a saída do `ComprehensionAgent` continuaria sendo um
`PlannerInput` bem formado — não um `ProblemSpecification` à parte —, e
`PlaninngAgent._understand()` continuaria responsável pela formalização
semântica.
