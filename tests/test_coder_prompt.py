from agents.plannig_agent import PlaninngAgent
from prompt_templates import build_coder_prompt

from tests.conftest import FakeLLM, canned_stage_responses, make_planner_input


def test_build_coder_prompt_injects_plan_before_final_instruction():
    fake = FakeLLM(canned_stage_responses())
    agent = PlaninngAgent(llm=fake)

    problem = make_planner_input()
    plan = agent.plan(problem)

    prompt = build_coder_prompt(problem.statement, plan)

    assert problem.statement in prompt
    assert "Plano de Resolução" in prompt
    assert prompt.index("Plano de Resolução") < prompt.index("Instrução final")
    assert "kadane" in prompt
