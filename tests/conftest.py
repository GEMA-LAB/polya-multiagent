import json

from services.llm_service import LLMResponse, LLMUsage
from agents.plannig_agent import PlannerInput, TestCaseExample


class FakeLLM:
    """Stub LLM used to test PlaninngAgent without hitting a real API.

    Returns canned JSON responses in the order they were queued -- the
    Planning Agent makes exactly one call per Pólya stage, in order:
    understand, devise_plan, carry_out_plan, look_back.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def send_prompt_with_usage(self, prompt, system_prompt=None, response_format=None,
                                images=None, timeout=None):
        self.calls.append({"prompt": prompt, "images": images})
        content = self._responses.pop(0)
        return LLMResponse(
            content=content,
            usage=LLMUsage(model="fake-model", prompt_tokens=10, completion_tokens=20, total_tokens=30),
            elapsed_seconds=0.01,
        )


UNDERSTANDING_JSON = json.dumps({
    "restatement": "Encontrar o subvetor contiguo de soma maxima.",
    "inputs_description": "N inteiros.",
    "outputs_description": "A soma maxima.",
    "constraints": ["1 <= N <= 200000"],
    "visual_elements": None,
    "ambiguities": [],
})

PLAN_JSON = json.dumps({
    "algorithmic_pattern": "programacao dinamica (Kadane)",
    "candidate_strategies": ["forca bruta O(N^2)", "kadane O(N)"],
    "chosen_strategy": "kadane",
    "strategy_justification": (
        "kadane e O(N), o que atende ao limite de N <= 200000; a alternativa "
        "forca bruta seria O(N^2), inviavel para esse tamanho de entrada."
    ),
    "complexity": {
        "time_complexity": "O(N)",
        "space_complexity": "O(1)",
        "justification": "uma passada pelo vetor com N <= 200000, sem estruturas auxiliares",
    },
    "corner_cases": ["todos os elementos negativos", "N = 1"],
})

EXECUTION_JSON = json.dumps({
    "pseudocode": "best = arr[0]; cur = arr[0]\nfor x in arr[1:]:\n  cur = max(x, cur + x)\n  best = max(best, cur)",
    "data_structures": [],
    "key_steps": ["inicializar best e cur com arr[0]", "iterar e atualizar cur", "atualizar best"],
    "traced_outputs": ["4"],
})

REVIEW_JSON = json.dumps({
    "risks": ["overflow em linguagens com inteiro de tamanho fixo"],
    "verification_checklist": ["testar vetor com todos negativos", "testar N=1"],
    "confidence": "high",
})


def canned_stage_responses() -> list[str]:
    return [UNDERSTANDING_JSON, PLAN_JSON, EXECUTION_JSON, REVIEW_JSON]


def make_planner_input(**overrides) -> PlannerInput:
    base = dict(
        problem_id="p1",
        statement="Encontre o subvetor de soma maxima em um vetor de N inteiros.",
        input_spec="N <= 200000",
        output_spec="a soma maxima",
        examples=[TestCaseExample(input="4\n-2 1 -3 4", output="4")],
        difficulty="medio",
    )
    base.update(overrides)
    return PlannerInput(**base)
