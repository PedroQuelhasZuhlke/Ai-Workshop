"""The one shape every pipeline stage must satisfy: `(input, ctx) -> StageResult`."""

from typing import Any, Protocol

from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import StageResult


class Stage(Protocol):
    """A pure, named transformation from one artifact type to another."""

    name: str

    def run(self, inp: Any, ctx: StageContext) -> StageResult[Any]: ...
