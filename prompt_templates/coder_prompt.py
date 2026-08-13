"""Prompt template for the (not yet implemented) Coding Agent.

Builds the final prompt for the LLM that writes source code. The Planning
Agent's structured output is rendered by PlannerOutput.to_prompt_section()
and interpolated here as a "## Plano de Resolução" section placed right
before the final instruction, so the coder receives Pólya's plan as extra
context instead of just the raw problem statement -- this is exactly what
the original zero-shot pipeline lacked.
"""

from agents.plannig_agent import PlannerOutput

CODER_INSTRUCTIONS = (
    "Você é um agente de programação competitiva. Escreva a solução final em "
    "Python 3, pronta para submissão, lendo da entrada padrão e escrevendo na "
    "saída padrão. Siga o plano de resolução acima, incluindo o tratamento "
    "dos corner cases listados. Responda apenas com o código, sem explicações "
    "adicionais."
)


def build_coder_prompt(statement: str, plan: PlannerOutput) -> str:
    return (
        f"## Enunciado\n{statement}\n\n"
        f"{plan.to_prompt_section()}\n\n"
        f"## Instrução final\n{CODER_INSTRUCTIONS}"
    )
