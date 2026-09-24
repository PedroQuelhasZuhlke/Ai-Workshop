"""Prompt regression tests for the two sanctioned LLM call sites (per
`.github/instructions/llm-calls.instructions.md`), driven verbatim by the committed
fixtures under `fixtures/llm/**`. See `fixtures/llm/README.md` for the fixture
schema and the severity-divergence note between the two call sites.

Fixture data is read-only here -- nothing under `fixtures/llm/**` is created or
edited by this file.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random
from typing import Any

import pytest

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
from pcbpick.llm.client import call_structured
from pcbpick.llm.fakes import FakeLLMClient
from pcbpick.normalize.llm_fallback import run_normalize_fallback
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity
from pcbpick.sourcing.evaluate import (
    TEMPLATE_NAME,
    CandidateRationale,
    EvaluateStage,
    EvaluateStageInput,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NORMALIZE_FALLBACK_DIR = _REPO_ROOT / "fixtures" / "llm" / "normalize_fallback"
_CANDIDATE_RATIONALE_DIR = _REPO_ROOT / "fixtures" / "llm" / "candidate_rationale"
_MAX_RETRIES = 2


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_attempts(expected_outcome: dict[str, Any], max_retries: int) -> int:
    attempts = expected_outcome["attempts"]
    if isinstance(attempts, int):
        return attempts
    # `call_structured` (src/pcbpick/llm/client.py) spends exactly `max_retries + 1`
    # total attempts before degrading to `failed=True` -- one initial attempt plus
    # `max_retries` retries, hardcoded in its final `return` rather than derived
    # from the loop's `attempt` variable, but the two agree (`range(1, max_retries
    # + 2)` yields `max_retries + 1` values). The fixture doc's "max_retries + 2"
    # wording is therefore off by one from the real implementation -- computed
    # correctly here rather than propagated, and reported as a documentation
    # defect rather than silently "fixed" in fixtures/llm/** (which is final).
    assert attempts == "max_retries + 2", f"unexpected attempts formula: {attempts!r}"
    return max_retries + 1


def _severity(name: str) -> Severity:
    return Severity(name.lower())


# Confirmed by directly running `run_normalize_fallback` against this fixture's own
# `response_text`, not by editing the fixture: a genuine defect in the fixture data,
# not a call-site/runner bug. `valid_ic_widget_row.json` is marked
# `validates_against_response_model: true` and `expected_call_structured_outcome`
# `{"failed": false, "attempts": 1}`, but its `response_text`'s
# `footprint.mounting` field is `"smd"`, which is not a valid `MountingType` member
# (only `"smt"`/`"tht"` are -- see `src/pcbpick/contracts/enums.py`). So
# `NormalizedRequirementFragment.model_validate_json` actually raises a
# `ValidationError` on every attempt and the call degrades to `failed=True`,
# `attempts=3` (with `max_retries=2`), exactly like this directory's two malformed
# fixtures -- not the accept path the fixture's own metadata claims. Per this
# milestone's instruction not to edit `fixtures/llm/**`, this is reported here (and
# in the stage-builder's final summary) instead of silently "fixed" by editing the
# fixture's `response_text`, `validates_against_response_model`, or
# `expected_call_structured_outcome`/`expected_stage_issue` fields.
_KNOWN_FIXTURE_DEFECTS = frozenset({"valid_ic_widget_row"})


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="prompt-regression",
        now=datetime(2026, 9, 24, tzinfo=UTC),
        rng=Random("prompt-regression"),
        config=PipelineConfig(),
    )


# --------------------------------------------------------------- normalize_fallback


@pytest.mark.parametrize(
    "fixture_path", sorted(_NORMALIZE_FALLBACK_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_normalize_fallback_prompt_regression(fixture_path: Path) -> None:
    fixture = _load_fixture(fixture_path)
    client = FakeLLMClient(model_id="fixture-client", default_response=fixture["response_text"])
    request_variables = fixture["request_variables"]

    result = run_normalize_fallback(
        client=client,
        raw_cells=request_variables["row"],
        category_hint=request_variables["category_hint"] or None,
        max_retries=_MAX_RETRIES,
    )

    expected_outcome = fixture["expected_call_structured_outcome"]
    assert result.failed == expected_outcome["failed"]
    assert result.attempts == _expected_attempts(expected_outcome, _MAX_RETRIES)

    expected_issue = fixture["expected_stage_issue"]
    if expected_issue["code"] is None:
        # No issue is recorded for a successful fallback (see
        # src/pcbpick/normalize/requirement_builder.py) -- the call must not have
        # failed for that to hold.
        assert not result.failed
    else:
        # normalize_fallback failure is always recorded as this exact INFO issue
        # by requirement_builder.py -- never BLOCKING (see fixtures/llm/README.md's
        # severity-divergence note).
        assert result.failed
        assert expected_issue["code"] == "llm_fallback_unavailable"
        assert _severity(expected_issue["severity"]) == Severity.INFO


# -------------------------------------------------------------- candidate_rationale


def _requirement_from_fixture(data: dict[str, Any]) -> NormalizedRequirement:
    """Builds a minimal, valid `NormalizedRequirement` carrying this fixture's
    `category`/`criticality` -- the only two fields of `request_variables.requirement`
    that are themselves real enum values (e.g. `mounting: "smd"` in the fixture's
    footprint dict is illustrative prompt JSON, not a valid `MountingType` member, so
    it is not round-tripped verbatim; see `tests/stages/test_evaluate.py`'s own
    `_requirement` helper for the same minimal-fixture-object pattern reused here).
    """
    return NormalizedRequirement(
        requirement_id="REQ-FIXTURE",
        reference_designators=["R1"],
        quantity_per_board=1,
        category=ComponentCategory(data["category"]),
        parameters={
            "value": ParameterValue(
                value=Decimal("1"), unit="ohm", raw_text="1R", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code=data["footprint"].get("package_code")),
        specified_mpn=None,
        criticality=Criticality(data["criticality"]),
        compliance_required=[],
        notes=None,
        confidence=Confidence(score=0.95),
        unresolved=[],
    )


def _candidate_from_fixture(data: dict[str, Any]) -> PartCandidate:
    """Builds a minimal, valid `PartCandidate` carrying this fixture's `mpn`,
    `manufacturer`, `lifecycle`, `compliance`, and `substitution_tier` -- the fields
    of `request_variables.candidate` that are real enum/scalar values (see the
    docstring on `_requirement_from_fixture` for why the rest are not round-tripped).
    """
    return PartCandidate(
        requirement_id="REQ-FIXTURE",
        mpn=data["mpn"],
        manufacturer=data["manufacturer"],
        parameters={
            "value": ParameterValue(
                value=Decimal("1"), unit="ohm", raw_text="1R", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code=data["footprint"].get("package_code")),
        lifecycle=Lifecycle(data["lifecycle"]),
        compliance=[ComplianceTag(tag) for tag in data["compliance"]],
        substitution_tier=SubstitutionTier(data["substitution_tier"]),
        policy_results=[
            PolicyResult(rule_name=r["rule"], passed=r["passed"], reason="fixture-derived")
            for r in data["policy_results"]
        ],
        rationale=None,
        evidence=[],
        offers=[],
    )


@dataclass
class _CountingLLMClient:
    """Tracks call count without changing `FakeLLMClient`'s own behavior."""

    inner: FakeLLMClient
    model_id: str = ""
    call_count: int = 0

    def __post_init__(self) -> None:
        self.model_id = self.inner.model_id

    def generate(self, *, template: str, variables: dict[str, str], response_model: Any) -> str:
        self.call_count += 1
        return self.inner.generate(
            template=template, variables=variables, response_model=response_model
        )


