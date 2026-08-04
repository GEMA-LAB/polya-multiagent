"""Prompt templates for the four Pólya stages.

Each stage prompt asks for a single JSON object whose keys line up exactly
with the corresponding dataclass in schemas.py, so parsing in main.py is a
plain `json.loads` + key lookup. Written in Portuguese because OBI problem
statements are in Portuguese and that is the language the model should
reason and answer in.
"""

from .schemas import PlannerInput, PlanningDepth, ProblemUnderstanding, SolutionPlan, ExecutionSketch

SYSTEM_PROMPT = (
    "Você é o Agente Planejador de um pipeline para resolver problemas de "
    "programação competitiva da Olimpíada Brasileira de Informática (OBI). "
    "Você aplica explicitamente o método de Pólya (compreender, planejar, "
    "executar, revisar) e NUNCA escreve o código-fonte final -- essa é "
    "responsabilidade de um Agente Codificador separado, mais adiante no "
    "pipeline. Responda sempre com um único objeto JSON válido, sem texto "
    "fora do JSON, sem markdown/backticks."
)


def _examples_block(planner_input: PlannerInput) -> str:
    if not planner_input.examples:
        return "(nenhum exemplo fornecido)"
    parts = []
    for i, ex in enumerate(planner_input.examples, start=1):
        block = f"Exemplo {i}:\nEntrada:\n{ex.input}\nSaída:\n{ex.output}"
        if ex.explanation:
            block += f"\nExplicação: {ex.explanation}"
        parts.append(block)
    return "\n\n".join(parts)


def _feedback_block(planner_input: PlannerInput) -> str:
    if not planner_input.previous_attempts:
        return ""
    lines = ["", "## Tentativas anteriores (feedback do Judge)", ""]
    for attempt in planner_input.previous_attempts:
        line = f"- Tentativa {attempt.attempt_number}: veredito {attempt.verdict}"
        if attempt.details:
            line += f" -- {attempt.details}"
        if attempt.failing_test_case:
            line += f" (caso de teste que falhou: {attempt.failing_test_case})"
        lines.append(line)
    lines.append(
        "Leve esse histórico em conta: se houve TLE, priorize uma estratégia "
        "com complexidade menor; se houve WA, reveja corner cases e a "
        "interpretação do enunciado; se houve CE/RE, reveja suposições sobre "
        "tipos e limites."
    )
    return "\n".join(lines)


def _depth_instruction(depth: PlanningDepth) -> str:
    if depth is PlanningDepth.DETAILED:
        return (
            "Este problema foi classificado como de alta complexidade "
            "(grafos, programação dinâmica, múltiplas imagens/casos, ou "
            "difícil). Seja detalhado e explícito em cada campo."
        )
    return (
        "Este problema foi classificado como simples. Seja direto e conciso "
        "em cada campo, sem perder informação essencial."
    )


def build_understanding_prompt(planner_input: PlannerInput, depth: PlanningDepth) -> str:
    images_note = (
        "O enunciado inclui imagem(ns) anexada(s) nesta mensagem "
        "(ex.: figura de grafo, geometria, diagrama). Descreva no campo "
        "'visual_elements' o que é relevante para modelar o problema."
        if planner_input.images_base64 else
        "Não há imagens associadas a este problema; deixe 'visual_elements' como null."
    )

    return (
        f"{_depth_instruction(depth)}\n\n"
        "## Etapa 1 de Pólya: Compreender o problema\n\n"
        f"### Enunciado\n{planner_input.statement}\n\n"
        f"### Especificação de entrada\n{planner_input.input_spec or '(não informado)'}\n\n"
        f"### Especificação de saída\n{planner_input.output_spec or '(não informado)'}\n\n"
        f"### Exemplos\n{_examples_block(planner_input)}\n\n"
        f"{images_note}\n"
        f"{_feedback_block(planner_input)}\n\n"
        "Responda em JSON com exatamente estas chaves:\n"
        "{\n"
        '  "restatement": "reformulação do problema com suas próprias palavras",\n'
        '  "inputs_description": "descrição dos dados de entrada",\n'
        '  "outputs_description": "descrição da saída esperada",\n'
        '  "constraints": ["lista de restrições, ex: limites de N, tempo, memória"],\n'
        '  "visual_elements": "descrição do conteúdo visual relevante, ou null",\n'
        '  "ambiguities": ["lista de ambiguidades detectadas no enunciado, pode ser vazia"]\n'
        "}"
    )


