"""Planning Agent (Agente Planejador).

Sits between the Orchestrator and the Coding Agent and applies George
Pólya's four problem-solving steps -- understand, devise a plan, carry out
the plan, look back -- as four distinct, auditable stages, each backed by
its own LLM call and its own typed output (see schemas.py). This is the
component that fills the gap identified in the original zero-shot study:
a single "just solve it" prompt skips modeling and corner-case analysis,
which is where competitive-programming solutions usually fail.

How the intelligent-agent characteristics from
https://smythos.com/developers/agent-development/intelligent-agent-characteristics/
map onto this class:

- Autonomia / orientação a objetivos: plan() recebe um problema e produz,
  sozinho, um plano completo em 4 etapas, sem intervenção humana, guiado
  pelo objetivo de maximizar a chance de o código gerado a partir do plano
  passar em todos os testes (AC).
- Reatividade: _infer_depth() reage ao conteúdo real do problema (imagens,
  dificuldade, número de exemplos, palavras-chave de grafo/DP no
  enunciado) e ajusta a profundidade do plano.
- Comportamento proativo: _detect_scale_hints() e _cross_check_complexity()
  antecipam problemas de desempenho (limites que sugerem N grande vs.
  complexidade escolhida) antes que apareçam como TLE no Judge, e ficam no
  campo `review.risks` mesmo que o modelo não os tenha citado.
- Aprendizado/adaptação: replan() implementa o ciclo de feedback -- um
  veredito do Judge (JudgeAttemptFeedback) é anexado ao histórico do
  problema e uma nova rodada de planejamento é executada com esse
  contexto. V1 sempre replaneja o ciclo inteiro; é o ponto de extensão
  para uma política mais fina (ex.: TLE -> só replanejar complexidade).
- Comunicação/sociabilidade: a entrada (PlannerInput) e a saída
  (PlannerOutput) são contratos tipados e serializáveis; PlannerOutput
  .to_prompt_section() gera diretamente o bloco Markdown consumido pelo
  prompt do Agente Codificador (prompt_templates/coder_prompt.py), sem
  reprocessamento manual.
"""

import json
import os
import re
from typing import Optional

from dotenv import load_dotenv
from openai import APIError, APITimeoutError

from services import LLM
from services.llm_service import LLMUsage
from .errors import PlannerMalformedResponseError, PlannerTimeoutError, PlannerError
from .prompts import (
    SYSTEM_PROMPT,
    build_understanding_prompt,
    build_planning_prompt,
    build_execution_prompt,
    build_review_prompt,
)
from .schemas import (
    ComplexityEstimate,
    ExecutionSketch,
    JudgeAttemptFeedback,
    PlanReview,
    PlannerInput,
    PlannerOutput,
    PlanningDepth,
    ProblemUnderstanding,
    SolutionPlan,
    TokenUsage,
)

_HARD_KEYWORDS = (
    "grafo", "graph", "árvore", "arvore", "tree", "dp", "programação dinâmica",
    "programacao dinamica", "dynamic programming", "menor caminho", "shortest path",
    "componente conexa", "union-find", "dsu", "topologic",
)
_HARD_DIFFICULTIES = {"hard", "dificil", "difícil", "avancado", "avançado", "ouro", "gold"}

_SCALE_PATTERN = re.compile(r"(?:(\d+(?:[.,]\d+)?)\s*[x*]?\s*)?10\s*\^\s*(\d+)|(\d{4,})")
_RISKY_COMPLEXITY_PATTERNS = ("n^2", "n²", "n^3", "n³", "2^n", "n!")


