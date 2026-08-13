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
- Comportamento proativo: _estimate_complexity_budget() antecipa problemas de
  desempenho (orçamento de operações vs. complexidade escolhida) antes que
  apareçam como TLE no Judge; _verify_trace_against_examples() confere o
  pseudocódigo contra a saída real dos exemplos antes de qualquer código
  ser escrito; _assess_justification_quality() sinaliza justificativas
  genéricas. Os três alimentam `review` mesmo que o modelo não tenha
  percebido o problema sozinho, e rebaixam `review.confidence`
  automaticamente quando falham (ver plan()).
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
import math
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
    TraceCheck,
)

_HARD_KEYWORDS = (
    "grafo", "graph", "árvore", "arvore", "tree", "dp", "programação dinâmica",
    "programacao dinamica", "dynamic programming", "menor caminho", "shortest path",
    "componente conexa", "union-find", "dsu", "topologic",
)
_HARD_DIFFICULTIES = {"hard", "dificil", "difícil", "avancado", "avançado", "ouro", "gold"}

# Matches a numeric bound, either scientific ("2 x 10^5", "10^6") or plain
# (4+ digits). Used only inside a small window right after a size-variable
# anchor (see _SIZE_VAR_ANCHOR) so that value bounds unrelated to input size
# (e.g. "-10^9 <= A, B <= 10^9" for two summands) are not mistaken for N.
_SCALE_PATTERN = re.compile(r"(?:(\d+(?:[.,]\d+)?)\s*[x*]?\s*)?10\s*\^\s*(\d+)|(\d{4,})")

# Canonical size-variable names used in OBI/competitive-programming
# statements ("1 <= N <= 200000", "N (número de vértices) <= 10^5", ...).
_SIZE_VAR_ANCHOR = re.compile(r"\b([NMQKT])\b\s*(?:\([^)]*\))?\s*(?:<=|≤)")

