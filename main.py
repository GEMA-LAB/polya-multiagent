import os

from agents import ComprehensionAgent, PlaninngAgent, ExecutationAgent, ReviewAgent
from services import LLM
from dotenv import load_dotenv
from prompt_templates import TEMPLATE_PROMPT

def main ():
    print("Polya Multiagent")
    comprehenshion = ComprehensionAgent()
    planinng = PlaninngAgent()
    executation = ExecutationAgent()
    review = ReviewAgent()
    
    # Example send prompt
    load_dotenv()
    llm = LLM(api_key=os.getenv("API_KEY"),
              base_url=os.getenv("BASE_URL"),
              model=os.getenv("MODEL"))
    
    content_text = llm.send_prompt(TEMPLATE_PROMPT)
    print(content_text)

if __name__ == "__main__":
    main()