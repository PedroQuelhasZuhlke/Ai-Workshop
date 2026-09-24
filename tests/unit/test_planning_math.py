"""Unit tests for `pcbpick.planning`'s pure math: order-quantity/MOQ/SPQ rounding,
price-break selection, buy-up detection, attrition classification, shipping cost,
and plan hashing. See `.github/skills/procurement-math/SKILL.md` for the formulas
under test.
"""

from decimal import Decimal

import pytest

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Confidence, Footprint, PriceBreak
from pcbpick.contracts.enums import (
    ComponentCategory,
    Criticality,
    DecisionMode,
    Lifecycle,
    SubstitutionTier,
    SupplierId,
)
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.plan import PlanLine, PlanTotals, PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.errors import ContractViolationError
from pcbpick.planning.attrition import AttritionPartClass, classify_part_class, compute_required_qty
from pcbpick.planning.config import DEFAULT_ATTRITION_CONFIG, DEFAULT_SHIPPING_CONFIG, ShippingTerm
from pcbpick.planning.order_quantity import (
    find_buy_up_opportunity,
    resolve_order_qty,
    round_up_to_multiple,
    select_price_break,
)
from pcbpick.planning.plan_hash import compute_plan_hash
from pcbpick.planning.shipping import compute_shipping_cost

# --- round_up_to_multiple -----------------------------------------------------------


def test_round_up_to_multiple_exact_multiple_is_unchanged() -> None:
    assert round_up_to_multiple(100, 10) == 100


def test_round_up_to_multiple_rounds_up() -> None:
    assert round_up_to_multiple(101, 10) == 110


def test_round_up_to_multiple_rejects_non_positive_multiple() -> None:
    with pytest.raises(ContractViolationError):
        round_up_to_multiple(10, 0)


# --- resolve_order_qty (MOQ/SPQ interplay) -------------------------------------------


def _offer(
    moq: int = 1,
    spq: int = 1,
    price_breaks: list[PriceBreak] | None = None,
    stock: int | None = 1000,
) -> SupplierOffer:
    from datetime import UTC, datetime

    from pcbpick.contracts.enums import Packaging

    return SupplierOffer(
        supplier=SupplierId.FIXTURE,
        sku="SKU-1",
        packaging=Packaging.CUT_TAPE,
        stock=stock,
        moq=moq,
        spq=spq,
        price_breaks=price_breaks
        or [PriceBreak(quantity=1, unit_price=Decimal("0.10"), currency="USD")],
        lead_time_days=None,
        snapshot_id="SNAP-1",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_resolve_order_qty_spq_rounds_up_above_moq() -> None:
    # need 44, spq=25 rounds up to 50, which already clears moq=10.
    offer = _offer(moq=10, spq=25)
    assert resolve_order_qty(44, offer) == 50


def test_resolve_order_qty_moq_wins_when_higher_than_rounded_spq() -> None:
    # need 4, spq=1 rounds to 4, but moq=100 dominates.
    offer = _offer(moq=100, spq=1)
    assert resolve_order_qty(4, offer) == 100


def test_resolve_order_qty_moq_itself_not_forced_to_be_an_spq_multiple() -> None:
    # need 1, spq=25 rounds to 25, moq=10 is lower -- spq rounding wins.
    offer = _offer(moq=10, spq=25)
    assert resolve_order_qty(1, offer) == 25


# --- select_price_break ---------------------------------------------------------------


def test_select_price_break_picks_highest_applicable_rung() -> None:
    breaks = [
        PriceBreak(quantity=1, unit_price=Decimal("0.10"), currency="USD"),
        PriceBreak(quantity=100, unit_price=Decimal("0.07"), currency="USD"),
        PriceBreak(quantity=1000, unit_price=Decimal("0.04"), currency="USD"),
    ]
    assert select_price_break(500, breaks).quantity == 100  # type: ignore[union-attr]
    assert select_price_break(1000, breaks).quantity == 1000  # type: ignore[union-attr]


def test_select_price_break_returns_none_when_order_qty_below_every_rung() -> None:
    breaks = [PriceBreak(quantity=100, unit_price=Decimal("0.07"), currency="USD")]
    assert select_price_break(10, breaks) is None


# --- find_buy_up_opportunity ----------------------------------------------------------


def test_find_buy_up_opportunity_finds_a_cheaper_larger_order() -> None:
    breaks = [
        PriceBreak(quantity=1, unit_price=Decimal("0.10"), currency="USD"),
        PriceBreak(quantity=1000, unit_price=Decimal("0.02"), currency="USD"),
    ]
    # 900 units @ 0.10 = 90.00; buying up to 1000 @ 0.02 = 20.00 -- a clear saving.
    opportunity = find_buy_up_opportunity(900, Decimal("90.00"), 1, breaks)
    assert opportunity is not None
    assert opportunity.new_order_qty == 1000
    assert opportunity.extra_qty == 100
    assert opportunity.saving == Decimal("70.00")


def test_find_buy_up_opportunity_returns_none_when_no_break_saves_money() -> None:
    breaks = [
        PriceBreak(quantity=1, unit_price=Decimal("0.10"), currency="USD"),
        PriceBreak(quantity=1000, unit_price=Decimal("0.099"), currency="USD"),
    ]
    # 900 @ 0.10 = 90.00; buying up to 1000 @ 0.099 = 99.00 -- more expensive, no saving.
    opportunity = find_buy_up_opportunity(900, Decimal("90.00"), 1, breaks)
    assert opportunity is None


# --- classify_part_class / compute_required_qty ---------------------------------------


def _requirement(
    category: ComponentCategory, footprint: Footprint | None = None
) -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id="REQ-TEST",
        reference_designators=["Z1"],
        quantity_per_board=4,
        category=category,
        parameters={},
        footprint=footprint or Footprint(),
        specified_mpn=None,
        criticality=Criticality.STANDARD,
        compliance_required=[],
        notes=None,
        confidence=Confidence(score=1.0),
        unresolved=[],
    )


