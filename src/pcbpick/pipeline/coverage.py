"""Pure coverage/observability metrics computed over already-produced stage artifacts.

Per `.github/instructions/testing.instructions.md`'s "Tracked metrics" section:

- % of BOM rows normalized without LLM fallback
- % of requirements filled at substitution tier 0 or 1
- Count of `BLOCKING` issues (by code)
- Plan total delta versus the previous run for each decision mode (left to the
  caller: it requires two runs' `PurchasePlan`s, which this module has no opinion
  about how to obtain -- see `plan_total_delta` below)

Every function here is a pure function of artifacts a stage has already produced
(`NormalizedRequirement`s, `PartCandidate`s, `StageIssue`s, `PurchasePlan`s) -- none
of them re-run a stage, touch the clock, or use randomness, matching
`.github/instructions/pipeline-stages.instructions.md`.
"""

from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import SubstitutionTier
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.results import Severity, StageIssue

ConfidenceTier = Literal["high", "medium", "low"]

# Thresholds match the only two scores `normalize/requirement_builder.py` actually
# produces today (0.95 when fully resolved, 0.3 when unresolved fields or an LLM
# fallback merge are present) -- "medium" exists as a tier for a future, more
# granular confidence scorer to land in without a contract change here.
_HIGH_CONFIDENCE_MIN = Decimal("0.9")
_LOW_CONFIDENCE_MAX = Decimal("0.5")

# The `normalize_fallback` LLM call site tags every merged parameter/fragment field
# with `ValueSource.LLM_INFERRED`, and its own success path appends this exact
# substring to `Confidence.reasons` (`requirement_builder.py`) -- both are the only
# artifact-visible signals a fallback merge happened, since a successful merge emits
# no `StageIssue` of its own (only a failed one does: `llm_fallback_unavailable`).
_LLM_FALLBACK_SUCCESS_REASON_MARKER = "normalize_fallback"


def confidence_tier(score: float | Decimal) -> ConfidenceTier:
    """Buckets a `Confidence.score` into the tier vocabulary the eval suite scores."""
    value = Decimal(str(score))
    if value >= _HIGH_CONFIDENCE_MIN:
        return "high"
    if value < _LOW_CONFIDENCE_MAX:
        return "low"
    return "medium"


def used_llm_fallback(requirement: NormalizedRequirement) -> bool:
    """True if this requirement's category/parameters were supplemented by a
    successful `normalize_fallback` merge (see the module docstring's provenance
    note -- there is no dedicated boolean field for this, so the reason-text marker
    is the only artifact-derived signal available)."""
    return any(
        _LLM_FALLBACK_SUCCESS_REASON_MARKER in reason for reason in requirement.confidence.reasons
    )


def pct_rows_normalized_without_llm_fallback(
    requirements: Sequence[NormalizedRequirement],
    normalize_issues: Sequence[StageIssue],
) -> Decimal | None:
    """% of rows that needed no `normalize_fallback` attempt at all (success or not).

    `None` when there are no rows to report a percentage over -- never `0`, which
    would misrepresent "no data" as "zero rows normalized cleanly".
    """
    total = len(requirements)
    if total == 0:
        return None
    fallback_successes = sum(1 for r in requirements if used_llm_fallback(r))
    fallback_failures = sum(
        1 for issue in normalize_issues if issue.code == "llm_fallback_unavailable"
    )
    attempted = fallback_successes + fallback_failures
    without_fallback = total - attempted
    return _percentage(without_fallback, total)


def pct_requirements_filled_at_tier_0_or_1(
    requirement_ids: Sequence[str], policy_candidates: Sequence[PartCandidate]
) -> Decimal | None:
    """% of the given requirements with at least one tier-0-or-1 policy-scored candidate."""
    total = len(requirement_ids)
    if total == 0:
        return None
    candidates_by_requirement: dict[str, list[PartCandidate]] = defaultdict(list)
    for candidate in policy_candidates:
        candidates_by_requirement[candidate.requirement_id].append(candidate)
    filled = sum(
        1
        for requirement_id in requirement_ids
        if any(
            candidate.substitution_tier in (SubstitutionTier.TIER_0, SubstitutionTier.TIER_1)
            for candidate in candidates_by_requirement.get(requirement_id, [])
        )
    )
    return _percentage(filled, total)


def blocking_issue_counts_by_code(*issue_lists: Sequence[StageIssue]) -> dict[str, int]:
    """Count of `BLOCKING` `StageIssue`s by `code`, across every issue list given."""
    counts: dict[str, int] = {}
    for issues in issue_lists:
        for issue in issues:
            if issue.severity == Severity.BLOCKING:
                counts[issue.code] = counts.get(issue.code, 0) + 1
    return counts


def plan_total_delta(previous: PurchasePlan | None, current: PurchasePlan) -> Decimal | None:
    """`current.grand_total` minus `previous.grand_total`, same currency required.

    `None` when there is no previous plan to compare against (first run for this
    decision mode) -- never `0`, which would misrepresent "no prior data" as "no
    change". Raises `ValueError` if the two plans are not denominated in the same
    currency; comparing totals across currencies without conversion would be a
    silently wrong number, not a delta.
    """
    if previous is None:
        return None
    if previous.totals.currency != current.totals.currency:
        raise ValueError(
            f"cannot delta plan totals across currencies: {previous.totals.currency!r} vs "
            f"{current.totals.currency!r}"
        )
    return current.totals.grand_total - previous.totals.grand_total


def _percentage(count: int, total: int) -> Decimal:
    return (Decimal(count) / Decimal(total) * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
