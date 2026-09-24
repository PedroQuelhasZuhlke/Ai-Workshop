"""Multi-supplier plan assembly: the requirement x supplier x offer matrix, bounded
supplier-subset enumeration, cheapest-within-subset assignment, and decision-mode
selection, per `.github/skills/procurement-math/SKILL.md`'s "Multi-supplier split"
section. No solver dependency -- plain exhaustive enumeration, as the skill doc
directs for a small supplier count.

## Single-currency plans

`PurchasePlan.totals.currency` is one `CurrencyCode`. Per the skill doc's money
rules ("never convert silently"), this module never mixes currencies within one
plan: `determine_plan_currency` picks the plan's single currency up front, and any
offer priced in a different currency is excluded from that plan's matrix entirely
(recorded as an `INFO` issue) rather than converted.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import DecisionMode, Lifecycle, SubstitutionTier, SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.plan import (
    PlanLine,
    PlanTotals,
    PlanWarning,
    PurchasePlan,
    UnfilledRequirement,
)
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.errors import ContractViolationError
from pcbpick.pipeline.results import Severity, StageIssue
from pcbpick.planning.attrition import classify_part_class, compute_required_qty
from pcbpick.planning.config import PlanningConfig
from pcbpick.planning.decision_modes import CandidateMetrics, rank
from pcbpick.planning.order_quantity import (
    compute_line_total,
    resolve_order_qty,
    select_price_break,
)
from pcbpick.planning.shipping import compute_shipping_cost

_MAX_SUPPLIER_SUBSET_SIZE = 3
_MIN_RISK_STOCK_MULTIPLE = 2


@dataclass(frozen=True)
class LineOption:
    """One viable way to fill one requirement: a candidate at a priced, dated offer."""

    requirement_id: str
    candidate: PartCandidate
    offer: SupplierOffer
    required_qty: int
    base_qty: int
    order_qty: int
    unit_price: Decimal
    extended_price: Decimal
    currency: str
    is_stale: bool


def determine_plan_currency(pairs: list[tuple[NormalizedRequirement, PartCandidate]]) -> str:
    """Picks the plan's single currency: the most common one across every price
    break on every offer, ties broken alphabetically for determinism."""
    counts: dict[str, int] = {}
    for _, candidate in pairs:
        for offer in candidate.offers:
            for price_break in offer.price_breaks:
                counts[price_break.currency] = counts.get(price_break.currency, 0) + 1
    if not counts:
        return "USD"  # nothing priced at all; an arbitrary stable placeholder, not a fact
    return min(counts, key=lambda currency: (-counts[currency], currency))


def build_line_options(
    pairs: list[tuple[NormalizedRequirement, PartCandidate]],
    board_quantity: int,
    config: PlanningConfig,
    now: datetime,
    plan_currency: str,
) -> tuple[dict[str, list[LineOption]], list[StageIssue]]:
    """Builds the requirement -> viable-offer matrix. See the module docstring for
    the single-currency rule. `PartCandidate`s at tier 3 are skipped defensively
    (policy should already have rejected them) with a `BLOCKING` issue."""
    options: dict[str, list[LineOption]] = {req.requirement_id: [] for req, _ in pairs}
    issues: list[StageIssue] = []
    freshness_window = timedelta(days=config.freshness_window_days)

    for requirement, candidate in sorted(
        pairs, key=lambda p: (p[0].requirement_id, p[1].mpn, p[1].manufacturer)
    ):
        rid = requirement.requirement_id
        if candidate.substitution_tier == SubstitutionTier.TIER_3:
            issues.append(
                StageIssue(
                    severity=Severity.BLOCKING,
                    code="tier3_candidate_rejected_by_planning",
                    message=(
                        f"candidate {candidate.mpn} for requirement {rid} is substitution "
                        "tier 3; policy should already have rejected it. Skipped defensively "
                        "and never considered for a plan"
                    ),
                    item_id=rid,
                )
            )
            continue

        part_class_result = classify_part_class(requirement, candidate)
        if part_class_result.used_dimension_fallback:
            issues.append(
                StageIssue(
                    severity=Severity.INFO,
                    code="attrition_class_dimension_fallback",
                    message=(
                        f"candidate {candidate.mpn} for requirement {rid} has no footprint "
                        "dimensions on either the requirement or the candidate; classified as "
                        "passives >0805 (5% attrition) by default"
                    ),
                    item_id=rid,
                )
            )
        base_qty = board_quantity * requirement.quantity_per_board
        required_qty = compute_required_qty(
            board_quantity,
            requirement.quantity_per_board,
            part_class_result.part_class,
            config.attrition,
        )

        if not candidate.offers:
            issues.append(
                StageIssue(
                    severity=Severity.INFO,
                    code="candidate_has_no_offers",
                    message=(
                        f"candidate {candidate.mpn} for requirement {rid} has no supplier "
                        "offers; it cannot be used to fill this requirement"
                    ),
                    item_id=rid,
                )
            )

        for offer in candidate.offers:
            order_qty = resolve_order_qty(required_qty, offer)
            price_break = select_price_break(order_qty, offer.price_breaks)
            if price_break is None:
                issues.append(
                    StageIssue(
                        severity=Severity.WARNING,
                        code="offer_missing_price_break",
                        message=(
                            f"offer {offer.sku} ({offer.supplier.value}) for candidate "
                            f"{candidate.mpn} (requirement {rid}) has no price break applicable "
                            f"at order quantity {order_qty}; excluded from planning"
                        ),
                        item_id=rid,
                    )
                )
                continue
            if price_break.currency != plan_currency:
                issues.append(
                    StageIssue(
                        severity=Severity.INFO,
                        code="offer_excluded_currency_mismatch",
                        message=(
                            f"offer {offer.sku} ({offer.supplier.value}) for candidate "
                            f"{candidate.mpn} (requirement {rid}) is priced in "
                            f"{price_break.currency}, not this plan's {plan_currency}; "
                            "excluded rather than silently converted"
                        ),
                        item_id=rid,
                    )
                )
                continue

            is_stale = (now - offer.fetched_at) > freshness_window
            extended_price = compute_line_total(order_qty, price_break.unit_price)
            options[rid].append(
                LineOption(
                    requirement_id=rid,
                    candidate=candidate,
                    offer=offer,
                    required_qty=required_qty,
                    base_qty=base_qty,
                    order_qty=order_qty,
                    unit_price=price_break.unit_price,
                    extended_price=extended_price,
                    currency=plan_currency,
                    is_stale=is_stale,
                )
            )

    for opts in options.values():
        opts.sort(key=lambda opt: (opt.extended_price, opt.offer.supplier.value, opt.offer.sku))

    return options, issues


def _is_low_risk(option: LineOption) -> bool:
    """The `lowest_risk` mode's hard filter, per the skill doc's decision-mode table."""
    stock = option.offer.stock
    return (
        option.candidate.substitution_tier <= SubstitutionTier.TIER_1
        and option.candidate.lifecycle == Lifecycle.ACTIVE
        and not option.is_stale
        and stock is not None
        and stock >= _MIN_RISK_STOCK_MULTIPLE * option.order_qty
    )


def _risk_penalty(lines: list[LineOption]) -> Decimal:
    """One penalty point per risk flag on a line: lower is safer. Used only by the
    `balanced` mode's normalized score -- `lowest_risk` uses a hard filter instead."""
    penalty = Decimal("0")
    for line in lines:
        if line.candidate.substitution_tier > SubstitutionTier.TIER_1:
            penalty += 1
        if line.candidate.lifecycle != Lifecycle.ACTIVE:
            penalty += 1
        if line.is_stale:
            penalty += 1
        stock = line.offer.stock
        if stock is None or stock < _MIN_RISK_STOCK_MULTIPLE * line.order_qty:
            penalty += 1
    return penalty


