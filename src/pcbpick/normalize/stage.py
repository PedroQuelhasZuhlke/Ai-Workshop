"""The `normalize`+`classify` pipeline stage: turns `IngestResult` into `NormalizedRequirement`s.

Purity note: the only "I/O" this stage can perform is the sanctioned `normalize_fallback`
LLM call site, and only through an injected `LLMClient` — no direct network access,
no clock, no randomness. DNP lines (`BomLine.populate=False`) are excluded from
sourcing here, per `BomLine.populate`'s contract doc; they remain visible in the
upstream `ingest` artifact, which is the audit anchor for them.
"""

from pcbpick.contracts.mapping import IngestResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.llm.client import LLMClient
from pcbpick.normalize.requirement_builder import build_requirement
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult

DEFAULT_MAX_LLM_RETRIES = 2


class NormalizeStage:
    """Reads ingested `BomLine`s and emits `NormalizedRequirement`s, one per populated line."""

    name = "normalize"

    def __init__(
        self, llm_client: LLMClient | None = None, max_llm_retries: int = DEFAULT_MAX_LLM_RETRIES
    ) -> None:
        self._llm_client = llm_client
        self._max_llm_retries = max_llm_retries

    def run(
        self, inp: IngestResult, ctx: StageContext
    ) -> StageResult[list[NormalizedRequirement]]:
        del ctx  # normalize needs no clock or randomness

        requirements: list[NormalizedRequirement] = []
        issues: list[StageIssue] = []
        excluded_dnp = 0

        for line in inp.lines:
            if not line.populate:
                excluded_dnp += 1
                continue
            requirement, line_issues = build_requirement(
                line,
                row_index=line.row_index,
                llm_client=self._llm_client,
                max_llm_retries=self._max_llm_retries,
            )
            requirements.append(requirement)
            issues.extend(line_issues)
            if requirement.unresolved:
                issues.append(
                    StageIssue(
                        severity=Severity.BLOCKING,
                        code="normalization_unresolved",
                        message=(
                            f"requirement {requirement.requirement_id} has unresolved fields: "
                            f"{', '.join(requirement.unresolved)}"
                        ),
                        item_id=requirement.requirement_id,
                    )
                )

        if excluded_dnp:
            issues.append(
                StageIssue(
                    severity=Severity.INFO,
                    code="dnp_lines_excluded",
                    message=f"{excluded_dnp} do-not-populate line(s) excluded from sourcing",
                )
            )

        requirements.sort(key=lambda r: r.requirement_id)
        return StageResult(output=requirements, issues=issues)
