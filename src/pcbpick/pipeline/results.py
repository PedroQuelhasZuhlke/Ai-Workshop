"""Stage output envelope: the artifact plus every issue recorded while producing it."""

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """How urgently an issue must be resolved before a requirement can proceed."""

    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class StageIssue:
    """One recorded problem. Stages never raise on bad input data — they record this."""

    severity: Severity
    code: str
    message: str
    item_id: str | None = None


@dataclass(frozen=True)
class StageResult[OutputT]:
    """What every `Stage.run` returns: the new artifact plus its issues."""

    output: OutputT
    issues: list[StageIssue] = field(default_factory=list)
