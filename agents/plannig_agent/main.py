import os
from typing import Optional

from dotenv import load_dotenv

from services import LLM
from prompt_templates import PLANNING_PROMPT_TEMPLATE


class PlaninngAgent:
    def __init__(self, llm: Optional[LLM] = None):
        load_dotenv()

        if llm is None:
            llm = LLM(
                api_key=os.getenv("API_KEY"),
                base_url=os.getenv("BASE_URL"),
                model=os.getenv("MODEL"),
            )

        self.__llm = llm

        print("Init Planning")

    def run(self, input_text: str) -> str:
        """Etapa 2 de Pólya (elaborar um plano): recebe o problema (texto)
        e devolve um plano de resolução (texto)."""
        prompt = PLANNING_PROMPT_TEMPLATE.format(input_text=input_text)
        return self.__llm.send_prompt(prompt)
