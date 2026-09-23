"""The `expand` pipeline stage: turns confirmed `NormalizedRequirement`s into
`SourcingQuery`s.

Purity note: no I/O, no clock, no RNG. A requirement with a non-empty `unresolved`
list has not been confirmed by an engineer yet — sourcing against it would be
sourcing from a value the system itself flagged as unreliable, exactly the
silent-guess failure mode `.github/instructions/pipeline-stages.instructions.md`
forbids. Such requirements are excluded here rather than expanded, and the exclusion
is recorded so it is auditable, not silent.
"""

from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult
from pcbpick.sourcing.types import SourcingQuery


class ExpandStage:
    """Maps each confirmed requirement to exactly one `SourcingQuery`."""

    name = "expand"

    def run(
        self, inp: list[NormalizedRequirement], ctx: StageContext
    ) -> StageResult[list[SourcingQuery]]:
        del ctx  # expand needs no clock or randomness

        queries: list[SourcingQuery] = []
        issues: list[StageIssue] = []

        for requirement in inp:
            if requirement.unresolved:
                issues.append(
                    StageIssue(
                        severity=Severity.INFO,
                        code="requirement_unresolved_excluded_from_sourcing",
                        message=(
                            f"requirement {requirement.requirement_id} has unresolved "
                            f"fields {sorted(requirement.unresolved)}; excluded from "
                            "sourcing until an engineer confirms it"
                        ),
                        item_id=requirement.requirement_id,
                    )
                )
                continue

            queries.append(
                SourcingQuery(
                    requirement_id=requirement.requirement_id,
                    category=requirement.category,
                    parameters=requirement.parameters,
                    footprint=requirement.footprint,
                    specified_mpn=requirement.specified_mpn,
                )
            )

        queries.sort(key=lambda query: query.requirement_id)
        return StageResult(output=queries, issues=issues)
