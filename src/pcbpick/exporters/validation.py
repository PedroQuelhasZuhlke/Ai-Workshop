"""Pre-export validation gates.

Each gate function inspects one condition and returns a rejection reason (`str`), or
`None` if the gate passes -- never raises on bad input data, per
`.github/instructions/pipeline-stages.instructions.md`. `validate_for_export`
composes every gate so an engineer sees every failure in one pass, not one at a time.
See `.github/skills/supplier-export/SKILL.md`'s "Gates before any file is produced".
"""

from datetime import datetime

from pcbpick.contracts.enums import PlanWarningKind, SubstitutionTier
from pcbpick.contracts.plan import PurchasePlan


def check_approved(approved_by: str, approved_at: datetime | None) -> str | None:
    """The plan must carry a named approver and a recorded approval timestamp."""
    if not approved_by.strip():
        return "plan has no recorded approver; an export cannot proceed without an approval"
    if approved_at is None:
        return "plan has no recorded approval timestamp; an export cannot proceed"
    return None


def check_no_stale_offers(
    plan: PurchasePlan, stale_offer_snapshot_ids: frozenset[str]
) -> str | None:
    """No selected line may rest on a stale offer.

    Staleness has two independent sources, both checked: the plan's own
    `PlanWarningKind.STALE_OFFER` warnings (computed by `PlanningStage` against
    `ctx.now` and the freshness window -- this is the primary, always-on check, so
    the gate cannot fail open just because a caller forgot to populate
    `stale_offer_snapshot_ids`), and any snapshot the caller separately flags via
    `stale_offer_snapshot_ids` (e.g. a fresh re-validation performed after the plan
    was built, per `.github/skills/supplier-export/SKILL.md` gate 2's
    "re-validate against the supplier before writing").
    """
    warned_ids = {
        warning.requirement_id
        for warning in plan.warnings
        if warning.kind == PlanWarningKind.STALE_OFFER and warning.requirement_id is not None
    }
    flagged_ids = {
        line.requirement_id for line in plan.lines if line.snapshot_id in stale_offer_snapshot_ids
    }
    stale_ids = sorted(warned_ids | flagged_ids)
    if stale_ids:
        return f"plan includes stale offer snapshot(s) for requirement(s): {', '.join(stale_ids)}"
    return None


def check_no_unreviewed_high_tier_lines(
    plan: PurchasePlan, reviewed_high_tier_requirement_ids: frozenset[str]
) -> str | None:
    """No tier-2+ substitution line may export without an explicit engineer review."""
    unreviewed_ids = sorted(
        {
            line.requirement_id
            for line in plan.lines
            if line.substitution_tier >= SubstitutionTier.TIER_2
            and line.requirement_id not in reviewed_high_tier_requirement_ids
        }
    )
    if unreviewed_ids:
        return (
            "plan includes unreviewed tier-2+ substitution(s) for requirement(s): "
            f"{', '.join(unreviewed_ids)}"
        )
    return None


def check_no_unfilled_requirements(plan: PurchasePlan) -> str | None:
    """An export can never proceed with unfilled requirements silently omitted."""
    if plan.unfilled:
        ids = ", ".join(sorted(item.requirement_id for item in plan.unfilled))
        return f"plan has unfilled requirement(s); cannot export a partial file: {ids}"
    return None


def check_every_order_qty_positive(plan: PurchasePlan) -> str | None:
    """Defensive backstop: `PlanLine.order_qty` is already `Field(gt=0)`-enforced at
    the contract boundary, so no plan reaching this function can violate it today.
    Kept as an explicit "no partial file" gate in case that constraint is ever
    relaxed upstream without this stage being revisited."""
    non_positive_ids = sorted({line.requirement_id for line in plan.lines if line.order_qty <= 0})
    if non_positive_ids:
        ids = ", ".join(non_positive_ids)
        return f"plan has non-positive order quantity for requirement(s): {ids}"
    return None


def validate_for_export(
    plan: PurchasePlan,
    approved_by: str,
    approved_at: datetime | None,
    stale_offer_snapshot_ids: frozenset[str],
    reviewed_high_tier_requirement_ids: frozenset[str],
) -> list[str]:
    """Every export gate, composed. An empty list means every gate passed."""
    checks = (
        check_approved(approved_by, approved_at),
        check_no_stale_offers(plan, stale_offer_snapshot_ids),
        check_no_unreviewed_high_tier_lines(plan, reviewed_high_tier_requirement_ids),
        check_no_unfilled_requirements(plan),
        check_every_order_qty_positive(plan),
    )
    return [reason for reason in checks if reason is not None]
