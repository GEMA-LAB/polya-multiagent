from typing import Optional
from openai import OpenAI

class LLM:
    def __init__(self,
                 api_key: str,
                 base_url: str,
                 model: str,
                 temperature: float = 1.0,
                 top_p: float = 1.0,
                 seed: Optional[int] = None,
                 frequency_penalty: float = 0.0,
                 presence_penalty: float = 0.0):
        
        if not (0.0 <= temperature <= 2.0):
            raise ValueError("[LLM Service]: 0.0 <= temperature <= 2.0")
            
        if not (0.0 <= top_p <= 1.0):
            raise ValueError("[LLM Service]: 0.0 <= top_p <= 1.0")
        
        if not (-2.0 <= frequency_penalty <= 2.0):
            raise ValueError("[LLM Service]: -2.0 <= frequency_penalty <= 2.0")
        
        if not (-2.0 <= presence_penalty <= 2.0):
                    raise ValueError("[LLM Service]: -2.0 <= presence_penalty <= 2.0")
        
        self.__model                = model
        self.__temperature          = temperature
        self.__top_p                = top_p
        self.__seed                 = seed
        self.__frequency_penalty    = frequency_penalty
        self.__presence_penalty     = presence_penalty
        
        self.__client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        
        print("LLM API")
        
    def send_prompt(self,
                    prompt: str,
                    system_prompt: Optional[str] = None,
                    response_format: dict = {"type": "text"}) -> str:

        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        kwargs = {
            "model": self.__model,
            "messages": messages,
            "temperature": self.__temperature,
            "top_p": self.__top_p,
            "seed": self.__seed,
            "frequency_penalty": self.__frequency_penalty,
            "presence_penalty": self.__presence_penalty,
            "response_format": response_format
        }
        
        if self.__seed is not None:
            kwargs["seed"] = self.__seed
        
        response = self.__client.chat.completions.create(**kwargs)
        
        print("Enviando o prompt")
        return response.choices[0].message.content