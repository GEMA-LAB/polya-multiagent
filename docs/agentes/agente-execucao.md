# Agente Executor (Agente Codificador)

> **Status**: não implementado (stub `ExecutationAgent` em
> `agents/executation_agent/`, só com `print()` no `__init__`).

## Papel

Corresponde à etapa 3 de Pólya — *carry out the plan* — mas produzindo
**código-fonte final, compilável e testável**, não o pseudocódigo que o
Agente Planejador já produz (ver
[`visao-geral.md`](visao-geral.md#os-quatro-agentes-e-o-orquestrador) para
a distinção entre os dois). É o agente descrito no artigo original como
"Service do LLM (Agente Codificador)" — a diferença é que agora ele
recebe um prompt já enriquecido com o plano de Pólya, em vez do enunciado
cru.

Diferente dos outros três agentes, este deveria funcionar como um agente
de **engenharia de software**, não só de raciocínio: gera código, mas
também compila, roda contra os exemplos e corrige, dentro de um número
limitado de iterações — em vez de devolver a primeira coisa que o LLM
escreveu.

## Entrada

| Campo | Tipo | Descrição |
|---|---|---|
| `problem` | `PlannerInput` | O problema original — usado para o enunciado e os exemplos (para teste local). |
| `plan` | `PlannerOutput` | Saída do Agente Planejador — estratégia, pseudocódigo, corner cases, riscos. |

Na prática, a montagem do prompt já está pronta:
`prompt_templates.build_coder_prompt(problem.statement, plan)` (ver
[`docs/agente-planejador/integracao.md`](../agente-planejador/integracao.md#como-o-plano-é-injetado-no-prompt-do-agente-codificador))
gera o texto completo — enunciado + plano de resolução + instrução final
— que o Agente Executor deveria passar para `LLM.send_prompt_with_usage()`.

## Saída: `CandidateSolution`

| Campo | Tipo | Descrição |
|---|---|---|
| `source_code` | `str` | Código-fonte extraído da resposta do LLM (sem texto ao redor). |
| `language` | `str` | Linguagem do código gerado (ex.: `"python3"`). |
| `compiled` | `bool` | Se o código compilou/passou no parse de sintaxe. |
| `compile_errors` | `Optional[str]` | Mensagem de erro de compilação, se houver. |
| `local_test_results` | `list[LocalTestResult]` | Resultado de rodar o código contra `PlannerInput.examples` (não os testes ocultos do Judge). |
| `iterations_used` | `int` | Quantas rodadas de gerar→compilar→testar→corrigir foram necessárias. |
| `metadata` | `TokenUsage` | Custo/tokens/tempo agregado de todas as chamadas de LLM desta etapa. |

`LocalTestResult`: `example_index: int`, `expected_output: str`,
`actual_output: str`, `passed: bool`, `stderr: Optional[str]`.

## Funcionamento

```
plano (PlannerOutput)
  │
  ▼
gerar código a partir de build_coder_prompt()
  │
  ▼
extrair bloco de código da resposta
  │              (texto ao redor do código, mesmo com instrução contra isso,
  │               deve ser tratado como resposta malformada e reextraído/retentado)
  ▼
compilar / checar sintaxe
  │
  ├── falhou ──► realimentar erro de compilação no LLM, gerar de novo
  │
  ▼
rodar contra PlannerInput.examples (teste local, antes do Judge)
  │
  ├── algum exemplo falhou ──► realimentar (esperado vs. obtido) no LLM, corrigir
  │
  ▼
até N iterações (limite duro, ex.: 3) ou todos os exemplos passarem
  │
  ▼
CandidateSolution
```

O ponto central: **testar contra os exemplos localmente antes de gastar
uma submissão no Judge**. Isso é a mesma lógica que
`PlaninngAgent._verify_trace_against_examples()` já aplica no nível do
pseudocódigo (comparando a simulação manual do modelo com a saída real) —
aqui a verificação é mais forte, porque o código de fato roda.

## Ferramentas necessárias

Diferente dos outros três agentes (que hoje só fazem chamadas de LLM),
este precisa de acesso real a:

- Um interpretador/compilador para a linguagem-alvo (ex.: `python3 -I` em
  subprocesso, ou um compilador C++).
- Um executor com **sandboxing**: sem acesso à rede, com limite de tempo
  e memória por execução, rodando em um processo isolado — o código vem
  de um LLM, não é confiável por padrão.
- Comparação de saída com tolerância configurável (espaços/quebras de
  linha no fim, mas não diferença numérica — a menos que o problema seja
  de saída com erro de ponto flutuante tolerado, o que deveria vir de
  `PlannerInput`/`ProblemUnderstanding`).

## Segurança

Este é o primeiro agente do pipeline que **executa** algo, não só
raciocina — o critério 8 (segurança) de
[`visao-geral.md`](visao-geral.md#dez-critérios-de-engenharia) se torna
central aqui. Nível de permissão sugerido: execução do código gerado é
uma ação de risco médio (não crítico, mas precisa de isolamento) —
timeout curto, sem rede, sem acesso a arquivos fora de um diretório
temporário descartável, executada como um usuário sem privilégios.

## Métricas

Correspondem aos quatro critérios de avaliação da etapa "Executar":

| Métrica | Definição | Onde medir |
|---|---|---|
| Compilação | Fração de gerações que compilam sem erro (eventualmente, dentro do limite de iterações). | `CandidateSolution.compiled`. |
| Correctness | Fração de exemplos locais que passam; depois, fração de casos ocultos do Judge que passam (veredito final). | `local_test_results` localmente; veredito do Judge (não implementado) para a medida real. |
| Tempo de execução | Tempo de execução do código gerado contra os exemplos/casos do Judge. | Medido pelo sandbox de execução; não é o mesmo que `TokenUsage.elapsed_seconds` (que mede tempo de chamada ao LLM, não de execução do código). |
| Memória | Pico de memória do código gerado durante a execução. | Medido pelo sandbox de execução (ex.: `resource.getrusage` em Python, ou limite de cgroup). |
| Número de iterações necessárias | Quantas rodadas de gerar→testar→corrigir até passar nos exemplos locais (ou até estourar o limite). | `CandidateSolution.iterations_used`. |

## Erros esperados

Seguindo o mesmo padrão do Agente Planejador
(`agents/plannig_agent/errors.py`): um módulo `errors.py` próprio, com uma
exceção base e subtipos para as falhas específicas deste agente — em
particular, uma equivalente a `PlannerMalformedResponseError` para quando
o LLM devolve texto que não é só código, mesmo com instrução para isso
(não reaproveitar a exceção do Planejador; são falhas de etapas
diferentes, com estados distintos anexados).
