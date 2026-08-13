import json
import math

import pytest

from agents.plannig_agent import (
    JudgeAttemptFeedback,
    MissingRequiredFieldError,
    PlaninngAgent,
    PlannerMalformedResponseError,
)

from tests.conftest import FakeLLM, canned_stage_responses, make_planner_input


def test_validate_missing_statement_raises():
    problem = make_planner_input(statement="   ")
    with pytest.raises(MissingRequiredFieldError):
        problem.validate()


def test_validate_missing_problem_id_raises():
    problem = make_planner_input(problem_id="")
    with pytest.raises(MissingRequiredFieldError):
        problem.validate()


def test_plan_produces_all_four_polya_sections():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    output = agent.plan(make_planner_input())

    assert "subvetor" in output.understanding.restatement
    assert output.plan.chosen_strategy == "kadane"
    assert "cur" in output.execution_sketch.pseudocode
    assert output.review.confidence == "high"
    assert output.iteration == 1
    assert len(fake.calls) == 4


def test_plan_aggregates_token_usage_and_cost_across_all_stages():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake, input_price=1.0, output_price=2.0)

    output = agent.plan(make_planner_input())

    # 4 stages x (10 prompt + 20 completion) tokens each
    assert output.metadata.prompt_tokens == 40
    assert output.metadata.completion_tokens == 80
    assert output.metadata.total_tokens == 120
    assert output.metadata.model == "fake-model"
    # cost = (40/1e6)*1.0 + (80/1e6)*2.0
    assert output.metadata.total_cost_usd == pytest.approx(0.00020, abs=1e-9)


def test_plan_forwards_images_only_to_understanding_stage():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    problem = make_planner_input(images_base64=["data:image/png;base64,AAAA"])
    agent.plan(problem)

    assert fake.calls[0]["images"] == ["data:image/png;base64,AAAA"]
    assert fake.calls[1]["images"] is None
    assert fake.calls[2]["images"] is None
    assert fake.calls[3]["images"] is None


def test_malformed_json_raises_planner_malformed_response_error():
    fake = FakeLLM(["isto nao e json"])
    agent = PlaninngAgent(llm=fake)

    with pytest.raises(PlannerMalformedResponseError):
        agent.plan(make_planner_input())


def test_missing_required_key_in_llm_response_raises():
    fake = FakeLLM(['{"restatement": "so isso"}'])
    agent = PlaninngAgent(llm=fake)

    with pytest.raises(PlannerMalformedResponseError):
        agent.plan(make_planner_input())


def test_replan_appends_previous_attempt_and_bumps_iteration():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    problem = make_planner_input()
    feedback = JudgeAttemptFeedback(attempt_number=1, verdict="TLE", details="excedeu tempo no caso 7")

    output = agent.replan(problem, feedback)

    assert problem.previous_attempts == [feedback]
    assert output.iteration == 2
    # the feedback block must have reached at least one of the prompts
    assert any("TLE" in call["prompt"] for call in fake.calls)


def test_depth_inference_reacts_to_hard_signals():
    agent = PlaninngAgent(llm=FakeLLM([]))

    easy = make_planner_input(statement="Some dois numeros a e b e imprima o resultado.", difficulty="facil")
    hard = make_planner_input(statement="Encontre o menor caminho em um grafo com N vertices.", difficulty="dificil")
    with_images = make_planner_input(images_base64=["data:image/png;base64,AAAA"])

    assert agent._infer_depth(easy).value == "concise"
    assert agent._infer_depth(hard).value == "detailed"
    assert agent._infer_depth(with_images).value == "detailed"


def test_complexity_budget_flags_infeasible_plan_and_downgrades_confidence():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    # override the plan stage response with an O(N^2) strategy for a large N
    fake._responses[1] = fake._responses[1].replace('"time_complexity": "O(N)"', '"time_complexity": "O(N^2)"')

    problem = make_planner_input(input_spec="1 <= N <= 10^6")
    output = agent.plan(problem)

    assert output.review.complexity_feasible is False
    assert "ACIMA do orçamento" in output.review.complexity_budget_note
    assert output.review.confidence == "low"
    assert any("ACIMA do orçamento" in risk for risk in output.review.risks)


def test_complexity_budget_accepts_feasible_plan():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    problem = make_planner_input(input_spec="1 <= N <= 200000", time_limit_seconds=2.0)
    output = agent.plan(problem)

    # O(N) for N <= 200000 within a 2s budget is comfortably feasible
    assert output.review.complexity_feasible is True
    assert output.review.confidence == "high"


def test_complexity_budget_ignores_unrelated_value_bounds():
    """Regression test: a bound on a value (A, B) must not be mistaken for
    a bound on input size (N), otherwise a trivial O(1) problem gets
    flagged as if it needed a smaller complexity."""
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    scale = agent._extract_scale(make_planner_input(
        statement="Leia dois inteiros A e B.",
        input_spec="-10^9 <= A, B <= 10^9",
    ))

    assert scale == 0.0


def test_verify_trace_against_examples_detects_mismatch_and_downgrades_confidence():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    # the pseudocode's traced output disagrees with the real expected output
    fake._responses[2] = fake._responses[2].replace('"traced_outputs": ["4"]', '"traced_outputs": ["3"]')

    output = agent.plan(make_planner_input())

    assert len(output.review.trace_checks) == 1
    assert output.review.trace_checks[0].matches is False
    assert output.review.trace_checks[0].expected_output == "4"
    assert output.review.trace_checks[0].traced_output == "3"
    assert output.review.confidence == "low"
    assert any("não bateu" in risk for risk in output.review.risks)


def test_verify_trace_against_examples_accepts_matching_trace():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    output = agent.plan(make_planner_input())

    assert len(output.review.trace_checks) == 1
    assert output.review.trace_checks[0].matches is True


def test_justification_quality_gate_flags_generic_justification_and_downgrades_confidence():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    fake._responses[1] = fake._responses[1].replace(
        json.dumps(
            "kadane e O(N), o que atende ao limite de N <= 200000; a alternativa "
            "forca bruta seria O(N^2), inviavel para esse tamanho de entrada."
        ),
        json.dumps("parece uma boa ideia"),
    )

    output = agent.plan(make_planner_input())

    assert output.review.justification_quality_issues
    assert output.review.confidence == "low"


def test_justification_quality_gate_accepts_quantified_comparative_justification():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    output = agent.plan(make_planner_input())

    assert output.review.justification_quality_issues == []


def test_approx_operations_distinguishes_log_variants():
    """Regression test: 'O((N + M) log N)' must not be classified as pure
    O(log N) just because 'log' appears next to a size variable."""
    agent = PlaninngAgent(llm=FakeLLM([]))
    n = 1_000_000

    pure_log = agent._approx_operations("O(log N)", n)
    n_log_n = agent._approx_operations("O(N log N)", n)
    sum_log_n = agent._approx_operations("O((N + M) log N)", n)

    assert pure_log == pytest.approx(math.log2(n))
    assert n_log_n == pytest.approx(n * math.log2(n))
    assert sum_log_n == pytest.approx(n * math.log2(n))
    assert pure_log < n_log_n


def test_to_prompt_section_is_injectable_markdown():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    output = agent.plan(make_planner_input())
    section = output.to_prompt_section()

    assert "Plano de Resolução" in section
    assert "kadane" in section
    assert "```" in section