def _candidate(footprint: Footprint | None = None) -> PartCandidate:
    return PartCandidate(
        requirement_id="REQ-TEST",
        mpn="CAND-1",
        manufacturer="TestCo",
        parameters={},
        footprint=footprint or Footprint(),
        lifecycle=Lifecycle.ACTIVE,
        compliance=[],
        substitution_tier=SubstitutionTier.TIER_0,
        policy_results=[],
        rationale=None,
        evidence=[],
        offers=[],
    )


def test_classify_passive_small_by_footprint_dimension() -> None:
    requirement = _requirement(ComponentCategory.RESISTOR)
    candidate = _candidate(Footprint(length_mm=Decimal("1.6"), width_mm=Decimal("0.8")))
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.PASSIVE_SMALL
    assert result.used_dimension_fallback is False


def test_classify_passive_large_by_footprint_dimension() -> None:
    requirement = _requirement(ComponentCategory.CAPACITOR)
    candidate = _candidate(Footprint(length_mm=Decimal("3.2"), width_mm=Decimal("1.6")))
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.PASSIVE_LARGE
    assert result.used_dimension_fallback is False


def test_classify_small_smd_semiconductor_by_category() -> None:
    requirement = _requirement(ComponentCategory.DIODE)
    candidate = _candidate()
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.SMALL_SMD_SEMICONDUCTOR


def test_classify_no_attrition_for_ic_category() -> None:
    requirement = _requirement(ComponentCategory.IC_ANALOG)
    candidate = _candidate()
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.NO_ATTRITION


def test_classify_passive_falls_back_to_large_bucket_when_no_dimension_stated() -> None:
    requirement = _requirement(ComponentCategory.RESISTOR, Footprint())
    candidate = _candidate(Footprint())
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.PASSIVE_LARGE
    assert result.used_dimension_fallback is True


def test_classify_passive_falls_back_to_requirement_footprint_when_candidate_lacks_dimensions() -> (
    None
):
    requirement = _requirement(
        ComponentCategory.RESISTOR, Footprint(length_mm=Decimal("1.6"), width_mm=Decimal("0.8"))
    )
    candidate = _candidate(Footprint())
    result = classify_part_class(requirement, candidate)
    assert result.part_class == AttritionPartClass.PASSIVE_SMALL
    assert result.used_dimension_fallback is False


