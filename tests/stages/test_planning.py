"""`PlanningStage` tests: golden-path decision-mode divergence, `lowest_risk`'s hard
filter, unfilled requirements, `PlanWarning` generation, and determinism.

Scenario (all hand-built -- no fixture adapter involved, mirroring
`tests/pipeline/test_sourcing_pipeline.py`'s precedent of hand-built
`NormalizedRequirement`/`PartCandidate` pairs):

- `req-r1` (resistor, small passive): two suppliers offer the same tier-0 candidate --
  `fixture` cheap/slow (30 day lead), `mouser` pricier/fast (1 day lead). This is the
  line that must make `lowest_cost` and `fastest_delivery` diverge: a supplier
  subset that drops `fixture` is strictly more expensive but strictly faster.
- `req-c1` (capacitor, large passive): a single tier-2, NRND candidate from
  `digikey`. Only `lowest_risk` should be unable to fill it (tier > 1 and non-active
  lifecycle both fail its hard filter).
- `req-y1` (crystal, no attrition): a single tier-0, active candidate from `digikey`
  whose only offer is stale (fetched 200 days ago against a 90-day freshness
  window). Every mode should include it with a `STALE_OFFER` warning except
  `lowest_risk`, which excludes staleness too.
- `req-u1` (IC): a policy-clean candidate with zero supplier offers at all -- every
  mode must report it as an `UnfilledRequirement`, never silently drop it.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Confidence, Footprint, ParameterValue, PriceBreak
from pcbpick.contracts.enums import (
    ComponentCategory,
    Criticality,
    DecisionMode,
    Lifecycle,
    MountingType,
    Packaging,
    PlanWarningKind,
    SubstitutionTier,
    SupplierId,
    ValueSource,
)
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.planning.stage import PlanningStage, PlanningStageInput

BOARD_QUANTITY = 10


def _ctx() -> StageContext:
    return StageContext(
        run_id="planning-test",
        now=datetime(2026, 9, 23, tzinfo=UTC),
        rng=Random("planning-test"),
        config=PipelineConfig(),
    )


def _requirement(
    requirement_id: str,
    category: ComponentCategory,
    quantity_per_board: int,
    footprint: Footprint,
) -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id=requirement_id,
        reference_designators=[requirement_id.upper()],
        quantity_per_board=quantity_per_board,
        category=category,
        parameters={},
        footprint=footprint,
        specified_mpn=None,
        criticality=Criticality.STANDARD,
        compliance_required=[],
        notes=None,
        confidence=Confidence(score=0.95),
        unresolved=[],
    )


def _offer(
    supplier: SupplierId,
    sku: str,
    *,
    unit_price: str,
    moq: int,
    spq: int,
    lead_time_days: int,
    stock: int,
    fetched_at: datetime,
    snapshot_id: str,
) -> SupplierOffer:
    return SupplierOffer(
        supplier=supplier,
        sku=sku,
        packaging=Packaging.CUT_TAPE,
        stock=stock,
        moq=moq,
        spq=spq,
        price_breaks=[PriceBreak(quantity=1, unit_price=Decimal(unit_price), currency="USD")],
        lead_time_days=lead_time_days,
        snapshot_id=snapshot_id,
        fetched_at=fetched_at,
    )


def _candidate(
    requirement_id: str,
    mpn: str,
    *,
    tier: SubstitutionTier,
    lifecycle: Lifecycle,
    offers: list[SupplierOffer],
) -> PartCandidate:
    return PartCandidate(
        requirement_id=requirement_id,
        mpn=mpn,
        manufacturer="Acme",
        parameters={
            "value": ParameterValue(
                value=Decimal("1"), unit="ohm", raw_text="1", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="0603", mounting=MountingType.SMT, raw_text="0603"),
        lifecycle=lifecycle,
        compliance=[],
        substitution_tier=tier,
        policy_results=[],
        rationale=None,
        evidence=[],
        offers=offers,
    )


def _build_pairs(now: datetime) -> list[tuple[NormalizedRequirement, PartCandidate]]:
    small_passive_fp = Footprint(
        package_code="RESC1608X55N",
        mounting=MountingType.SMT,
        length_mm=Decimal("1.6"),
        width_mm=Decimal("0.8"),
        raw_text="0603",
    )
    large_passive_fp = Footprint(
        package_code="CAPC3225X135N",
        mounting=MountingType.SMT,
        length_mm=Decimal("3.2"),
        width_mm=Decimal("2.5"),
        raw_text="1210",
    )
    ic_fp = Footprint(
        package_code="SOIC127P600X175-8N", mounting=MountingType.SMT, raw_text="SOIC-8"
    )

    req_r1 = _requirement("req-r1", ComponentCategory.RESISTOR, 2, small_passive_fp)
    req_c1 = _requirement("req-c1", ComponentCategory.CAPACITOR, 1, large_passive_fp)
    req_y1 = _requirement("req-y1", ComponentCategory.CRYSTAL, 1, ic_fp)
    req_u1 = _requirement("req-u1", ComponentCategory.IC_ANALOG, 1, ic_fp)

    candidate_r1 = _candidate(
        "req-r1",
        "R-A",
        tier=SubstitutionTier.TIER_0,
        lifecycle=Lifecycle.ACTIVE,
        offers=[
            _offer(
                SupplierId.FIXTURE,
                "R-A-FIX",
                unit_price="0.05",
                moq=1,
                spq=10,
                lead_time_days=30,
                stock=1000,
                fetched_at=now,
                snapshot_id="snap-fixture-1",
            ),
            _offer(
                SupplierId.MOUSER,
                "R-A-MOU",
                unit_price="0.20",
                moq=1,
                spq=10,
                lead_time_days=1,
                stock=1000,
                fetched_at=now,
                snapshot_id="snap-mouser-1",
            ),
        ],
    )
    candidate_c1 = _candidate(
        "req-c1",
        "C-B",
        tier=SubstitutionTier.TIER_2,
        lifecycle=Lifecycle.NRND,
        offers=[
            _offer(
                SupplierId.DIGIKEY,
                "C-B-DK",
                unit_price="0.10",
                moq=1,
                spq=1,
                lead_time_days=5,
                stock=500,
                fetched_at=now,
                snapshot_id="snap-digikey-1",
            )
        ],
    )
    candidate_y1 = _candidate(
        "req-y1",
        "Y-C",
        tier=SubstitutionTier.TIER_0,
        lifecycle=Lifecycle.ACTIVE,
        offers=[
            _offer(
                SupplierId.DIGIKEY,
                "Y-C-DK",
                unit_price="1.00",
                moq=1,
                spq=1,
                lead_time_days=2,
                stock=100,
                fetched_at=now - timedelta(days=200),
                snapshot_id="snap-digikey-2",
            )
        ],
    )
    candidate_u1 = _candidate(
        "req-u1",
        "U-D",
        tier=SubstitutionTier.TIER_0,
        lifecycle=Lifecycle.ACTIVE,
        offers=[],
    )

    return [
        (req_r1, candidate_r1),
        (req_c1, candidate_c1),
        (req_y1, candidate_y1),
        (req_u1, candidate_u1),
    ]


def _plans_by_mode(plans: list[PurchasePlan]) -> dict[DecisionMode, PurchasePlan]:
    return {plan.mode: plan for plan in plans}


def _run() -> list[PurchasePlan]:
    ctx = _ctx()
    pairs = _build_pairs(ctx.now)
    result = PlanningStage().run(
        PlanningStageInput(pairs=pairs, board_quantity=BOARD_QUANTITY), ctx
    )
    return result.output


def test_produces_exactly_one_plan_per_decision_mode() -> None:
    plans = _run()
    assert {plan.mode for plan in plans} == set(DecisionMode)
    assert len(plans) == len(DecisionMode)


def test_req_u1_is_unfilled_in_every_mode_never_silently_dropped() -> None:
    plans = _run()
    for plan in plans:
        assert "req-u1" in {u.requirement_id for u in plan.unfilled}


def test_lowest_cost_and_fastest_delivery_diverge_on_the_resistor_line() -> None:
    plans = _plans_by_mode(_run())
    lowest_cost = plans[DecisionMode.LOWEST_COST]
    fastest = plans[DecisionMode.FASTEST_DELIVERY]

    # both plans fill the same three fillable requirements (only req-u1 is unfilled)
    assert {line.requirement_id for line in lowest_cost.lines} == {"req-r1", "req-c1", "req-y1"}
    assert {line.requirement_id for line in fastest.lines} == {"req-r1", "req-c1", "req-y1"}

    lowest_cost_r1 = next(line for line in lowest_cost.lines if line.requirement_id == "req-r1")
    fastest_r1 = next(line for line in fastest.lines if line.requirement_id == "req-r1")

    assert lowest_cost_r1.supplier == SupplierId.FIXTURE  # cheap, slow
    assert fastest_r1.supplier == SupplierId.MOUSER  # pricier, fast

    assert lowest_cost.totals.grand_total < fastest.totals.grand_total
    assert fastest.longest_lead_time_days < lowest_cost.longest_lead_time_days
    assert lowest_cost.totals.grand_total == Decimal("25.50")
    assert fastest.totals.grand_total == Decimal("33.00")
    assert lowest_cost.longest_lead_time_days == 30
    assert fastest.longest_lead_time_days == 5


def test_lowest_risk_excludes_the_tier2_nrnd_and_stale_candidates() -> None:
    plans = _plans_by_mode(_run())
    lowest_risk = plans[DecisionMode.LOWEST_RISK]

    # only req-r1 survives the lowest_risk hard filter (tier<=1, active, fresh, well-stocked)
    assert {line.requirement_id for line in lowest_risk.lines} == {"req-r1"}
    unfilled_ids = {u.requirement_id for u in lowest_risk.unfilled}
    assert unfilled_ids == {"req-c1", "req-y1", "req-u1"}


def test_warnings_flag_nrnd_high_tier_and_stale_offer() -> None:
    plans = _plans_by_mode(_run())
    lowest_cost = plans[DecisionMode.LOWEST_COST]

    kinds_by_requirement: dict[str, set[PlanWarningKind]] = {}
    for warning in lowest_cost.warnings:
        assert warning.requirement_id is not None
        kinds_by_requirement.setdefault(warning.requirement_id, set()).add(warning.kind)

    assert kinds_by_requirement["req-c1"] == {
        PlanWarningKind.NRND_LIFECYCLE,
        PlanWarningKind.HIGH_TIER_SUBSTITUTION,
    }
    assert kinds_by_requirement["req-y1"] == {PlanWarningKind.STALE_OFFER}
    assert "req-r1" not in kinds_by_requirement


def test_planning_stage_is_deterministic_across_runs() -> None:
    first = _run()
    second = _run()
    assert [p.model_dump_json() for p in first] == [p.model_dump_json() for p in second]
