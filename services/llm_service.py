import time
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI


@dataclass
class LLMUsage:
    """Token accounting for a single completion call."""
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """Completion content plus the usage/timing data needed for cost tracking."""
    content: str
    usage: LLMUsage
    elapsed_seconds: float


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

    @staticmethod
    def _build_user_content(prompt: str, images: Optional[list[str]]):
        """Builds a text-only or multimodal message body.

        `images` items are expected to already be data URIs
        (e.g. "data:image/png;base64,...."), matching the format used by
        `PlannerInput.images_base64` (see agents/plannig_agent/schemas.py).
        """
        if not images:
            return prompt

        content = [{"type": "text", "text": prompt}]
        for image in images:
            content.append({"type": "image_url", "image_url": {"url": image}})
        return content

    def _create_completion(self,
                            prompt: str,
                            system_prompt: Optional[str],
                            response_format: dict,
                            images: Optional[list[str]],
                            timeout: Optional[float]):
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": self._build_user_content(prompt, images)})

        kwargs = {
            "model": self.__model,
            "messages": messages,
            "temperature": self.__temperature,
            "top_p": self.__top_p,
            "frequency_penalty": self.__frequency_penalty,
            "presence_penalty": self.__presence_penalty,
            "response_format": response_format,
        }

        if self.__seed is not None:
            kwargs["seed"] = self.__seed

        if timeout is not None:
            kwargs["timeout"] = timeout

        return self.__client.chat.completions.create(**kwargs)

    def send_prompt(self,
                    prompt: str,
                    system_prompt: Optional[str] = None,
                    response_format: dict = {"type": "text"}) -> str:

        print("Enviando o prompt")
        response = self._create_completion(prompt, system_prompt, response_format, images=None, timeout=None)
        return response.choices[0].message.content

    def send_prompt_with_usage(self,
                                prompt: str,
                                system_prompt: Optional[str] = None,
                                response_format: dict = {"type": "text"},
                                images: Optional[list[str]] = None,
                                timeout: Optional[float] = None) -> LLMResponse:
        """Same call as send_prompt, but also returns token usage and wall-clock
        time, and optionally attaches images (multimodal). Used by agents that
        need to report cost/latency metadata, e.g. the Planning Agent."""

        print("Enviando o prompt")
        started_at = time.monotonic()
        response = self._create_completion(prompt, system_prompt, response_format, images, timeout)
        elapsed = time.monotonic() - started_at

        usage = response.usage
        return LLMResponse(
            content=response.choices[0].message.content,
            usage=LLMUsage(
                model=self.__model,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            elapsed_seconds=elapsed,
        )
