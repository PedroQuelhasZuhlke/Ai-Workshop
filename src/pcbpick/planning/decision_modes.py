"""One scoring/ranking function per `DecisionMode`, per
`.github/skills/procurement-math/SKILL.md`'s decision-mode table. Every score is a
totally ordered tuple ending in `compute_plan_hash`, so two candidate plans that tie
on every objective metric still resolve to a single winner deterministically -- never
by insertion order.

`lowest_risk`'s objective ("tier 0/1 only, active lifecycle, stock >= 2x order qty,
fresh offers") is a hard filter applied by the caller (`planning.multi_supplier`)
before candidates ever reach this module -- once filtered, its only remaining
differentiator is total cost, same shape as `lowest_cost`. `balanced` is the only mode
that needs cross-candidate context (min-max normalization), so it is scored as a
batch rather than one candidate at a time.
"""

from dataclasses import dataclass
from decimal import Decimal

from pcbpick.contracts.enums import DecisionMode
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.errors import ContractViolationError
from pcbpick.planning.config import BalancedWeights
from pcbpick.planning.plan_hash import compute_plan_hash

ScoreKey = tuple[Decimal | int | str, ...]


@dataclass(frozen=True)
class CandidateMetrics:
    """One candidate supplier-subset assignment's plan plus its risk penalty.

    `risk_penalty` is computed by `multi_supplier` (it needs `PartCandidate`/
    `SupplierOffer` data this module never inspects directly) -- lower is safer.
    """

    plan: PurchasePlan
    risk_penalty: Decimal


def score_lowest_cost(metrics: CandidateMetrics) -> ScoreKey:
    plan = metrics.plan
    return (
        plan.totals.grand_total,
        plan.supplier_count,
        plan.longest_lead_time_days,
        compute_plan_hash(plan),
    )


def score_fastest_delivery(metrics: CandidateMetrics) -> ScoreKey:
    plan = metrics.plan
    return (plan.longest_lead_time_days, plan.totals.grand_total, compute_plan_hash(plan))


def score_fewest_suppliers(metrics: CandidateMetrics) -> ScoreKey:
    plan = metrics.plan
    return (plan.supplier_count, plan.totals.grand_total, compute_plan_hash(plan))


def score_lowest_risk(metrics: CandidateMetrics) -> ScoreKey:
    plan = metrics.plan
    return (plan.totals.grand_total, compute_plan_hash(plan))


def _normalize(values: list[Decimal]) -> list[Decimal]:
    """Min-max normalizes to `[0, 1]`; every value normalizes to `0` if all are equal."""
    lowest, highest = min(values), max(values)
    if highest == lowest:
        return [Decimal("0") for _ in values]
    return [(value - lowest) / (highest - lowest) for value in values]


def score_balanced(candidates: list[CandidateMetrics], weights: BalancedWeights) -> list[ScoreKey]:
    """One score per candidate, in the same order, each ending in its `plan_hash`."""
    costs = _normalize([c.plan.totals.grand_total for c in candidates])
    lead_times = _normalize([Decimal(c.plan.longest_lead_time_days) for c in candidates])
    supplier_counts = _normalize([Decimal(c.plan.supplier_count) for c in candidates])
    risks = _normalize([c.risk_penalty for c in candidates])

    scores: list[ScoreKey] = []
    for candidate, cost, lead_time, supplier_count, risk in zip(
        candidates, costs, lead_times, supplier_counts, risks, strict=True
    ):
        weighted = (
            weights.cost * cost
            + weights.lead_time * lead_time
            + weights.supplier_count * supplier_count
            + weights.risk * risk
        )
        scores.append(
            (weighted, candidate.plan.totals.grand_total, compute_plan_hash(candidate.plan))
        )
    return scores


def _score_single(mode: DecisionMode, metrics: CandidateMetrics) -> ScoreKey:
    match mode:
        case DecisionMode.LOWEST_COST:
            return score_lowest_cost(metrics)
        case DecisionMode.FASTEST_DELIVERY:
            return score_fastest_delivery(metrics)
        case DecisionMode.FEWEST_SUPPLIERS:
            return score_fewest_suppliers(metrics)
        case DecisionMode.LOWEST_RISK:
            return score_lowest_risk(metrics)
        case DecisionMode.BALANCED:
            raise AssertionError("balanced mode is scored as a batch via score_balanced")


def rank(mode: DecisionMode, candidates: list[CandidateMetrics], weights: BalancedWeights) -> int:
    """Returns the index of the winning candidate in `candidates` for `mode`."""
    if not candidates:
        raise ContractViolationError("no candidate assignment to rank")

    keys: list[ScoreKey]
    if mode == DecisionMode.BALANCED:
        keys = score_balanced(candidates, weights)
    else:
        keys = [_score_single(mode, c) for c in candidates]

    return min(range(len(candidates)), key=lambda i: keys[i])
