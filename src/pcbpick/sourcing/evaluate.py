"""The `evaluate` pipeline stage: attaches a `rationale` to every policy-surviving
candidate. See `.github/instructions/llm-calls.instructions.md` and
`src/pcbpick/llm/templates/candidate_rationale.md` — this is the second (and last)
sanctioned LLM call site.

Purity note: the only I/O this stage performs is the `candidate_rationale` LLM call,
through an injected `LLMClient`. No clock, no RNG. `policy` runs before `evaluate`
(see `docs/architecture.md`), so a `SubstitutionTier.TIER_3` candidate here has
already been rejected and flagged `BLOCKING` by `policy` — this stage never sends
one to the model; it only records why it was skipped, for audit purposes.

The response model `CandidateRationale` is not a versioned contract, same status as
`PrePolicyCandidate` — it never crosses a pipeline-stage boundary on its own, only
its `rationale`/`concerns` fields do, folded into the re-emitted `PartCandidate`.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import SubstitutionTier
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.llm.client import LLMClient, call_structured
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult

TEMPLATE_NAME = "candidate_rationale"
DEFAULT_MAX_LLM_RETRIES = 2

EvaluateStagePair = tuple[NormalizedRequirement, PartCandidate]


class CandidateRationale(BaseModel):
    """The `candidate_rationale` LLM call site's structured response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rationale: str
    concerns: list[str]


@dataclass(frozen=True)
class EvaluateStageInput:
    """One (requirement, candidate) pair per row, mirroring `PolicyStageInput`'s shape."""

    pairs: list[EvaluateStagePair]


def _requirement_prompt_data(requirement: NormalizedRequirement) -> dict[str, object]:
    """Minimized prompt data: category/parameters/footprint/criticality only.

    Never reference designators, project name, or file path — none of those fields
    are even present on `NormalizedRequirement`, so there is nothing to strip here
    beyond simply not including anything but these four fields.
    """
    return {
        "category": requirement.category.value,
        "parameters": {
            name: value.model_dump(mode="json") for name, value in requirement.parameters.items()
        },
        "footprint": requirement.footprint.model_dump(mode="json"),
        "criticality": requirement.criticality.value,
    }


def _candidate_prompt_data(candidate: PartCandidate) -> dict[str, object]:
    """Minimized prompt data: pass/fail summary only, never the full rule reasoning."""
    return {
        "mpn": candidate.mpn,
        "manufacturer": candidate.manufacturer,
        "parameters": {
            name: value.model_dump(mode="json") for name, value in candidate.parameters.items()
        },
        "footprint": candidate.footprint.model_dump(mode="json"),
        "lifecycle": candidate.lifecycle.value,
        "compliance": [tag.value for tag in candidate.compliance],
        "substitution_tier": candidate.substitution_tier.value,
        "policy_results": [
            {"rule_name": result.rule_name, "passed": result.passed}
            for result in candidate.policy_results
        ],
    }


class EvaluateStage:
    """Generates a rationale for every policy-surviving candidate; skips tier-3 rejects."""

    name = "evaluate"

    def __init__(
        self, llm_client: LLMClient | None = None, max_llm_retries: int = DEFAULT_MAX_LLM_RETRIES
    ) -> None:
        self._llm_client = llm_client
        self._max_llm_retries = max_llm_retries

    def run(
        self, inp: EvaluateStageInput, ctx: StageContext
    ) -> StageResult[list[PartCandidate]]:
        del ctx  # evaluate needs no clock or randomness

        output: list[PartCandidate] = []
        issues: list[StageIssue] = []

        for requirement, candidate in inp.pairs:
            if candidate.substitution_tier == SubstitutionTier.TIER_3:
                issues.append(
                    StageIssue(
                        severity=Severity.INFO,
                        code="rationale_skipped_rejected_candidate",
                        message=(
                            f"candidate {candidate.mpn} for requirement "
                            f"{candidate.requirement_id} was rejected at tier 3 by policy; "
                            "no rationale generated and the LLM was never called"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )
                continue

            variables = {
                "requirement": json.dumps(_requirement_prompt_data(requirement), sort_keys=True),
                "candidate": json.dumps(_candidate_prompt_data(candidate), sort_keys=True),
            }
            result = call_structured(
                client=self._llm_client,
                template=TEMPLATE_NAME,
                response_model=CandidateRationale,
                variables=variables,
                max_retries=self._max_llm_retries,
            )

            if result.failed or result.value is None:
                output.append(candidate)
                issues.append(
                    StageIssue(
                        severity=Severity.BLOCKING,
                        code="candidate_rationale_llm_failed",
                        message=(
                            f"rationale generation failed for candidate {candidate.mpn} "
                            f"(requirement {candidate.requirement_id}): "
                            f"{result.error or 'no LLM client configured'}; engineer must "
                            "review policy_results directly"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )
                continue

            output.append(candidate.model_copy(update={"rationale": result.value.rationale}))
            for concern in result.value.concerns:
                issues.append(
                    StageIssue(
                        severity=Severity.WARNING,
                        code="candidate_rationale_concern",
                        message=(
                            f"concern for candidate {candidate.mpn} "
                            f"(requirement {candidate.requirement_id}): {concern}"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )

        output.sort(key=lambda c: (c.requirement_id, c.mpn))
        return StageResult(output=output, issues=issues)
