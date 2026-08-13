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


def test_scale_hint_and_complexity_cross_check_flags_risky_plan():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    # override the plan stage response with an O(N^2) strategy for a large N
    fake._responses[1] = fake._responses[1].replace('"time_complexity": "O(N)"', '"time_complexity": "O(N^2)"')

    problem = make_planner_input(input_spec="1 <= N <= 10^6")
    output = agent.plan(problem)

    assert any("N^2" in risk or "inviável" in risk for risk in output.review.risks)


def test_to_prompt_section_is_injectable_markdown():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    output = agent.plan(make_planner_input())
    section = output.to_prompt_section()

    assert "Plano de Resolução" in section
    assert "kadane" in section
    assert "```" in section
