"""The `planning` pipeline stage: one `PurchasePlan` per `DecisionMode`.

Purity note: no I/O, no RNG. `ctx.now` is used only for the offer-freshness check
(`STALE_OFFER` warnings) -- everything else is deterministic given the input pairs,
`board_quantity`, and `PlanningConfig`, per
`.github/instructions/pipeline-stages.instructions.md`.
"""

from dataclasses import dataclass

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import DecisionMode, Lifecycle, PlanWarningKind, SubstitutionTier
from pcbpick.contracts.plan import PlanWarning, PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult
from pcbpick.planning.config import DEFAULT_PLANNING_CONFIG, PlanningConfig
from pcbpick.planning.multi_supplier import (
    LineOption,
    build_line_options,
    build_plan,
    determine_plan_currency,
    select_plan_for_mode,
)
from pcbpick.planning.order_quantity import find_buy_up_opportunity

PlanningStagePair = tuple[NormalizedRequirement, PartCandidate]

# Every `DecisionMode` member, in a fixed order -- this stage produces exactly one
# `PurchasePlan` per member, per `.github/instructions/pipeline-stages.instructions.md`.
_ALL_MODES = sorted(DecisionMode, key=lambda mode: mode.value)


@dataclass(frozen=True)
class PlanningStageInput:
    """One (requirement, candidate) pair per row, mirroring `PolicyStageInput`'s
    shape, plus the board quantity every plan is computed against."""

    pairs: list[PlanningStagePair]
    board_quantity: int


def _compute_warnings(lines: list[LineOption], config: PlanningConfig) -> list[PlanWarning]:
    warnings: list[PlanWarning] = []
    for line in lines:
        if line.is_stale:
            fetched_date = line.offer.fetched_at.date().isoformat()
            warnings.append(
                PlanWarning(
                    kind=PlanWarningKind.STALE_OFFER,
                    requirement_id=line.requirement_id,
                    message=(
                        f"offer {line.offer.sku} ({line.offer.supplier.value}) for "
                        f"{line.candidate.mpn} was fetched {fetched_date}, older than the "
                        f"{config.freshness_window_days}-day freshness window; must be "
                        "re-fetched before this plan can be approved"
                    ),
                )
            )
        if line.candidate.lifecycle == Lifecycle.NRND:
            warnings.append(
                PlanWarning(
                    kind=PlanWarningKind.NRND_LIFECYCLE,
                    requirement_id=line.requirement_id,
                    message=f"{line.candidate.mpn} ({line.candidate.manufacturer}) is NRND",
                )
            )
        elif line.candidate.lifecycle == Lifecycle.EOL:
            warnings.append(
                PlanWarning(
                    kind=PlanWarningKind.EOL_LIFECYCLE,
                    requirement_id=line.requirement_id,
                    message=f"{line.candidate.mpn} ({line.candidate.manufacturer}) is EOL",
                )
            )
        if line.candidate.substitution_tier >= SubstitutionTier.TIER_2:
            warnings.append(
                PlanWarning(
                    kind=PlanWarningKind.HIGH_TIER_SUBSTITUTION,
                    requirement_id=line.requirement_id,
                    message=(
                        f"{line.candidate.mpn} is a tier-{int(line.candidate.substitution_tier)} "
                        "substitution for this requirement"
                    ),
                )
            )
    warnings.sort(key=lambda w: (w.kind.value, w.requirement_id or "", w.message))
    return warnings


def _buy_up_issues(lines: list[LineOption]) -> list[StageIssue]:
    """`INFO` issues for break-point buy-up opportunities.

    Surfaced via `StageIssue`, not `PlanWarning`/`PlanLine`: neither contract has a
    field or `PlanWarningKind` member for this today (contracts are frozen for this
    milestone), and a buy-up is a proposal, never silently applied to `order_qty`.
    """
    issues: list[StageIssue] = []
    for line in lines:
        opportunity = find_buy_up_opportunity(
            line.order_qty, line.extended_price, line.offer.spq, line.offer.price_breaks
        )
        if opportunity is not None:
            issues.append(
                StageIssue(
                    severity=Severity.INFO,
                    code="buy_up_opportunity",
                    message=(
                        f"requirement {line.requirement_id} ({line.candidate.mpn}, "
                        f"{line.offer.sku}): ordering {opportunity.extra_qty} more "
                        f"(-> {opportunity.new_order_qty}) would save "
                        f"{opportunity.saving} {line.currency} in total; not applied"
                    ),
                    item_id=line.requirement_id,
                )
            )
    return issues


class PlanningStage:
    """Produces one `PurchasePlan` per `DecisionMode` from priced, policy-scored candidates."""

    name = "planning"

    def __init__(self, config: PlanningConfig = DEFAULT_PLANNING_CONFIG) -> None:
        self._config = config

    def run(self, inp: PlanningStageInput, ctx: StageContext) -> StageResult[list[PurchasePlan]]:
        issues: list[StageIssue] = [
            StageIssue(
                severity=Severity.INFO,
                code="planning_config_versions",
                message=(
                    f"planning stage used attrition config {self._config.attrition.version}, "
                    f"shipping config {self._config.shipping.version}, balanced weights "
                    f"{self._config.balanced_weights.version}"
                ),
            )
        ]

        plan_currency = determine_plan_currency(inp.pairs)
        options_by_requirement, matrix_issues = build_line_options(
            inp.pairs, inp.board_quantity, self._config, ctx.now, plan_currency
        )
        issues.extend(matrix_issues)

        plans: list[PurchasePlan] = []
        for mode in _ALL_MODES:
            lines, unfilled = select_plan_for_mode(
                mode, options_by_requirement, inp.board_quantity, plan_currency, self._config
            )
            warnings = _compute_warnings(lines, self._config)
            issues.extend(_buy_up_issues(lines))
            plans.append(
                build_plan(
                    mode, inp.board_quantity, plan_currency, lines, self._config, unfilled, warnings
                )
            )

        plans.sort(key=lambda plan: plan.mode.value)
        return StageResult(output=plans, issues=issues)
