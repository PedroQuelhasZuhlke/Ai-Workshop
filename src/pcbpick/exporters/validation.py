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
    plan: PurchasePlan, acknowledged_stale_requirement_ids: frozenset[str]
) -> str | None:
    """No selected line may rest on a stale, un-acknowledged offer.

    Staleness is always computed from the plan's own `PlanWarningKind.STALE_OFFER`
    warnings (set by `PlanningStage` against `ctx.now` and the freshness window) --
    the gate can never fail open by omission. An engineer may override a *specific*
    stale line by acknowledging its `requirement_id` at approval time (the
    `acknowledged_stale_offer_snapshot_ids` field end-to-end through the API/DB/web
    layers -- see `api/db.py`'s `ApprovalRecord` and `web/src/pages/RunPage.tsx` --
    is in practice always populated with the warning's `requirement_id`, since
    `PlanWarning` carries no `snapshot_id` of its own to key on; this function
    matches on that same key rather than fighting the field's historical name).
    The acknowledgment is recorded on the immutable `ApprovalRecord`, so the
    override itself is as auditable as the approval it belongs to. A stale
    requirement that is not acknowledged still blocks export.
    """
    stale_requirement_ids = {
        warning.requirement_id
        for warning in plan.warnings
        if warning.kind == PlanWarningKind.STALE_OFFER and warning.requirement_id is not None
    }
    unacknowledged_ids = sorted(stale_requirement_ids - acknowledged_stale_requirement_ids)
    if unacknowledged_ids:
        return (
            "plan includes stale offer(s) not acknowledged by the approving engineer "
            f"for requirement(s): {', '.join(unacknowledged_ids)}"
        )
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
    acknowledged_stale_requirement_ids: frozenset[str],
    reviewed_high_tier_requirement_ids: frozenset[str],
) -> list[str]:
    """Every export gate, composed. An empty list means every gate passed."""
    checks = (
        check_approved(approved_by, approved_at),
        check_no_stale_offers(plan, acknowledged_stale_requirement_ids),
        check_no_unreviewed_high_tier_lines(plan, reviewed_high_tier_requirement_ids),
        check_no_unfilled_requirements(plan),
        check_every_order_qty_positive(plan),
    )
    return [reason for reason in checks if reason is not None]
