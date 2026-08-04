from typing import Optional


class PlannerError(Exception):
    """Base exception for every failure raised by the Planning Agent."""


class MissingRequiredFieldError(PlannerError):
    """A required field is missing or empty in a PlannerInput payload."""


class PlannerTimeoutError(PlannerError):
    """The underlying LLM call did not return within the configured timeout."""


class PlannerMalformedResponseError(PlannerError):
    """The LLM response could not be parsed into the expected stage schema.

    Carries the stage name and raw text so the caller (Orchestrator, logs,
    or a future retry policy) can inspect what the model actually returned.
    """

    def __init__(self, stage: str, raw_response: str, cause: Optional[Exception] = None):
        self.stage = stage
        self.raw_response = raw_response
        message = f"[Planning Agent] Resposta malformada na etapa '{stage}': {raw_response[:300]!r}"
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause
