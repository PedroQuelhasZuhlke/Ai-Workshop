"""PolicyResult — the outcome of one policy rule evaluated against a candidate."""

from pydantic import BaseModel, ConfigDict


class PolicyResult(BaseModel):
    """One rule's verdict, emitted for every rule evaluated — including passes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_name: str
    passed: bool
    reason: str
