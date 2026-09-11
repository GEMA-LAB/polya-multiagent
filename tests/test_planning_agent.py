from agents.plannig_agent.main import PlaninngAgent

from tests.conftest import FakeLLM


def test_run_returns_llm_text_output():
    fake = FakeLLM("plano de resolucao gerado")
    agent = PlaninngAgent(llm=fake)

    output = agent.run("Some dois numeros A e B.")

    assert output == "plano de resolucao gerado"
    assert len(fake.calls) == 1


def test_run_includes_input_text_in_the_prompt():
    fake = FakeLLM("plano")
    agent = PlaninngAgent(llm=fake)

    agent.run("Enunciado do problema X.")

    assert "Enunciado do problema X." in fake.calls[0]
