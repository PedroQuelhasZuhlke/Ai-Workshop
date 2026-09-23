"""Stage tests for `evaluate` (`EvaluateStage`): rationale attachment, malformed-
response degradation, tier-3 exclusion from the LLM entirely, concern surfacing,
and determinism, per `.github/instructions/pipeline-stages.instructions.md` and
`.github/instructions/llm-calls.instructions.md`.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from random import Random

from pydantic import BaseModel

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Confidence, Footprint, ParameterValue
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    Lifecycle,
    SubstitutionTier,
    ValueSource,
)
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.llm.fakes import FakeLLMClient
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity
from pcbpick.sourcing.evaluate import TEMPLATE_NAME, EvaluateStage, EvaluateStageInput


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _requirement(requirement_id: str = "REQ-1") -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id=requirement_id,
        reference_designators=["R1"],
        quantity_per_board=1,
        category=ComponentCategory.RESISTOR,
        parameters={
            "resistance": ParameterValue(
                value=Decimal("10000"), unit="ohm", raw_text="10k", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="RESC1608X55N"),
        specified_mpn=None,
        criticality=Criticality.STANDARD,
        compliance_required=[ComplianceTag.ROHS],
        notes=None,
        confidence=Confidence(score=0.95),
        unresolved=[],
    )


def _candidate(
    *,
    requirement_id: str = "REQ-1",
    mpn: str = "RC0603FR-0710KL",
    tier: SubstitutionTier = SubstitutionTier.TIER_0,
    rationale: str | None = None,
) -> PartCandidate:
    return PartCandidate(
        requirement_id=requirement_id,
        mpn=mpn,
        manufacturer="Yageo",
        parameters={
            "resistance": ParameterValue(
                value=Decimal("10000"), unit="ohm", raw_text="10k", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="RESC1608X55N"),
        lifecycle=Lifecycle.ACTIVE,
        compliance=[ComplianceTag.ROHS],
        substitution_tier=tier,
        policy_results=[PolicyResult(rule_name="exact_mpn", passed=True, reason="matched")],
        rationale=rationale,
        evidence=[],
        offers=[],
    )


@dataclass
class _CountingLLMClient:
    """Wraps `FakeLLMClient` to track how many times `generate` was actually called.

    Not a `FakeLLMClient` change — a local test double per this stage's test needs,
    per the task's guidance not to widen the shared fake for one test file.
    """

    inner: FakeLLMClient
    model_id: str = field(init=False)
    call_count: int = 0

    def __post_init__(self) -> None:
        self.model_id = self.inner.model_id

    def generate(
        self, *, template: str, variables: dict[str, str], response_model: type[BaseModel]
    ) -> str:
        self.call_count += 1
        return self.inner.generate(
            template=template, variables=variables, response_model=response_model
        )


def _client(response: str) -> _CountingLLMClient:
    return _CountingLLMClient(FakeLLMClient(model_id="fake-1", default_response=response))


def test_rationale_attached_on_success() -> None:
    response = json.dumps({"rationale": "Exact MPN match, tier 0.", "concerns": []})
    client = _client(response)

    result = EvaluateStage(llm_client=client).run(
        EvaluateStageInput(pairs=[(_requirement(), _candidate())]), _make_ctx()
    )

    assert len(result.output) == 1
    assert result.output[0].rationale == "Exact MPN match, tier 0."
    assert client.call_count == 1
    assert not any(issue.severity == Severity.BLOCKING for issue in result.issues)


def test_malformed_response_records_blocking_issue_and_leaves_rationale_none() -> None:
    client = _client("not valid json")

    result = EvaluateStage(llm_client=client, max_llm_retries=0).run(
        EvaluateStageInput(pairs=[(_requirement(), _candidate())]), _make_ctx()
    )

    assert len(result.output) == 1
    assert result.output[0].rationale is None
    blocking = [i for i in result.issues if i.severity == Severity.BLOCKING]
    assert len(blocking) == 1
    assert blocking[0].code == "candidate_rationale_llm_failed"


def test_tier3_candidate_is_skipped_and_never_sent_to_the_llm() -> None:
    client = _client(json.dumps({"rationale": "should never be used", "concerns": []}))
    rejected = _candidate(tier=SubstitutionTier.TIER_3)

    result = EvaluateStage(llm_client=client).run(
        EvaluateStageInput(pairs=[(_requirement(), rejected)]), _make_ctx()
    )

    assert result.output == []
    assert client.call_count == 0
    assert any(
        issue.code == "rationale_skipped_rejected_candidate" and issue.severity == Severity.INFO
        for issue in result.issues
    )


def test_concerns_are_surfaced_as_warning_issues() -> None:
    response = json.dumps(
        {"rationale": "Fits, but flagged.", "concerns": ["NRND lifecycle", "tier-2 substitution"]}
    )
    client = _client(response)

    result = EvaluateStage(llm_client=client).run(
        EvaluateStageInput(pairs=[(_requirement(), _candidate())]), _make_ctx()
    )

    concern_issues = [i for i in result.issues if i.code == "candidate_rationale_concern"]
    assert len(concern_issues) == 2
    assert all(i.severity == Severity.WARNING for i in concern_issues)
    assert any("NRND lifecycle" in i.message for i in concern_issues)
    assert any("tier-2 substitution" in i.message for i in concern_issues)
    # concerns never change the tier
    assert result.output[0].substitution_tier == SubstitutionTier.TIER_0


def test_no_llm_client_configured_degrades_to_blocking_not_a_crash() -> None:
    result = EvaluateStage(llm_client=None).run(
        EvaluateStageInput(pairs=[(_requirement(), _candidate())]), _make_ctx()
    )

    assert len(result.output) == 1
    assert result.output[0].rationale is None
    assert any(i.code == "candidate_rationale_llm_failed" for i in result.issues)


def test_output_sorted_by_requirement_id_then_mpn() -> None:
    response = json.dumps({"rationale": "ok", "concerns": []})
    client = _client(response)
    pairs = [
        (_requirement("REQ-B"), _candidate(requirement_id="REQ-B", mpn="MPN-B")),
        (_requirement("REQ-A"), _candidate(requirement_id="REQ-A", mpn="MPN-A")),
    ]

    result = EvaluateStage(llm_client=client).run(EvaluateStageInput(pairs=pairs), _make_ctx())

    keys = [(c.requirement_id, c.mpn) for c in result.output]
    assert keys == sorted(keys)


def test_evaluate_is_deterministic_across_runs() -> None:
    response = json.dumps({"rationale": "ok", "concerns": ["one"]})
    rejected = _candidate(requirement_id="REQ-B", mpn="MPN-B", tier=SubstitutionTier.TIER_3)
    pairs = [
        (_requirement("REQ-A"), _candidate(requirement_id="REQ-A", mpn="MPN-A")),
        (_requirement("REQ-B"), rejected),
    ]
    ctx = _make_ctx()

    first = EvaluateStage(llm_client=_client(response)).run(EvaluateStageInput(pairs=pairs), ctx)
    second = EvaluateStage(llm_client=_client(response)).run(EvaluateStageInput(pairs=pairs), ctx)

    assert [c.model_dump_json() for c in first.output] == [
        c.model_dump_json() for c in second.output
    ]
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]


def test_template_name_constant_matches_prompt_template_file() -> None:
    assert TEMPLATE_NAME == "candidate_rationale"