def build_planning_prompt(planner_input: PlannerInput, understanding: ProblemUnderstanding, depth: PlanningDepth) -> str:
    return (
        f"{_depth_instruction(depth)}\n\n"
        "## Etapa 2 de Pólya: Elaborar um plano\n\n"
        f"### Compreensão já estabelecida\n"
        f"Reformulação: {understanding.restatement}\n"
        f"Restrições: {understanding.constraints}\n"
        f"Elementos visuais: {understanding.visual_elements or '(nenhum)'}\n\n"
        f"{_feedback_block(planner_input)}\n\n"
        "Identifique o padrão algorítmico (força bruta, busca, grafos, "
        "programação dinâmica, guloso, matemática, geometria, etc.), proponha "
        "estratégias candidatas, estime complexidade de tempo/espaço frente "
        "aos limites do problema, escolha a estratégia mais adequada com "
        "justificativa, e liste corner cases esperados (entradas vazias, "
        "valores extremos, ciclos, empates, overflow etc.) -- essa é a causa "
        "mais comum de falha de modelos em programação competitiva.\n\n"
        "Responda em JSON com exatamente estas chaves:\n"
        "{\n"
        '  "algorithmic_pattern": "nome do padrão algorítmico principal",\n'
        '  "candidate_strategies": ["lista de estratégias candidatas consideradas"],\n'
        '  "chosen_strategy": "estratégia escolhida",\n'
        '  "strategy_justification": "por que essa estratégia foi escolhida em vez das outras",\n'
        '  "complexity": {\n'
        '    "time_complexity": "ex: O(N log N)",\n'
        '    "space_complexity": "ex: O(N)",\n'
        '    "justification": "por que essa complexidade atende aos limites do problema"\n'
        "  },\n"
        '  "corner_cases": ["lista de corner cases que a solução precisa tratar"]\n'
        "}"
    )


def build_execution_prompt(planner_input: PlannerInput, understanding: ProblemUnderstanding,
                            plan: SolutionPlan, depth: PlanningDepth) -> str:
    return (
        f"{_depth_instruction(depth)}\n\n"
        "## Etapa 3 de Pólya: Executar o plano\n\n"
        f"Estratégia escolhida: {plan.chosen_strategy} ({plan.algorithmic_pattern})\n"
        f"Complexidade alvo: {plan.complexity.time_complexity}\n"
        f"Corner cases: {plan.corner_cases}\n\n"
        "Traduza o plano em um pseudocódigo estruturado, claro o suficiente "
        "para orientar a geração do código final -- mas NÃO escreva código "
        "Python/C++ completo, apenas pseudocódigo/esqueleto de alto nível. "
        "Isso será usado como contexto adicional para o Agente Codificador.\n\n"
        "Responda em JSON com exatamente estas chaves:\n"
        "{\n"
        '  "pseudocode": "pseudocódigo estruturado em texto (pode usar \\n)",\n'
        '  "data_structures": ["estruturas de dados usadas"],\n'
        '  "key_steps": ["passos-chave do algoritmo em ordem"]\n'
        "}"
    )


def build_review_prompt(planner_input: PlannerInput, understanding: ProblemUnderstanding,
                         plan: SolutionPlan, execution: ExecutionSketch, depth: PlanningDepth) -> str:
    return (
        f"{_depth_instruction(depth)}\n\n"
        "## Etapa 4 de Pólya: Revisar / Refletir (Look back)\n\n"
        f"Plano: {plan.chosen_strategy}, complexidade {plan.complexity.time_complexity}\n"
        f"Pseudocódigo:\n{execution.pseudocode}\n\n"
        f"{_feedback_block(planner_input)}\n\n"
        "Aponte riscos do plano (complexidade no limite, casos não cobertos, "
        "armadilhas do enunciado) e defina critérios de verificação que o "
        "próprio agente ou o Judge deveriam validar depois da geração do "
        "código. Dê também um nível de confiança geral no plano.\n\n"
        "Responda em JSON com exatamente estas chaves:\n"
        "{\n"
        '  "risks": ["lista de riscos identificados"],\n'
        '  "verification_checklist": ["lista de itens a verificar após gerar o código"],\n'
        '  "confidence": "low | medium | high"\n'
        "}"
    )
