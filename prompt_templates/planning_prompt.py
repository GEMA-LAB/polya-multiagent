PLANNING_PROMPT_TEMPLATE = (
    "Você deve elaborar um plano de resolução para o problema de programação "
    "competitiva abaixo, aplicando a etapa \"elaborar um plano\" do método de "
    "Pólya: identifique o padrão algorítmico, proponha uma estratégia "
    "adequada aos limites do problema, estime a complexidade de tempo/espaço, "
    "e liste os principais corner cases a tratar. Não escreva código.\n\n"
    "## Problema\n{input_text}\n\n"
    "## Plano de resolução"
)
