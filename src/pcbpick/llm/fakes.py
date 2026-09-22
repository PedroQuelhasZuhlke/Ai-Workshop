"""Test/offline `LLMClient` implementations. No live network calls, ever.

Not used by default — the `normalize` stage's default is no client at all (fallback
disabled, matching the M1 precedent for the column-mapping LLM tier). A real provider
client is wired in the same shape as `LLMClient` once credentials exist.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(frozen=True)
class FakeLLMClient:
    """Returns a fixed, pre-recorded JSON response for every call — deterministic, offline."""

    model_id: str
    responses: dict[str, str] = field(default_factory=dict)
    default_response: str | None = None

    def generate(
        self, *, template: str, variables: dict[str, str], response_model: type[BaseModel]
    ) -> str:
        del variables, response_model
        if template in self.responses:
            return self.responses[template]
        if self.default_response is not None:
            return self.default_response
        return "{}"
