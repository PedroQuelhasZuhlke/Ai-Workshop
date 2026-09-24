"""Run manifest bookkeeping. Not a domain contract — see docs/data-contracts.md for those."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StageMeta(BaseModel):
    """Recorded once per stage execution: what ran, on what, for how long."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    stage_name: str
    input_hash: str
    config_hash: str
    duration_seconds: float
    issue_counts: dict[str, int]
    # Additive (M8): the same issues `issue_counts` already tallies by severity,
    # tallied instead by `StageIssue.code` -- e.g. `llm_fallback_unavailable`,
    # `candidate_rationale_llm_failed`, `catalog_details_missing`. This is the one
    # generic substrate both the LLM fallback/failure rate and any future
    # supplier-adapter error rate can be read from without a second, parallel
    # counting mechanism (`sourcing/suppliers/resilience.py`'s `CircuitBreaker`
    # tracks consecutive failures for its own trip/cooldown decision, but does not
    # expose a cumulative call/failure count today -- adding one there is flagged as
    # a follow-up, not duplicated here with a second, less authoritative tally).
    issue_code_counts: dict[str, int] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """The `meta.json` written once per run and rewritten after every stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    created_at: datetime
    source_file: str
    source_file_sha256: str
    stages: list[StageMeta] = Field(default_factory=list)
