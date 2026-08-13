# Escopo previsto dos demais agentes

O repositório já reserva um diretório em `agents/` para cada um dos quatro
agentes do pipeline — um deles, `PlaninngAgent` (Agente Planejador), está
totalmente implementado e documentado em
[`docs/agente-planejador/`](agente-planejador/). Os outros três continuam
como estavam (classes vazias, só com `print()` no `__init__`), fora do
escopo deste trabalho. Este documento é um guia curto do que cada um
deveria fazer, para quem for implementá-los, mantendo consistência com o
padrão estabelecido pelo Agente Planejador.

## Convenções a seguir (estabelecidas pelo Agente Planejador)

- **Contrato tipado**: uma `dataclass` de entrada e uma de saída por
  agente, em `schemas.py`, dentro do próprio pacote do agente (ex.:
  `agents/<nome>_agent/schemas.py`). Não há `pydantic` no projeto; não
  introduza a dependência sem necessidade real de validação/serialização
  que `dataclasses` não resolvam.
- **Erros explícitos**: um módulo `errors.py` com uma exceção base
  específica do agente e subtipos para timeout, resposta malformada e
  campo obrigatório ausente — não deixe erros de parsing ou de API
  vazarem como `Exception` genérica.
- **Injeção do cliente LLM**: o construtor deve aceitar um `LLM` (ou
  compatível por duck typing) via parâmetro opcional, com fallback para
  construir um a partir de variáveis de ambiente. Isso é o que torna o
  agente testável sem chamadas de rede reais (ver `tests/conftest.py` e
  o `FakeLLM`/`ScriptedLLM` usados lá).
- **Variáveis de ambiente com prefixo**: siga o padrão
  `<AGENTE>__API_KEY`, `<AGENTE>__BASE_URL`, `<AGENTE>__MODEL_NAME`,
  `<AGENTE>__INPUT_PRICE`, `<AGENTE>__OUTPUT_PRICE`, com fallback para as
  variáveis sem prefixo (`API_KEY`, `BASE_URL`, `MODEL`). Veja o exemplo
  em `PLANNER__*` (`docs/agente-planejador/integracao.md`).
- **Metadados de custo**: se o agente chama um LLM, ele deve devolver
  tokens/custo/tempo (reaproveite `services.llm_service.LLM
  .send_prompt_with_usage()`, que já devolve `LLMUsage` + tempo decorrido).
- **Testes com stub de LLM**: nada de teste que dependa de rede/chave de
  API real. Injete um stub que devolve JSON fixo, como já é feito para o
  Agente Planejador.

## `ComprehensionAgent` (`agents/comprehension_agent/`)

No desenho atual, a compreensão profunda do problema já acontece *dentro*
do Agente Planejador (etapa 1 de Pólya, `PlaninngAgent._understand()`).
Um `ComprehensionAgent` separado só se justifica se ele assumir uma
responsabilidade que hoje está fora do Agente Planejador, por exemplo:

- Pré-processamento de entrada bruta antes do planejamento: OCR/parsing de
  PDFs dos cadernos da OBI, extração de imagens embutidas no enunciado,
  normalização de texto (encoding, remoção de cabeçalho/rodapé do PDF).
- Enriquecimento do `PlannerInput` a partir do banco de problemas (ex.:
  popular `time_limit_seconds`/`memory_limit_mb` a partir de metadados do
  caderno, já que hoje esses campos existem no schema mas nada os
  preenche automaticamente).

Se implementado dessa forma, sua saída natural é justamente um
`PlannerInput` já populado, que alimenta `PlaninngAgent.plan()`.

## `ExecutationAgent` (`agents/executation_agent/`) — futuro Agente Codificador

Este é o agente descrito no artigo original como "Service do LLM (Agente
Codificador)": recebe o enunciado e devolve uma solução em código. A
diferença em relação ao pipeline original é que agora ele deve consumir o
prompt já enriquecido com o plano de Pólya
(`prompt_templates.build_coder_prompt()`), não mais o enunciado cru.

Responsabilidades sugeridas:

- `generate(problem: PlannerInput, plan: PlannerOutput) -> str`: monta o
  prompt via `build_coder_prompt()`, chama o LLM e devolve o código-fonte.
- Extrair apenas o bloco de código da resposta do modelo (o modelo pode
  devolver texto ao redor, mesmo com instrução para não fazê-lo) —
  tratar isso como um caso de `PlannerMalformedResponseError`-equivalente
  próprio deste agente, não reaproveitar a exceção do Planejador.
- Igual ao Agente Planejador, aceitar um `LLM` por injeção de dependência
  e reportar `TokenUsage` da geração de código.

## `ReviewAgent` (`agents/review_agent/`)

Importante não confundir com a etapa 4 de Pólya (*look back*) que já
existe **dentro** do Agente Planejador (`PlaninngAgent._look_back()`) —
essa etapa revisa o **plano antes de qualquer código ser escrito**. Um
`ReviewAgent` separado faz sentido como uma etapa **pós-execução**, depois
que o Judge já rodou:

- Receber o veredito do Judge + o código gerado + o `PlannerOutput`
  original e produzir um diagnóstico legível (ex.: "o WA no caso 3 é
  consistente com a ambiguidade sobre grafo direcionado/não-direcionado
  que o Agente Planejador já havia sinalizado em `review.risks`").
- Decidir, de forma mais informada que um `replan()` cego, se vale a pena
  chamar `PlaninngAgent.replan()` de novo ou se o problema é só um bug de
  implementação do Agente Codificador (nesse caso, reenviar para o
  Agente Codificador com o mesmo plano, sem replanejar do zero).
- Esse agente é o lugar natural para acumular estatísticas por execução em
  lote (taxa de AC por dificuldade, por padrão algorítmico, etc.) — hoje
  inexistentes no repositório.
