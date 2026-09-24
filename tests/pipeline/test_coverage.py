"""Unit tests for `pcbpick.pipeline.coverage`'s pure metric functions. Every
hand-computed expected value shows its arithmetic in a comment, per this
milestone's requirement not to assert a bare number.
"""

from decimal import Decimal

import pytest

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Confidence, Evidence, Footprint, ParameterValue
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    DecisionMode,
    Lifecycle,
    SubstitutionTier,
    SupplierId,
    ValueSource,
)
from pcbpick.contracts.plan import PlanTotals, PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.coverage import (
    blocking_issue_counts_by_code,
    confidence_tier,
    pct_requirements_filled_at_tier_0_or_1,
    pct_rows_normalized_without_llm_fallback,
    plan_total_delta,
)
from pcbpick.pipeline.results import Severity, StageIssue


def _requirement(requirement_id: str, *, reasons: list[str] | None = None) -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id=requirement_id,
        reference_designators=["R1"],
        quantity_per_board=1,
        category=ComponentCategory.RESISTOR,
        parameters={},
        footprint=Footprint(),
        specified_mpn=None,
        criticality=Criticality.STANDARD,
        compliance_required=[],
        notes=None,
        confidence=Confidence(score=0.5, reasons=reasons or []),
        unresolved=[],
    )


def _candidate(requirement_id: str, mpn: str, tier: SubstitutionTier) -> PartCandidate:
    return PartCandidate(
        requirement_id=requirement_id,
        mpn=mpn,
        manufacturer="Acme",
        parameters={
            "resistance": ParameterValue(
                value=Decimal("1"), unit="ohm", raw_text="1R", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(),
        lifecycle=Lifecycle.ACTIVE,
        compliance=[ComplianceTag.ROHS],
        substitution_tier=tier,
        policy_results=[],
        rationale=None,
        evidence=[Evidence(description="fixture")],
        offers=[],
    )


def _plan(grand_total: Decimal, currency: str = "USD") -> PurchasePlan:
    return PurchasePlan(
        mode=DecisionMode.LOWEST_COST,
        board_quantity=1,
        attrition_pct=Decimal("0"),
        lines=[],
        totals=PlanTotals(
            currency=currency,
            supplier_subtotals={SupplierId.MOUSER: grand_total},
            shipping_total=Decimal("0"),
            grand_total=grand_total,
        ),
        longest_lead_time_days=0,
        supplier_count=1,
        unfilled=[],
        warnings=[],
        snapshot_ids=[],
    )


def test_confidence_tier_thresholds() -> None:
    assert confidence_tier(0.95) == "high"
    assert confidence_tier(Decimal("0.9")) == "high"
    assert confidence_tier(0.6) == "medium"
    assert confidence_tier(0.5) == "medium"
    assert confidence_tier(0.3) == "low"


def test_pct_rows_normalized_without_llm_fallback() -> None:
    requirements = [
        _requirement("R1", reasons=["merged via normalize_fallback"]),
        _requirement("R2", reasons=["merged via normalize_fallback"]),
        _requirement("R3"),
        _requirement("R4"),
        _requirement("R5"),
    ]
    issues = [
        StageIssue(severity=Severity.INFO, code="llm_fallback_unavailable", message="x"),
    ]

    result = pct_rows_normalized_without_llm_fallback(requirements, issues)

    # total = 5 rows.
    # fallback_successes = 2 (R1, R2 carry the "normalize_fallback" reason marker).
    # fallback_failures = 1 (one llm_fallback_unavailable issue).
    # attempted = 2 + 1 = 3.
    # without_fallback = 5 - 3 = 2.
    # percentage = 2 / 5 * 100 = 40.00
    assert result == Decimal("40.00")


def test_pct_rows_normalized_without_llm_fallback_is_none_for_no_rows() -> None:
    assert pct_rows_normalized_without_llm_fallback([], []) is None


def test_pct_requirements_filled_at_tier_0_or_1() -> None:
    requirement_ids = ["R1", "R2", "R3", "R4"]
    candidates = [
        _candidate("R1", "MPN-1", SubstitutionTier.TIER_0),
        _candidate("R2", "MPN-2", SubstitutionTier.TIER_2),
        _candidate("R3", "MPN-3", SubstitutionTier.TIER_1),
        # R4 has no candidates at all.
    ]

    result = pct_requirements_filled_at_tier_0_or_1(requirement_ids, candidates)

    # total = 4 requirements.
    # filled = R1 (tier 0) and R3 (tier 1) = 2. R2 is tier 2 only, R4 has none.
    # percentage = 2 / 4 * 100 = 50.00
    assert result == Decimal("50.00")


def test_pct_requirements_filled_at_tier_0_or_1_is_none_for_no_requirements() -> None:
    assert pct_requirements_filled_at_tier_0_or_1([], []) is None


def test_blocking_issue_counts_by_code() -> None:
    issues_a = [
        StageIssue(severity=Severity.BLOCKING, code="a", message="1"),
        StageIssue(severity=Severity.WARNING, code="a", message="2"),
        StageIssue(severity=Severity.BLOCKING, code="b", message="3"),
    ]
    issues_b = [
        StageIssue(severity=Severity.BLOCKING, code="a", message="4"),
        StageIssue(severity=Severity.INFO, code="c", message="5"),
    ]

    result = blocking_issue_counts_by_code(issues_a, issues_b)

    # "a": one BLOCKING in issues_a + one BLOCKING in issues_b = 2 (the WARNING "a" doesn't count).
    # "b": one BLOCKING in issues_a = 1.
    # "c": zero BLOCKING (only INFO) -- absent from the result entirely.
    assert result == {"a": 2, "b": 1}


def test_plan_total_delta_computes_difference() -> None:
    previous = _plan(Decimal("100.00"))
    current = _plan(Decimal("150.00"))

    # 150.00 - 100.00 = 50.00
    assert plan_total_delta(previous, current) == Decimal("50.00")


def test_plan_total_delta_is_none_with_no_previous_plan() -> None:
    assert plan_total_delta(None, _plan(Decimal("100.00"))) is None


def test_plan_total_delta_raises_on_currency_mismatch() -> None:
    previous = _plan(Decimal("100.00"), currency="USD")
    current = _plan(Decimal("100.00"), currency="EUR")

    with pytest.raises(ValueError, match="currenc"):
        plan_total_delta(previous, current)
