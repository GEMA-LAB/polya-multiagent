from agents import ComprehensionAgent, PlaninngAgent, ExecutationAgent, ReviewAgent
from agents.plannig_agent import PlannerInput, TestCaseExample
from dotenv import load_dotenv
from prompt_templates import build_coder_prompt


def main():
    print("Polya Multiagent")

    # ComprehensionAgent, ExecutationAgent (futuro Agente Executor) e
    # ReviewAgent ainda não estão implementados -- ver docs/agentes/ para
    # o escopo previsto de cada um.
    comprehenshion = ComprehensionAgent()
    executation = ExecutationAgent()
    review = ReviewAgent()

    load_dotenv()

    # Pipeline: Problema -> Agente Planejador -> Plano -> Agente Codificador (TODO)
    planning = PlaninngAgent()

    problem = PlannerInput(
        problem_id="obi-exemplo-01",
        statement=(
            "Dada uma lista de N inteiros, determine a soma máxima de um "
            "subvetor contíguo não vazio (problema do subvetor de soma máxima)."
        ),
        input_spec="A primeira linha contém N (1 <= N <= 200000). A segunda linha contém N inteiros.",
        output_spec="Um único inteiro: a soma máxima encontrada.",
        examples=[TestCaseExample(input="4\n-2 1 -3 4", output="4")],
        difficulty="medio",
    )

    plan = planning.plan(problem)
    print(plan.to_prompt_section())

    coder_prompt = build_coder_prompt(problem.statement, plan)
    print("\n--- Prompt para o Agente Codificador (ainda não implementado) ---")
    print(coder_prompt)


if __name__ == "__main__":
    main()
