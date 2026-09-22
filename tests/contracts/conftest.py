"""Shared sample instances for every contract model, used by round-trip/rejection tests."""

from datetime import UTC, datetime
from decimal import Decimal

from pcbpick.contracts import (
    BomLine,
    ColumnMapping,
    ComplianceTag,
    ComponentCategory,
    Confidence,
    Criticality,
    DecisionMode,
    Evidence,
    ExportFormat,
    Footprint,
    IngestResult,
    Lifecycle,
    MappingMethod,
    MappingProposal,
    MountingType,
    MpnRef,
    Packaging,
    ParameterValue,
    PartCandidate,
    PlanLine,
    PlanTotals,
    PlanWarning,
    PlanWarningKind,
    PolicyResult,
    PriceBreak,
    PurchasePlan,
    SubstitutionTier,
    SupplierExport,
    SupplierId,
    SupplierOffer,
    UnfilledRequirement,
    ValueSource,
)
from pcbpick.contracts.requirement import NormalizedRequirement

FIXED_TIME = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)


def make_parameter_value() -> ParameterValue:
    return ParameterValue(
        value=Decimal("10000"),
        unit="ohm",
        tolerance_pct=Decimal("1"),
        min=None,
        max=None,
        raw_text="10k",
        source=ValueSource.PARSED,
    )


def make_footprint() -> Footprint:
    return Footprint(
        package_code="0402",
        mounting=MountingType.SMT,
        pin_count=2,
        pitch_mm=Decimal("0.5"),
        length_mm=Decimal("1.0"),
        width_mm=Decimal("0.5"),
        height_mm=Decimal("0.5"),
        raw_text="0402",
    )


def make_mpn_ref() -> MpnRef:
    return MpnRef(mpn="RC0402FR-0710KL", manufacturer="Yageo", source=ValueSource.PARSED)


def make_confidence() -> Confidence:
    return Confidence(score=0.95, reasons=["exact EIA notation match"])


def make_evidence() -> Evidence:
    return Evidence(
        description="Datasheet Table 3",
        url="https://example.com/datasheet.pdf",
        snapshot_id="snap-001",
        field_name="resistance",
    )


def make_price_break() -> PriceBreak:
    return PriceBreak(quantity=100, unit_price=Decimal("0.01"), currency="USD")


def make_policy_result() -> PolicyResult:
    return PolicyResult(rule_name="voltage_derating", passed=True, reason="20% margin met")


def make_bom_line() -> BomLine:
    return BomLine(
        row_index=0,
        raw={"Designator": "R1", "Value": "10k"},
        reference_designators=["R1"],
        quantity=1,
        source_file="board.csv",
        mapping_profile="altium",
        populate=True,
    )


def make_column_mapping() -> ColumnMapping:
    return ColumnMapping(
        target_field="reference_designators",
        source_column="Designator",
        method=MappingMethod.PROFILE,
        confidence=1.0,
    )


def make_mapping_proposal() -> MappingProposal:
    return MappingProposal(
        source_file="board.csv",
        eda_profile="altium",
        header_row_index=0,
        mappings=[make_column_mapping()],
        unmapped_columns=["LibRef"],
        missing_required_fields=[],
        requires_confirmation=False,
    )


def make_ingest_result() -> IngestResult:
    return IngestResult(lines=[make_bom_line()], mapping_proposal=make_mapping_proposal())


def make_normalized_requirement() -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id="req-1",
        reference_designators=["R1"],
        quantity_per_board=1,
        category=ComponentCategory.RESISTOR,
        parameters={"resistance": make_parameter_value()},
        footprint=make_footprint(),
        specified_mpn=make_mpn_ref(),
        criticality=Criticality.STANDARD,
        compliance_required=[ComplianceTag.ROHS],
        notes=None,
        confidence=make_confidence(),
        unresolved=[],
    )


