# polya-multiagent
Estudos sobre metodologia de polya com cada ciclo sendo agentes inteligentes com motores de busca usando LLMs

## Agente Planejador

Entre a seleção do problema e a geração de código, o **Agente Planejador**
(`agents/plannig_agent/`, classe `PlaninngAgent`) aplica explicitamente as
quatro etapas do método de Pólya — compreender, planejar, executar (em
pseudocódigo) e revisar — antes de qualquer código ser escrito, produzindo
um plano estruturado (estratégia algorítmica, complexidade estimada,
corner cases, riscos) que é injetado no prompt do Agente Codificador. Isso
ataca diretamente a limitação observada em prompting zero-shot puro para
problemas difíceis de programação competitiva (grafos, programação
dinâmica), que tende a pular a modelagem do problema.

Documentação completa em [`docs/agente-planejador/`](docs/agente-planejador/)
(visão geral, interface de entrada/saída, exemplos ponta a ponta e
integração com o Orquestrador/Judge) e uma nota sobre o escopo previsto
dos demais agentes em [`docs/outros-agentes.md`](docs/outros-agentes.md).