@pytest.mark.parametrize(
    "fixture_path", sorted(_CANDIDATE_RATIONALE_DIR.glob("*.json")), ids=lambda p: p.stem
)
def test_candidate_rationale_prompt_regression(fixture_path: Path) -> None:
    fixture = _load_fixture(fixture_path)
    client = _CountingLLMClient(
        FakeLLMClient(model_id="fixture-client", default_response=fixture["response_text"])
    )
    request_variables = fixture["request_variables"]

    # `call_structured` directly, exactly as `EvaluateStage.run` invokes it
    # internally, to check `expected_call_structured_outcome` (attempts is not
    # otherwise observable from `EvaluateStage`'s own return value).
    direct_result = call_structured(
        client=client,
        template=TEMPLATE_NAME,
        response_model=CandidateRationale,
        variables={"requirement": "{}", "candidate": "{}"},
        max_retries=_MAX_RETRIES,
    )
    expected_outcome = fixture["expected_call_structured_outcome"]
    assert direct_result.failed == expected_outcome["failed"]
    assert direct_result.attempts == _expected_attempts(expected_outcome, _MAX_RETRIES)

    # The real `EvaluateStage.run` path, to check `expected_stage_issue`.
    requirement = _requirement_from_fixture(request_variables["requirement"])
    candidate = _candidate_from_fixture(request_variables["candidate"])
    stage_result = EvaluateStage(llm_client=client, max_llm_retries=_MAX_RETRIES).run(
        EvaluateStageInput(pairs=[(requirement, candidate)]), _make_ctx()
    )

    expected_issue = fixture["expected_stage_issue"]
    matching_issues = [i for i in stage_result.issues if i.code == expected_issue["code"]]
    assert matching_issues, (
        f"expected an issue with code {expected_issue['code']!r}, got "
        f"{[(i.code, i.severity) for i in stage_result.issues]!r}"
    )
    assert all(i.severity == _severity(expected_issue["severity"]) for i in matching_issues)

    if expected_issue["code"] == "candidate_rationale_llm_failed":
        assert stage_result.output[0].rationale is None
    elif expected_issue["code"] == "candidate_rationale_concern":
        assert stage_result.output[0].rationale is not None
        # `substitution_tier` and `policy_results` must be unaffected by concerns.
        assert stage_result.output[0].substitution_tier == candidate.substitution_tier
        assert stage_result.output[0].policy_results == candidate.policy_results
