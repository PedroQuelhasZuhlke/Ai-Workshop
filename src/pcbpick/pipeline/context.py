"""The typed context every stage receives instead of touching the clock or the RNG."""

from dataclasses import dataclass
from datetime import datetime
from random import Random

from pydantic import BaseModel, ConfigDict


class PipelineConfig(BaseModel):
    """Per-stage settings passed through `StageContext.config`.

    Unlike the artifact contracts, this allows unknown keys: stages own their own
    config shape and land here incrementally as they're built in later milestones,
    without requiring a change to this base type.
    """

    model_config = ConfigDict(frozen=True, extra="allow")


@dataclass(frozen=True)
class StageContext:
    """Everything a stage may use instead of the wall clock, RNG, or environment."""

    run_id: str
    now: datetime
    rng: Random
    config: PipelineConfig