def _option_sort_key(option: LineOption) -> tuple[Decimal, int, str, str]:
    lead_time = option.offer.lead_time_days if option.offer.lead_time_days is not None else 0
    return (option.extended_price, lead_time, option.offer.supplier.value, option.offer.sku)


def _assign_cheapest_within_subset(
    fillable: dict[str, list[LineOption]], subset: frozenset[SupplierId]
) -> list[LineOption] | None:
    """Assigns every requirement in `fillable` to its cheapest option within `subset`.

    Returns `None` if any requirement has no option from a supplier in `subset`."""
    lines: list[LineOption] = []
    for requirement_id in sorted(fillable):
        usable = [opt for opt in fillable[requirement_id] if opt.offer.supplier in subset]
        if not usable:
            return None
        lines.append(min(usable, key=_option_sort_key))
    return lines


def build_plan(
    mode: DecisionMode,
    board_quantity: int,
    plan_currency: str,
    lines: list[LineOption],
    config: PlanningConfig,
    unfilled: list[UnfilledRequirement],
    warnings: list[PlanWarning],
) -> PurchasePlan:
    """Assembles a full `PurchasePlan` from a chosen set of `LineOption`s. Used both
    for the final, returned plan and (with empty `unfilled`/`warnings`) internally
    for provisional per-subset scoring -- the totals math is identical either way."""
    sorted_lines = sorted(lines, key=lambda line: line.requirement_id)
    plan_lines = [
        PlanLine(
            requirement_id=line.requirement_id,
            mpn=line.candidate.mpn,
            manufacturer=line.candidate.manufacturer,
            supplier=line.offer.supplier,
            sku=line.offer.sku,
            substitution_tier=line.candidate.substitution_tier,
            order_qty=line.order_qty,
            unit_price=line.unit_price,
            extended_price=line.extended_price,
            currency=plan_currency,
            snapshot_id=line.offer.snapshot_id,
        )
        for line in sorted_lines
    ]

    supplier_subtotals: dict[SupplierId, Decimal] = {}
    for line in lines:
        supplier_subtotals[line.offer.supplier] = (
            supplier_subtotals.get(line.offer.supplier, Decimal("0")) + line.extended_price
        )

    shipping_total = Decimal("0")
    for supplier, subtotal in supplier_subtotals.items():
        term = config.shipping.terms_by_supplier.get(supplier)
        if term is None:
            raise ContractViolationError(
                f"no shipping terms configured for supplier {supplier.value!r}"
            )
        shipping_total += compute_shipping_cost(term, subtotal)

    grand_total = sum(supplier_subtotals.values(), Decimal("0")) + shipping_total

    base_total = sum((line.base_qty for line in lines), 0)
    extra_total = sum((line.required_qty - line.base_qty for line in lines), 0)
    attrition_pct = Decimal(extra_total) / Decimal(base_total) if base_total > 0 else Decimal("0")

    return PurchasePlan(
        mode=mode,
        board_quantity=board_quantity,
        attrition_pct=attrition_pct,
        lines=plan_lines,
        totals=PlanTotals(
            currency=plan_currency,
            supplier_subtotals=dict(
                sorted(supplier_subtotals.items(), key=lambda item: item[0].value)
            ),
            shipping_total=shipping_total,
            grand_total=grand_total,
        ),
        longest_lead_time_days=max((line.offer.lead_time_days or 0 for line in lines), default=0),
        supplier_count=len(supplier_subtotals),
        unfilled=sorted(unfilled, key=lambda item: item.requirement_id),
        warnings=sorted(warnings, key=lambda w: (w.kind.value, w.requirement_id or "", w.message)),
        snapshot_ids=sorted({line.offer.snapshot_id for line in lines}),
    )


