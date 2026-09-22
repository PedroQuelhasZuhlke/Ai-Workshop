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


class RunManifest(BaseModel):
    """The `meta.json` written once per run and rewritten after every stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    created_at: datetime
    source_file: str
    source_file_sha256: str
    stages: list[StageMeta] = Field(default_factory=list)