def test_compute_required_qty_applies_percentage_and_minimum_extra_floor() -> None:
    # board_qty=1, qty_per_board=4 -> base 4; 10% of 4 rounds up to 1, but min_extra=10 wins.
    required = compute_required_qty(
        1, 4, AttritionPartClass.PASSIVE_SMALL, DEFAULT_ATTRITION_CONFIG
    )
    assert required == 4 + 10


def test_compute_required_qty_percentage_dominates_at_higher_volume() -> None:
    # board_qty=100, qty_per_board=4 -> base 400; 10% = 40, which beats the 10-piece floor.
    required = compute_required_qty(
        100, 4, AttritionPartClass.PASSIVE_SMALL, DEFAULT_ATTRITION_CONFIG
    )
    assert required == 440


def test_compute_required_qty_no_attrition_bucket_adds_nothing() -> None:
    required = compute_required_qty(
        10, 1, AttritionPartClass.NO_ATTRITION, DEFAULT_ATTRITION_CONFIG
    )
    assert required == 10


# --- compute_shipping_cost -------------------------------------------------------------


def test_shipping_cost_below_threshold_charges_flat_fee() -> None:
    term = ShippingTerm(Decimal("8.00"), Decimal("65.00"), "USD")
    assert compute_shipping_cost(term, Decimal("10.00")) == Decimal("8.00")


def test_shipping_cost_above_threshold_is_free() -> None:
    term = ShippingTerm(Decimal("8.00"), Decimal("65.00"), "USD")
    assert compute_shipping_cost(term, Decimal("70.00")) == Decimal("0")


def test_shipping_cost_exactly_at_threshold_is_free() -> None:
    term = ShippingTerm(Decimal("8.00"), Decimal("65.00"), "USD")
    assert compute_shipping_cost(term, Decimal("65.00")) == Decimal("0")


def test_shipping_cost_with_no_threshold_always_charges() -> None:
    term = ShippingTerm(Decimal("5.00"), None, "USD")
    assert compute_shipping_cost(term, Decimal("999999")) == Decimal("5.00")


def test_default_shipping_config_has_terms_for_every_supplier() -> None:
    for supplier in SupplierId:
        assert supplier in DEFAULT_SHIPPING_CONFIG.terms_by_supplier


# --- compute_plan_hash -----------------------------------------------------------------


def _plan_line(order_qty: int = 10) -> PlanLine:
    return PlanLine(
        requirement_id="REQ-R1",
        mpn="RC0603FR-0710KL",
        manufacturer="Yageo",
        supplier=SupplierId.MOUSER,
        sku="MOUSER-SKU-1",
        substitution_tier=SubstitutionTier.TIER_0,
        order_qty=order_qty,
        unit_price=Decimal("0.05"),
        extended_price=Decimal("0.05") * order_qty,
        currency="USD",
        snapshot_id="SNAP-1",
    )


def _plan(order_qty: int = 10) -> PurchasePlan:
    line = _plan_line(order_qty)
    return PurchasePlan(
        mode=DecisionMode.LOWEST_COST,
        board_quantity=1,
        attrition_pct=Decimal("0"),
        lines=[line],
        totals=PlanTotals(
            currency="USD",
            supplier_subtotals={SupplierId.MOUSER: line.extended_price},
            shipping_total=Decimal("0"),
            grand_total=line.extended_price,
        ),
        longest_lead_time_days=0,
        supplier_count=1,
        unfilled=[],
        warnings=[],
        snapshot_ids=["SNAP-1"],
    )


def test_compute_plan_hash_is_stable_for_the_same_plan() -> None:
    plan = _plan()
    assert compute_plan_hash(plan) == compute_plan_hash(plan)
    assert compute_plan_hash(_plan()) == compute_plan_hash(_plan())


def test_compute_plan_hash_differs_for_a_different_plan() -> None:
    assert compute_plan_hash(_plan(order_qty=10)) != compute_plan_hash(_plan(order_qty=20))