def make_supplier_offer() -> SupplierOffer:
    return SupplierOffer(
        supplier=SupplierId.FIXTURE,
        sku="FIX-001",
        packaging=Packaging.CUT_TAPE,
        stock=1000,
        moq=1,
        spq=1,
        price_breaks=[make_price_break()],
        lead_time_days=None,
        snapshot_id="snap-001",
        fetched_at=FIXED_TIME,
    )


def make_part_candidate() -> PartCandidate:
    return PartCandidate(
        requirement_id="req-1",
        mpn="RC0402FR-0710KL",
        manufacturer="Yageo",
        parameters={"resistance": make_parameter_value()},
        footprint=make_footprint(),
        lifecycle=Lifecycle.ACTIVE,
        compliance=[ComplianceTag.ROHS],
        substitution_tier=SubstitutionTier.TIER_0,
        policy_results=[make_policy_result()],
        rationale="Exact match on resistance and footprint.",
        evidence=[make_evidence()],
        offers=[make_supplier_offer()],
    )


def make_plan_line() -> PlanLine:
    return PlanLine(
        requirement_id="req-1",
        mpn="RC0402FR-0710KL",
        manufacturer="Yageo",
        supplier=SupplierId.FIXTURE,
        sku="FIX-001",
        substitution_tier=SubstitutionTier.TIER_0,
        order_qty=100,
        unit_price=Decimal("0.01"),
        extended_price=Decimal("1.00"),
        currency="USD",
        snapshot_id="snap-001",
    )


def make_plan_totals() -> PlanTotals:
    return PlanTotals(
        currency="USD",
        supplier_subtotals={SupplierId.FIXTURE: Decimal("1.00")},
        shipping_total=Decimal("0.00"),
        grand_total=Decimal("1.00"),
    )


def make_unfilled_requirement() -> UnfilledRequirement:
    return UnfilledRequirement(requirement_id="req-2", reason="no candidate met voltage rating")


def make_plan_warning() -> PlanWarning:
    return PlanWarning(
        kind=PlanWarningKind.HIGH_TIER_SUBSTITUTION,
        requirement_id="req-1",
        message="Tier 2 substitution used",
    )


def make_purchase_plan() -> PurchasePlan:
    return PurchasePlan(
        mode=DecisionMode.LOWEST_COST,
        board_quantity=100,
        attrition_pct=Decimal("2"),
        lines=[make_plan_line()],
        totals=make_plan_totals(),
        longest_lead_time_days=14,
        supplier_count=1,
        unfilled=[make_unfilled_requirement()],
        warnings=[make_plan_warning()],
        snapshot_ids=["snap-001"],
    )


def make_supplier_export() -> SupplierExport:
    return SupplierExport(
        supplier=SupplierId.FIXTURE,
        format=ExportFormat.CSV,
        rows=[{"sku": "FIX-001", "qty": "100"}],
        approved_by="jane.doe",
        approved_at=FIXED_TIME,
        plan_hash="deadbeef",
    )


ALL_MODEL_FACTORIES = {
    "BomLine": make_bom_line,
    "ColumnMapping": make_column_mapping,
    "IngestResult": make_ingest_result,
    "MappingProposal": make_mapping_proposal,
    "NormalizedRequirement": make_normalized_requirement,
    "ParameterValue": make_parameter_value,
    "PartCandidate": make_part_candidate,
    "SupplierOffer": make_supplier_offer,
    "PurchasePlan": make_purchase_plan,
    "SupplierExport": make_supplier_export,
    "Footprint": make_footprint,
    "MpnRef": make_mpn_ref,
    "Confidence": make_confidence,
    "PolicyResult": make_policy_result,
    "Evidence": make_evidence,
    "PriceBreak": make_price_break,
    "PlanLine": make_plan_line,
    "PlanTotals": make_plan_totals,
    "UnfilledRequirement": make_unfilled_requirement,
    "PlanWarning": make_plan_warning,
}
