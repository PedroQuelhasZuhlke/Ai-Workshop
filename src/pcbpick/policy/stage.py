"""The `policy` pipeline stage: scores each requirement/candidate pair.

Purity note: no I/O, no clock, no RNG — every rule in `pcbpick.policy.rules` is a
pure function of its inputs, per `.github/instructions/pipeline-stages.instructions.md`.
"""

from dataclasses import dataclass

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import Lifecycle, SubstitutionTier
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.policy.derating_config import DEFAULT_DERATING_CONFIG, DeratingConfig
from pcbpick.policy.rules import evaluate_candidate

RequirementCandidatePair = tuple[NormalizedRequirement, PrePolicyCandidate]

_WARNING_LIFECYCLES = frozenset({Lifecycle.NRND, Lifecycle.EOL, Lifecycle.UNKNOWN})


@dataclass(frozen=True)
class PolicyStageInput:
    """One (requirement, candidate) pair per row: sourcing (M4) hasn't yet defined a
    batched candidate-assembly artifact, so this stage takes the pairing directly."""

    pairs: list[RequirementCandidatePair]


class PolicyStage:
    """Scores every candidate against its requirement and assigns a substitution tier."""

    name = "policy"

    def __init__(self, config: DeratingConfig = DEFAULT_DERATING_CONFIG) -> None:
        self._config = config

    def run(self, inp: PolicyStageInput, ctx: StageContext) -> StageResult[list[PartCandidate]]:
        del ctx  # policy scoring needs no clock or randomness

        output: list[PartCandidate] = []
        issues: list[StageIssue] = [
            StageIssue(
                severity=Severity.INFO,
                code="derating_config_version",
                message=f"policy stage used derating config version {self._config.version}",
            )
        ]

        for requirement, pre_candidate in inp.pairs:
            tier, results = evaluate_candidate(requirement, pre_candidate, self._config)
            candidate = PartCandidate(
                schema_version=pre_candidate.schema_version,
                requirement_id=pre_candidate.requirement_id,
                mpn=pre_candidate.mpn,
                manufacturer=pre_candidate.manufacturer,
                parameters=pre_candidate.parameters,
                footprint=pre_candidate.footprint,
                lifecycle=pre_candidate.lifecycle,
                compliance=pre_candidate.compliance,
                substitution_tier=tier,
                policy_results=results,
                rationale=None,
                evidence=[],
                offers=[],
            )
            output.append(candidate)

            if tier == SubstitutionTier.TIER_3:
                failed = [r.rule_name for r in results if not r.passed]
                issues.append(
                    StageIssue(
                        severity=Severity.BLOCKING,
                        code="candidate_rejected_tier3",
                        message=(
                            f"candidate {candidate.mpn} rejected for requirement "
                            f"{candidate.requirement_id}: failed {', '.join(failed)}"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )
            elif candidate.lifecycle in _WARNING_LIFECYCLES:
                issues.append(
                    StageIssue(
                        severity=Severity.WARNING,
                        code="lifecycle_review_required",
                        message=(
                            f"candidate {candidate.mpn} for requirement "
                            f"{candidate.requirement_id} has lifecycle "
                            f"'{candidate.lifecycle.value}'; requires engineer review"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )

            if pre_candidate.snapshot_id is None:
                issues.append(
                    StageIssue(
                        severity=Severity.WARNING,
                        code="candidate_missing_snapshot_provenance",
                        message=(
                            f"candidate {candidate.mpn} for requirement "
                            f"{candidate.requirement_id} has no snapshot_id recorded; its "
                            "lifecycle/compliance facts cannot be traced to a supplier snapshot"
                        ),
                        item_id=candidate.requirement_id,
                    )
                )

        output.sort(key=lambda c: (c.requirement_id, c.mpn))
        return StageResult(output=output, issues=issues)
