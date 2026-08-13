"""Typed I/O contract for the Planning Agent (Agente Planejador).

The rest of the repository has no pydantic dependency and no established
schema convention yet (see docs/agente-planejador/interface.md for the
adaptation note), so this module uses stdlib `dataclasses` to keep the
contract typed without adding a new dependency.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .errors import MissingRequiredFieldError


class PlanningDepth(str, Enum):
    """How much detail the agent should produce for a given problem.

    Set by PlaninngAgent._infer_depth() -- the Planning Agent's reactivity:
    it reacts to difficulty, presence of images, and statement keywords
    instead of always planning at the same depth.
    """
    CONCISE = "concise"
    DETAILED = "detailed"


@dataclass
class TestCaseExample:
    """One sample input/output pair taken from the problem statement."""
    input: str
    output: str
    explanation: Optional[str] = None


@dataclass
class JudgeAttemptFeedback:
    """Verdict from a previous Judge run, used to feed the replan() loop."""
    attempt_number: int
    verdict: str  # "AC" | "WA" | "CE" | "RE" | "TLE"
    details: Optional[str] = None
    failing_test_case: Optional[str] = None


@dataclass
class PlannerInput:
    """What the Orchestrator hands to the Planning Agent for one problem."""
    problem_id: str
    statement: str
    input_spec: Optional[str] = None
    output_spec: Optional[str] = None
    examples: list[TestCaseExample] = field(default_factory=list)
    images_base64: list[str] = field(default_factory=list)
    difficulty: Optional[str] = None
    time_limit_seconds: Optional[float] = None
    memory_limit_mb: Optional[float] = None
    previous_attempts: list[JudgeAttemptFeedback] = field(default_factory=list)

    def validate(self) -> None:
        if not self.problem_id or not self.problem_id.strip():
            raise MissingRequiredFieldError("PlannerInput.problem_id é obrigatório e não pode ser vazio.")
        if not self.statement or not self.statement.strip():
            raise MissingRequiredFieldError("PlannerInput.statement é obrigatório e não pode ser vazio.")


@dataclass
class ProblemUnderstanding:
    """Pólya step 1 -- Understand the problem."""
    restatement: str
    inputs_description: str
    outputs_description: str
    constraints: list[str] = field(default_factory=list)
    visual_elements: Optional[str] = None
    ambiguities: list[str] = field(default_factory=list)


@dataclass
class ComplexityEstimate:
    time_complexity: str
    space_complexity: str
    justification: str


@dataclass
class SolutionPlan:
    """Pólya step 2 -- Devise a plan."""
    algorithmic_pattern: str
    candidate_strategies: list[str]
    chosen_strategy: str
    strategy_justification: str
    complexity: ComplexityEstimate
    corner_cases: list[str] = field(default_factory=list)


@dataclass
class ExecutionSketch:
    """Pólya step 3 -- Carry out the plan (pseudocode, not final source code;
    turning this into Python/C++ remains the Coding Agent's job)."""
    pseudocode: str
    data_structures: list[str] = field(default_factory=list)
    key_steps: list[str] = field(default_factory=list)
    traced_outputs: list[str] = field(default_factory=list)
    """Model's manual, step-by-step simulation of `pseudocode` against each
    entry of PlannerInput.examples, in the same order. Grounds the
    "algoritmo correto" check: PlaninngAgent._verify_trace_against_examples()
    compares this, in code, against the real expected output -- it is not
    just the model asserting its own solution is correct."""


@dataclass
class TraceCheck:
    """Result of comparing one traced_outputs entry against the real
    expected output of the corresponding example, computed in code (not by
    the LLM) by PlaninngAgent._verify_trace_against_examples()."""
    example_index: int
    expected_output: str
    traced_output: str
    matches: bool


@dataclass
class PlanReview:
    """Pólya step 4 -- Look back."""
    risks: list[str] = field(default_factory=list)
    verification_checklist: list[str] = field(default_factory=list)
    confidence: str = "medium"  # "low" | "medium" | "high"
    trace_checks: list[TraceCheck] = field(default_factory=list)
    """Code-computed, per PlaninngAgent._verify_trace_against_examples() --
    supports the "algoritmo correto" criterion with a grounded signal
    instead of relying only on the LLM's self-report."""
    complexity_feasible: Optional[bool] = None
    """Code-computed, per PlaninngAgent._estimate_complexity_budget() -- an
    operation-count budget check (time_limit_seconds x ~1e8 ops/s) against
    the chosen time_complexity for the scale detected in the statement.
    None when no size limit could be detected. Supports "complexidade
    correta" with a quantified signal instead of only keyword matching."""
    complexity_budget_note: Optional[str] = None
    """Human-readable explanation of the complexity_feasible computation."""
    justification_quality_issues: list[str] = field(default_factory=list)
    """Code-computed, per PlaninngAgent._assess_justification_quality() --
    structural gaps in strategy_justification/complexity.justification
    (too short, no reference to a concrete limit, no comparison against a
    discarded alternative). Empty means no issue was detected. Supports
    "qualidade da justificativa" with a deterministic, repeatable check."""


@dataclass
class TokenUsage:
    """Cost/latency metadata, aggregated across the 4 Pólya-stage LLM calls."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_cost_usd: Optional[float] = None
    output_cost_usd: Optional[float] = None
    total_cost_usd: Optional[float] = None
    elapsed_seconds: float = 0.0


@dataclass
class PlannerOutput:
    """What the Planning Agent hands back to the Orchestrator / Coding Agent."""
    problem_id: str
    understanding: ProblemUnderstanding
    plan: SolutionPlan
    execution_sketch: ExecutionSketch
    review: PlanReview
    metadata: TokenUsage
    iteration: int = 1

    def to_prompt_section(self) -> str:
        """Renders the plan as a Markdown block meant to be injected into the
        Coding Agent's prompt (see prompt_templates/coder_prompt.py)."""

        corner_cases = "\n".join(f"- {c}" for c in self.plan.corner_cases) or "- (nenhum identificado)"
        risks = "\n".join(f"- {r}" for r in self.review.risks) or "- (nenhum identificado)"
        checklist = "\n".join(f"- [ ] {c}" for c in self.review.verification_checklist) or "- [ ] (nenhum item)"

        failed_traces = [c for c in self.review.trace_checks if not c.matches]
        warning = ""
        if failed_traces or self.review.complexity_feasible is False:
            warning = (
                "\n> ⚠️ **Este plano falhou em verificações automáticas** "
                f"(confiança rebaixada para '{self.review.confidence}'). "
                "Revise a estratégia e o pseudocódigo antes de traduzi-los em código.\n"
            )

        return (
            "## Plano de Resolução (gerado pelo Agente Planejador, método de Pólya)\n"
            f"{warning}\n"
            f"### 1. Compreensão do problema\n{self.understanding.restatement}\n\n"
            f"**Entrada:** {self.understanding.inputs_description}\n\n"
            f"**Saída:** {self.understanding.outputs_description}\n\n"
            f"### 2. Estratégia escolhida\n"
            f"**Padrão algorítmico:** {self.plan.algorithmic_pattern}\n\n"
            f"**Estratégia:** {self.plan.chosen_strategy} -- {self.plan.strategy_justification}\n\n"
            f"**Complexidade estimada:** tempo {self.plan.complexity.time_complexity}, "
            f"espaço {self.plan.complexity.space_complexity} "
            f"({self.plan.complexity.justification})\n\n"
            f"**Corner cases a tratar:**\n{corner_cases}\n\n"
            f"### 3. Pseudocódigo\n```\n{self.execution_sketch.pseudocode}\n```\n\n"
            f"### 4. Riscos e checklist de verificação\n"
            f"**Riscos:**\n{risks}\n\n"
            f"**Checklist de verificação:**\n{checklist}\n"
        )
