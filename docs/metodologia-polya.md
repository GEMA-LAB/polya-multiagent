# A metodologia de Pólya

Este documento explica o método de resolução de problemas de George
Pólya em si — independente de como ele é implementado neste repositório.
Para ver como cada etapa vira um agente concreto, com contrato de entrada
e saída, veja [`docs/agentes/`](agentes/); para o agente que já implementa
o método, veja [`docs/agente-planejador/`](agente-planejador/).

## Origem

O método vem do livro *How to Solve It* (1945), do matemático húngaro
George Pólya. O livro nasceu da experiência de Pólya ensinando matemática
e observando que alunos capazes travavam não por falta de conhecimento
técnico, mas por falta de um processo para atacar um problema que nunca
tinham visto antes. Em vez de ensinar mais teoremas, Pólya propôs ensinar
um **processo** — replicável em qualquer problema, não só em matemática.

O método organiza a resolução de problemas em quatro etapas. A ideia
central não é que elas sejam um checklist burocrático, mas que cada etapa
tenha perguntas específicas que ajudam a destravar quem está preso.

## As quatro etapas

### 1. Compreender o problema

Antes de qualquer tentativa de solução, é preciso conseguir enunciar o
problema com precisão. Pólya observa que é comum alguém tentar resolver um
problema que não entendeu direito — e travar sem saber se o problema é
difícil ou se a dificuldade é só não ter entendido o que está sendo
pedido.

Perguntas-guia desta etapa:

- Qual é a incógnita? Quais são os dados? Qual é a condição?
- É possível satisfazer a condição? A condição é suficiente para
  determinar a incógnita? Ou é insuficiente? Ou redundante? Ou
  contraditória?
- Desenhe uma figura. Introduza uma notação adequada.
- Separe as diferentes partes da condição. Você consegue escrevê-las?

### 2. Elaborar um plano

Um plano é a ideia de **como** conectar os dados à incógnita — antes de
executar qualquer coisa. Pólya insiste que raramente essa ideia surge do
nada: ela normalmente vem de reconhecer que o problema (ou parte dele) é
parecido com algo já resolvido antes.

Perguntas-guia desta etapa:

- Você já viu isso antes? Ou já viu o mesmo problema formulado de forma
  ligeiramente diferente?
- Você conhece um problema relacionado? Conhece algum teorema que possa
  ser útil?
- Olhe para a incógnita e tente pensar em um problema familiar que tenha
  a mesma incógnita, ou uma parecida.
- Aqui está um problema relacionado ao seu, e já resolvido antes — você
  consegue usá-lo? Consegue usar o resultado dele? Consegue usar o
  método dele?
- Você consegue reformular o problema? Consegue reformulá-lo de um jeito
  ainda diferente?
- Se não consegue resolver o problema proposto, tente primeiro resolver
  algum problema relacionado. Consegue imaginar um problema relacionado
  mais acessível? Um problema mais geral? Um problema mais específico?
  Um problema análogo?
- Consegue resolver uma parte do problema? Mantenha só uma parte da
  condição, descarte o resto — até onde a incógnita fica determinada, e
  como ela pode variar?
- Você usou todos os dados? Usou toda a condição? Levou em conta todas as
  noções essenciais envolvidas no problema?

Dessas perguntas nasce um conjunto de **heurísticas** — estratégias
gerais para gerar um plano quando nenhuma ideia óbvia aparece:

| Heurística | Ideia |
|---|---|
| Analogia | Resolver um problema parecido, mais simples, e adaptar o raciocínio. |
| Trabalhar de trás para frente | Partir da incógnita/objetivo e perguntar o que precisaria ser verdade um passo antes, repetindo até chegar aos dados. |
| Especialização | Testar um caso particular simples do problema geral (ex.: N pequeno) para enxergar um padrão. |
| Generalização | Resolver uma versão mais geral do problema, às vezes mais fácil de enxergar do que o caso específico. |
| Decompor e recombinar | Quebrar o problema em subproblemas menores, resolver cada um, e recombinar as soluções. |
| Problema auxiliar | Inventar um problema intermediário mais fácil, cuja solução ajuda a resolver o original. |
| Variação do problema | Mudar os dados ou a incógnita, mantendo a estrutura, para aproximar o problema de algo já conhecido. |

### 3. Executar o plano

Executar é mais fácil do que planejar, mas Pólya alerta que não é
automático: um plano pode parecer certo em linhas gerais e ainda assim
esconder um passo errado. Por isso, cada passo da execução precisa ser
verificado individualmente, não só o resultado final.

Perguntas-guia desta etapa:

- Ao executar seu plano de solução, verifique cada passo.
- Você consegue ver claramente que o passo está correto? Consegue provar
  que está correto?

### 4. Revisar (*olhar para trás*)

Esta é a etapa mais frequentemente pulada — e a que Pólya considera mais
valiosa para quem quer melhorar como resolve problemas, não só resolver o
problema em questão. Revisar não é conferir se a resposta "parece certa";
é examinar ativamente o raciocínio em busca de erros, e extrair da solução
algo reaproveitável para o futuro.

Perguntas-guia desta etapa:

- Você consegue conferir o resultado? Consegue conferir o argumento?
- Consegue chegar ao resultado por um caminho diferente? Consegue
  enxergá-lo de forma direta, sem repetir toda a derivação?
- Consegue usar o resultado, ou o método, para algum outro problema?

## O método não é uma linha reta

Um ponto central do livro, fácil de perder ao resumir as quatro etapas
como uma lista numerada: raramente se passa pelas quatro etapas uma única
vez, em ordem. É comum, ao executar o plano, perceber que ele não
funciona e voltar para "elaborar um plano" — ou, ao tentar planejar,
perceber que o problema não foi bem compreendido e voltar para a etapa 1.
O processo é cíclico, guiado pelo que cada etapa revela sobre as
anteriores, não uma esteira de produção.

## Por que isso importa para além da sala de aula

O valor do método de Pólya não está em nenhuma das quatro etapas
isoladamente — qualquer pessoa já "entende o problema" e "tenta algo" de
forma intuitiva. O valor está em tornar **explícito** um processo que
normalmente fica implícito, o que traz duas vantagens práticas:

- Cada etapa pode ser **auditada** separadamente: dá para saber se um
  erro veio de má compreensão do problema, de uma estratégia errada, de
  um erro de execução, ou de falta de revisão — em vez de só saber que "a
  resposta final está errada".
- Cada etapa pode receber **atenção proporcional à dificuldade real** do
  problema: um problema simples pode passar rápido pelas quatro etapas; um
  problema difícil de programação competitiva, por exemplo, costuma
  exigir bem mais tempo em "elaborar um plano" (qual algoritmo? qual
  complexidade?) do que em "executar" (escrever o código já é o passo
  fácil, uma vez que o plano está certo).

É exatamente essa auditabilidade — poder isolar em qual etapa o raciocínio
falhou — que motiva usar as quatro etapas como quatro componentes
separados em vez de um único prompt monolítico pedindo "resolva isso".
Como esse mapeamento é feito neste repositório, etapa a etapa, está em
[`docs/agentes/visao-geral.md`](agentes/visao-geral.md).

## Referência

Pólya, G. (1945). *How to Solve It: A New Aspect of Mathematical Method*.
Princeton University Press.