def select_plan_for_mode(
    mode: DecisionMode,
    options_by_requirement: dict[str, list[LineOption]],
    board_quantity: int,
    plan_currency: str,
    config: PlanningConfig,
) -> tuple[list[LineOption], list[UnfilledRequirement]]:
    """Picks the winning supplier-subset assignment for one `DecisionMode`.

    Returns the chosen lines (sorted by `requirement_id`) and every requirement this
    mode could not fill, each with a reason -- never silently dropped."""
    pool = options_by_requirement
    if mode == DecisionMode.LOWEST_RISK:
        pool = {
            rid: [opt for opt in opts if _is_low_risk(opt)]
            for rid, opts in options_by_requirement.items()
        }

    unfilled: list[UnfilledRequirement] = []
    for requirement_id, opts in pool.items():
        if opts:
            continue
        if options_by_requirement[requirement_id]:
            reason = (
                "no offer for this requirement meets the lowest_risk mode's criteria "
                "(substitution tier <=1, active lifecycle, fresh offer, stock >= "
                f"{_MIN_RISK_STOCK_MULTIPLE}x order quantity); "
                f"{len(options_by_requirement[requirement_id])} offer(s) exist under other "
                "decision modes"
            )
        else:
            reason = "no policy-surviving candidate has a usable priced offer for this requirement"
        unfilled.append(UnfilledRequirement(requirement_id=requirement_id, reason=reason))
    unfilled.sort(key=lambda item: item.requirement_id)

    fillable = {rid: opts for rid, opts in pool.items() if opts}
    if not fillable:
        return [], unfilled

    suppliers = sorted(
        {opt.offer.supplier for opts in fillable.values() for opt in opts}, key=lambda s: s.value
    )
    max_subset_size = min(_MAX_SUPPLIER_SUBSET_SIZE, len(suppliers))

    assignments: list[list[LineOption]] = []
    for size in range(1, max_subset_size + 1):
        for subset in combinations(suppliers, size):
            lines = _assign_cheapest_within_subset(fillable, frozenset(subset))
            if lines is not None:
                assignments.append(lines)

    if not assignments:
        # No <=3-supplier subset can fill every fillable requirement -- fall back to
        # every supplier that has any offer at all rather than silently dropping a
        # fillable requirement (the skill doc's subset bound is a default, not a
        # hard ceiling on coverage).
        lines = _assign_cheapest_within_subset(fillable, frozenset(suppliers))
        assert lines is not None  # every requirement in `fillable` has >=1 option somewhere
        assignments.append(lines)

    plans = [
        build_plan(mode, board_quantity, plan_currency, lines, config, [], [])
        for lines in assignments
    ]
    metrics = [
        CandidateMetrics(plan=plan, risk_penalty=_risk_penalty(lines))
        for lines, plan in zip(assignments, plans, strict=True)
    ]
    winner_index = rank(mode, metrics, config.balanced_weights)
    winning_lines = sorted(assignments[winner_index], key=lambda line: line.requirement_id)
    return winning_lines, unfilled