def _require_keys(data: dict, keys: tuple, stage: str, raw: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise PlannerMalformedResponseError(
            stage=stage,
            raw_response=raw,
            cause=KeyError(f"campos ausentes: {missing}"),
        )


def _dedup(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class PlaninngAgent:
    def __init__(self,
                 llm: Optional[LLM] = None,
                 *,
                 timeout: float = 60.0,
                 input_price: Optional[float] = None,
                 output_price: Optional[float] = None):
        load_dotenv()

        if llm is None:
            llm = LLM(
                api_key=os.getenv("PLANNER__API_KEY") or os.getenv("API_KEY"),
                base_url=os.getenv("PLANNER__BASE_URL") or os.getenv("BASE_URL"),
                model=os.getenv("PLANNER__MODEL_NAME") or os.getenv("MODEL"),
            )

        self.__llm = llm
        self.__timeout = timeout
        self.__input_price = (
            input_price if input_price is not None
            else float(os.getenv("PLANNER__INPUT_PRICE", "0") or 0)
        )
        self.__output_price = (
            output_price if output_price is not None
            else float(os.getenv("PLANNER__OUTPUT_PRICE", "0") or 0)
        )

        print("Init Planning")

    # -- public API ---------------------------------------------------

    def plan(self, planner_input: PlannerInput) -> PlannerOutput:
        """Runs the full Pólya cycle and returns a structured plan."""
        planner_input.validate()
        depth = self._infer_depth(planner_input)

        understanding, u1, t1 = self._understand(planner_input, depth)
        solution_plan, u2, t2 = self._devise_plan(planner_input, understanding, depth)
        execution, u3, t3 = self._carry_out_plan(planner_input, understanding, solution_plan, depth)
        review, u4, t4 = self._look_back(planner_input, understanding, solution_plan, execution, depth)

        scale_hints = self._detect_scale_hints(planner_input)
        review.risks = _dedup(review.risks + self._cross_check_complexity(solution_plan, scale_hints))

        metadata = self._aggregate_usage([u1, u2, u3, u4], t1 + t2 + t3 + t4)

        return PlannerOutput(
            problem_id=planner_input.problem_id,
            understanding=understanding,
            plan=solution_plan,
            execution_sketch=execution,
            review=review,
            metadata=metadata,
            iteration=len(planner_input.previous_attempts) + 1,
        )

    def replan(self, planner_input: PlannerInput, feedback: JudgeAttemptFeedback) -> PlannerOutput:
        """Feedback-loop entry point: appends the Judge's verdict to the
        problem's history and re-runs the Pólya cycle so every stage can
        react to it via `_feedback_block()` in prompts.py."""
        planner_input.previous_attempts.append(feedback)
        return self.plan(planner_input)

    # -- Pólya stages ---------------------------------------------------

    def _understand(self, planner_input: PlannerInput, depth: PlanningDepth):
        prompt = build_understanding_prompt(planner_input, depth)
        data, usage, elapsed = self._call_llm_json(
            stage="understand",
            prompt=prompt,
            images=planner_input.images_base64 or None,
        )
        _require_keys(
            data,
            ("restatement", "inputs_description", "outputs_description", "constraints"),
            "understand",
            json.dumps(data),
        )
        understanding = ProblemUnderstanding(
            restatement=data["restatement"],
            inputs_description=data["inputs_description"],
            outputs_description=data["outputs_description"],
            constraints=list(data.get("constraints", [])),
            visual_elements=data.get("visual_elements"),
            ambiguities=list(data.get("ambiguities", [])),
        )
        return understanding, usage, elapsed

    def _devise_plan(self, planner_input: PlannerInput, understanding: ProblemUnderstanding, depth: PlanningDepth):
        prompt = build_planning_prompt(planner_input, understanding, depth)
        data, usage, elapsed = self._call_llm_json(stage="devise_plan", prompt=prompt)
        _require_keys(
            data,
            ("algorithmic_pattern", "candidate_strategies", "chosen_strategy",
             "strategy_justification", "complexity"),
            "devise_plan",
            json.dumps(data),
        )
        complexity_data = data["complexity"]
        _require_keys(
            complexity_data,
            ("time_complexity", "space_complexity", "justification"),
            "devise_plan.complexity",
            json.dumps(data),
        )
        solution_plan = SolutionPlan(
            algorithmic_pattern=data["algorithmic_pattern"],
            candidate_strategies=list(data.get("candidate_strategies", [])),
            chosen_strategy=data["chosen_strategy"],
            strategy_justification=data["strategy_justification"],
            complexity=ComplexityEstimate(
                time_complexity=complexity_data["time_complexity"],
                space_complexity=complexity_data["space_complexity"],
                justification=complexity_data["justification"],
            ),
            corner_cases=list(data.get("corner_cases", [])),
        )
        return solution_plan, usage, elapsed

    def _carry_out_plan(self, planner_input: PlannerInput, understanding: ProblemUnderstanding,
                         solution_plan: SolutionPlan, depth: PlanningDepth):
        prompt = build_execution_prompt(planner_input, understanding, solution_plan, depth)
        data, usage, elapsed = self._call_llm_json(stage="carry_out_plan", prompt=prompt)
        _require_keys(data, ("pseudocode",), "carry_out_plan", json.dumps(data))
        execution = ExecutionSketch(
            pseudocode=data["pseudocode"],
            data_structures=list(data.get("data_structures", [])),
            key_steps=list(data.get("key_steps", [])),
        )
        return execution, usage, elapsed

    def _look_back(self, planner_input: PlannerInput, understanding: ProblemUnderstanding,
                    solution_plan: SolutionPlan, execution: ExecutionSketch, depth: PlanningDepth):
        prompt = build_review_prompt(planner_input, understanding, solution_plan, execution, depth)
        data, usage, elapsed = self._call_llm_json(stage="look_back", prompt=prompt)
        review = PlanReview(
            risks=list(data.get("risks", [])),
            verification_checklist=list(data.get("verification_checklist", [])),
            confidence=data.get("confidence", "medium"),
        )
        return review, usage, elapsed

    # -- reactivity / proactivity ----------------------------------------

    def _infer_depth(self, planner_input: PlannerInput) -> PlanningDepth:
        """Reatividade: decide o quão detalhado o plano deve ser a partir do
        conteúdo real do problema, não de um valor fixo."""
        difficulty = (planner_input.difficulty or "").strip().lower()
        if difficulty in _HARD_DIFFICULTIES:
            return PlanningDepth.DETAILED
        if planner_input.images_base64:
            return PlanningDepth.DETAILED
        if len(planner_input.examples) > 3:
            return PlanningDepth.DETAILED

        text = planner_input.statement.lower()
        if any(keyword in text for keyword in _HARD_KEYWORDS):
            return PlanningDepth.DETAILED

        return PlanningDepth.CONCISE

    def _detect_scale_hints(self, planner_input: PlannerInput) -> list[str]:
        """Proatividade: extrai limites numéricos do enunciado/especificação
        de entrada e sinaliza, antes de qualquer execução no Judge, quando a
        escala sugere a necessidade de uma complexidade menor."""
        text = " ".join(filter(None, [planner_input.statement, planner_input.input_spec]))
        max_scale = 0.0
        for match in _SCALE_PATTERN.finditer(text):
            if match.group(2):
                coefficient = float(match.group(1).replace(",", ".")) if match.group(1) else 1.0
                value = coefficient * (10 ** int(match.group(2)))
            elif match.group(3):
                value = float(match.group(3))
            else:
                continue
            max_scale = max(max_scale, value)

        if max_scale >= 10 ** 7:
            return [f"Limites sugerem escala ~{max_scale:.0e}; soluções O(N log N) ou melhores provavelmente são necessárias."]
        if max_scale >= 10 ** 4:
            return [f"Limites sugerem escala ~{max_scale:.0e}; evite complexidade O(N^2) ou pior sem justificativa explícita."]
        return []

    def _cross_check_complexity(self, solution_plan: SolutionPlan, scale_hints: list[str]) -> list[str]:
        """Proatividade: cruza a complexidade escolhida pelo modelo com os
        limites detectados em _detect_scale_hints, mesmo que o próprio modelo
        não tenha sinalizado o conflito."""
        if not scale_hints:
            return []

        complexity = solution_plan.complexity.time_complexity.lower().replace(" ", "")
        if any(pattern in complexity for pattern in _RISKY_COMPLEXITY_PATTERNS):
            return scale_hints + [
                f"A estratégia escolhida tem complexidade '{solution_plan.complexity.time_complexity}', "
                "que pode ser inviável dado o tamanho de entrada sugerido pelo enunciado."
            ]
        return scale_hints

    # -- LLM plumbing -----------------------------------------------------

    def _call_llm_json(self, *, stage: str, prompt: str, images: Optional[list[str]] = None):
        try:
            response = self.__llm.send_prompt_with_usage(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                response_format={"type": "json_object"},
                images=images,
                timeout=self.__timeout,
            )
        except APITimeoutError as exc:
            raise PlannerTimeoutError(
                f"[Planning Agent] Timeout na etapa '{stage}' após {self.__timeout}s"
            ) from exc
        except APIError as exc:
            raise PlannerError(f"[Planning Agent] Erro na chamada ao LLM na etapa '{stage}': {exc}") from exc

        try:
            parsed = json.loads(response.content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise PlannerMalformedResponseError(stage=stage, raw_response=response.content or "", cause=exc) from exc

        if not isinstance(parsed, dict):
            raise PlannerMalformedResponseError(stage=stage, raw_response=response.content or "")

        return parsed, response.usage, response.elapsed_seconds

    def _aggregate_usage(self, usages: list[LLMUsage], elapsed_total: float) -> TokenUsage:
        prompt_tokens = sum(u.prompt_tokens for u in usages)
        completion_tokens = sum(u.completion_tokens for u in usages)
        total_tokens = sum(u.total_tokens for u in usages)
        model = usages[0].model if usages else ""

        input_cost = (prompt_tokens / 1_000_000) * self.__input_price
        output_cost = (completion_tokens / 1_000_000) * self.__output_price

        return TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            input_cost_usd=round(input_cost, 6),
            output_cost_usd=round(output_cost, 6),
            total_cost_usd=round(input_cost + output_cost, 6),
            elapsed_seconds=round(elapsed_total, 3),
        )
