class FakeLLM:
    """Stub LLM used to test PlaninngAgent without hitting a real API."""

    def __init__(self, response: str):
        self._response = response
        self.calls = []

    def send_prompt(self, prompt, system_prompt=None, response_format=None):
        self.calls.append(prompt)
        return self._response
