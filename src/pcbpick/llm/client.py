"""The structured-call boundary shared by the two sanctioned LLM call sites.

See `.github/instructions/llm-calls.instructions.md`. Every call declares a Pydantic
response model and validates against it; a validation failure retries up to
`max_retries` with the error fed back, then degrades to a recorded failure — never a
crash, never a silent default.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError


class LLMClient(Protocol):
    """The minimal boundary a real provider client must satisfy.

    `generate` returns raw text the caller will validate against `response_model` —
    the client itself does no parsing or retrying, `call_structured` owns that.
    """

    model_id: str

    def generate(
        self, *, template: str, variables: dict[str, str], response_model: type[BaseModel]
    ) -> str: ...


@dataclass(frozen=True)
class StructuredCallResult[ModelT]:
    """Outcome of a `call_structured` invocation — never raises on a bad response."""

    value: ModelT | None
    failed: bool
    attempts: int
    error: str | None = None


def call_structured[ModelT: BaseModel](
    *,
    client: LLMClient | None,
    template: str,
    response_model: type[ModelT],
    variables: dict[str, str],
    max_retries: int = 2,
) -> StructuredCallResult[ModelT]:
    """Call `client.generate`, validate against `response_model`, retry on failure.

    `client=None` means no provider is configured — degrades immediately to a
    recorded failure, exactly like a validation failure that exhausted its retries.
    """
    if client is None:
        return StructuredCallResult(
            value=None, failed=True, attempts=0, error="no LLM client configured"
        )

    last_error: str | None = None
    for attempt in range(1, max_retries + 2):
        raw = client.generate(template=template, variables=variables, response_model=response_model)
        try:
            value = response_model.model_validate_json(raw)
        except ValidationError as exc:
            last_error = str(exc)
            continue
        return StructuredCallResult(value=value, failed=False, attempts=attempt)
    return StructuredCallResult(value=None, failed=True, attempts=max_retries + 1, error=last_error)