_OPS_PER_SECOND = 1e8  # common competitive-programming rule of thumb


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

        self._apply_deterministic_checks(planner_input, solution_plan, execution, review)

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
            traced_outputs=[str(o) for o in data.get("traced_outputs", [])],
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

    # -- deterministic checks (código, não LLM) --------------------------
    #
    # As três checagens abaixo sustentam, com sinais computados (não apenas
    # auto-relatados pelo modelo), os critérios "algoritmo correto",
    # "complexidade correta" e "qualidade da justificativa": ver
    # docs/agente-planejador/interface.md.

    def _apply_deterministic_checks(self, planner_input: PlannerInput, solution_plan: SolutionPlan,
                                     execution: ExecutionSketch, review: PlanReview) -> None:
        trace_checks = self._verify_trace_against_examples(planner_input, execution)
        complexity_feasible, budget_note = self._estimate_complexity_budget(planner_input, solution_plan)
        justification_issues = self._assess_justification_quality(solution_plan)

        review.trace_checks = trace_checks
        review.complexity_feasible = complexity_feasible
        review.complexity_budget_note = budget_note
        review.justification_quality_issues = justification_issues

        new_risks = []
        failed_traces = [c for c in trace_checks if not c.matches]
        for check in failed_traces:
            new_risks.append(
                f"Rastreamento manual do pseudocódigo não bateu com o exemplo {check.example_index + 1} "
                f"(esperado: {check.expected_output!r}, obtido: {check.traced_output!r})."
            )
        if complexity_feasible is False:
            new_risks.append(budget_note)
        new_risks.extend(justification_issues)

        review.risks = _dedup(review.risks + new_risks)

        if failed_traces or complexity_feasible is False or justification_issues:
            review.confidence = "low"

    @staticmethod
    def _normalize_output(text: str) -> str:
        return " ".join(text.split())

    def _verify_trace_against_examples(self, planner_input: PlannerInput,
                                        execution: ExecutionSketch) -> list[TraceCheck]:
        """'Algoritmo correto': compara, em código, o que o modelo alega que
        o pseudocódigo produziria (ExecutionSketch.traced_outputs) contra a
        saída real de cada exemplo -- não é o modelo apenas afirmando que
        está certo."""
        checks = []
        for i, example in enumerate(planner_input.examples):
            traced = execution.traced_outputs[i] if i < len(execution.traced_outputs) else ""
            matches = bool(traced) and self._normalize_output(traced) == self._normalize_output(example.output)
            checks.append(TraceCheck(
                example_index=i,
                expected_output=example.output,
                traced_output=traced,
                matches=matches,
            ))
        return checks

    def _extract_scale(self, planner_input: PlannerInput) -> float:
        """Extrai o maior limite numérico associado a uma variável de
        tamanho canônica (N, M, Q, K, T), procurando em uma janela curta
        logo após ocorrências de "N <=", "M <=" etc. Ancorar na variável
        evita confundir limites de valor (ex.: "-10^9 <= A, B <= 10^9" para
        dois números somados) com limites de tamanho de entrada."""
        text = " ".join(filter(None, [planner_input.input_spec, planner_input.statement]))
        max_scale = 0.0
        for anchor in _SIZE_VAR_ANCHOR.finditer(text):
            window = text[anchor.end():anchor.end() + 20]
            match = _SCALE_PATTERN.search(window)
            if not match:
                continue
            if match.group(2):
                coefficient = float(match.group(1).replace(",", ".")) if match.group(1) else 1.0
                value = coefficient * (10 ** int(match.group(2)))
            elif match.group(3):
                value = float(match.group(3))
            else:
                continue
            max_scale = max(max_scale, value)
        return max_scale

    @staticmethod
    def _approx_operations(complexity: str, n: float) -> Optional[float]:
        """Estima grosseiramente o número de operações de uma notação
        Big-O em texto livre, para N dado. Necessariamente heurístico --
        complexidade é texto livre do LLM, não uma expressão estruturada --
        mas dá um número para comparar com o orçamento de operações, em vez
        de só casar substrings como "n^2".

        O caso "log" precisa de cuidado: "(N + M) log N", "N log N" e
        "log N" sozinho devem virar estimativas bem diferentes. Em vez de
        checar substrings fixas tipo "nlogn" (que não bate com "(N+M)
        log N"), removemos o termo "log(...)" da string e checamos se
        ainda sobra alguma variável de tamanho (N/M/Q/K) fora dele -- se
        sobrar, é um fator multiplicativo (N log N); se não sobrar, é
        log N "puro"."""
        c = complexity.lower().replace(" ", "")
        n = max(n, 2.0)
        try:
            if "n!" in c:
                return math.factorial(min(int(n), 20)) if n <= 20 else math.inf
            if "2^n" in c:
                return 2.0 ** min(n, 60)
            if "n^3" in c or "n³" in c:
                return n ** 3
            if "n^2" in c or "n²" in c:
                return n ** 2
            if "sqrt(n)" in c or "n^0.5" in c or "√n" in c:
                return n ** 0.5
            if "log" in c:
                log_n = math.log2(n)
                outside_log = re.sub(r"log2?\(?[a-z0-9+*]*\)?", "", c)
                has_extra_size_var = bool(re.search(r"[nmqk]", outside_log))
                return n * log_n if has_extra_size_var else log_n
            if c.strip("o() ") in ("1", ""):
                return 1.0
            # padrão: trata como aproximadamente linear (O(N), O(N+M), etc.)
            return n
        except OverflowError:
            return math.inf

    def _estimate_complexity_budget(self, planner_input: PlannerInput,
                                     solution_plan: SolutionPlan) -> tuple[Optional[bool], Optional[str]]:
        """'Complexidade correta': em vez de casar palavras-chave, calcula
        um orçamento de operações (limite de tempo x ~1e8 op/s, regra
        prática comum em programação competitiva) e compara com a
        complexidade escolhida aplicada à escala de N detectada. Devolve
        (None, None) quando nenhuma escala pôde ser detectada -- nesse
        caso não há base para julgar."""
        n = self._extract_scale(planner_input)
        if n <= 0:
            return None, None

        time_limit = planner_input.time_limit_seconds or 1.0
        budget = time_limit * _OPS_PER_SECOND
        approx_ops = self._approx_operations(solution_plan.complexity.time_complexity, n)
        if approx_ops is None:
            return None, None

        feasible = approx_ops <= budget
        note = (
            f"Orçamento de complexidade: N~{n:.0e}, limite de tempo "
            f"{'informado' if planner_input.time_limit_seconds else 'assumido (não informado)'} "
            f"de {time_limit:.1f}s -> orçamento ~{budget:.0e} operações; complexidade "
            f"'{solution_plan.complexity.time_complexity}' estimada em ~{approx_ops:.0e} operações "
            f"({'dentro do orçamento' if feasible else 'ACIMA do orçamento, risco real de TLE'})."
        )
        return feasible, note

    def _assess_justification_quality(self, solution_plan: SolutionPlan) -> list[str]:
        """'Qualidade da justificativa': checagem estrutural determinística
        (não um juiz de LLM) -- garante que a justificativa não é
        genérica: tem tamanho mínimo, cita algum número dos limites do
        problema, e (quando há alternativas) menciona por que ao menos uma
        foi descartada."""
        issues = []
        justification = solution_plan.strategy_justification.strip()
        if len(justification) < 20:
            issues.append("Justificativa da estratégia é muito curta/genérica.")
        if not re.search(r"\d", justification):
            issues.append("Justificativa da estratégia não cita nenhum valor numérico dos limites do problema.")

        other_strategies = [
            s for s in solution_plan.candidate_strategies if s != solution_plan.chosen_strategy
        ]
        if other_strategies:
            mentioned = any(
                word in justification.lower()
                for strategy in other_strategies
                for word in re.findall(r"\w+", strategy.lower())
                if len(word) > 3
            )
            if not mentioned:
                issues.append("Justificativa não explica por que as estratégias alternativas foram descartadas.")

        complexity_justification = solution_plan.complexity.justification.strip()
        if len(complexity_justification) < 15:
            issues.append("Justificativa da complexidade é muito curta/genérica.")

        return issues

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
