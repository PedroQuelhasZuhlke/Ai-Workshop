"""Golden-BOM eval case runner: loads a `case.json`, drives the real stage chain,
and scores the fields present in its `expect` block. See `evals/README.md`'s
"Runner requirements" section -- this module is exactly that runner.

Purity/determinism note: every stage invocation here goes through the same
`StageContext`/`Stage.run` boundary every other caller uses (`api/orchestrator.py`'s
`run_sourcing_chain` is the closest existing precedent for chaining
expand->source->policy->evaluate directly). No stage is re-implemented, patched, or
given hidden inputs. `StageContext.now`/`.rng` are fixed per case id, so running the
same case twice produces byte-identical `EvalCaseResult`s.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Any

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import SubstitutionTier
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.llm.fakes import FakeLLMClient
from pcbpick.normalize.stage import NormalizeStage
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.coverage import confidence_tier
from pcbpick.pipeline.results import Severity, StageIssue
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.policy.stage import PolicyStage, PolicyStageInput
from pcbpick.sourcing.evaluate import EvaluateStage, EvaluateStageInput
from pcbpick.sourcing.expand import ExpandStage
from pcbpick.sourcing.stage import SourceStage
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)

# Every stage name a case's `chain` may name, in the order the real pipeline runs
# them (`docs/architecture.md`). A case's `chain` is always a prefix of this order.
_STAGE_ORDER = ["ingest", "normalize", "expand", "source", "policy", "evaluate"]


@dataclass(frozen=True)
class FieldScore:
    """One `expect` field's outcome: which field, pass/fail, and why."""

    field: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    case_path: Path
    field_scores: list[FieldScore] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(score.passed for score in self.field_scores)

    @property
    def failed_scores(self) -> list[FieldScore]:
        return [score for score in self.field_scores if not score.passed]


@dataclass(frozen=True)
class _ChainArtifacts:
    requirements: list[NormalizedRequirement]
    ingest_issues: list[StageIssue]
    normalize_issues: list[StageIssue]
    expand_issues: list[StageIssue]
    source_candidates: list[PrePolicyCandidate] | None
    source_issues: list[StageIssue]
    policy_candidates: list[PartCandidate] | None
    policy_issues: list[StageIssue]
    evaluate_candidates: list[PartCandidate] | None
    evaluate_issues: list[StageIssue]
    dnp_excluded: int


def discover_case_paths(cases_root: Path | None = None) -> list[Path]:
    """Every `case.json` under `evals/cases/`, sorted for a deterministic report order."""
    root = cases_root or (_REPO_ROOT / "evals" / "cases")
    return sorted(root.glob("*/case.json"))


def run_eval_case(case_path: Path, *, repo_root: Path | None = None) -> EvalCaseResult:
    """Loads `case_path`, runs its `chain`, and scores every field in its `expect`."""
    root = repo_root or _REPO_ROOT
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id: str = case["case_id"]
    chain: list[str] = case["chain"]
    inputs: dict[str, Any] = case["inputs"]
    expect: dict[str, Any] = case.get("expect", {})

    ctx = StageContext(
        run_id=f"eval-{case_id}", now=_FIXED_NOW, rng=Random(case_id), config=PipelineConfig()
    )

    artifacts = _run_chain(inputs=inputs, chain=chain, ctx=ctx, repo_root=root)
    scores = _score_expect(expect, artifacts)
    return EvalCaseResult(case_id=case_id, case_path=case_path, field_scores=scores)


def run_all_eval_cases(cases_root: Path | None = None) -> list[EvalCaseResult]:
    return [run_eval_case(path) for path in discover_case_paths(cases_root)]


# --------------------------------------------------------------------------- chain


def _run_chain(
    *, inputs: dict[str, Any], chain: list[str], ctx: StageContext, repo_root: Path
) -> _ChainArtifacts:
    ingest_issues: list[StageIssue] = []
    dnp_excluded = 0

    if "bom_file" in inputs:
        bom_path = repo_root / inputs["bom_file"]
        normalize_client = _fake_client(inputs, "normalize_fallback_fixture", repo_root)

        ingest_sr = IngestStage().run(
            IngestInput(file_name=bom_path.name, content=bom_path.read_bytes()), ctx
        )
        ingest_issues = ingest_sr.issues
        dnp_excluded = sum(1 for line in ingest_sr.output.lines if not line.populate)

        normalize_sr = NormalizeStage(llm_client=normalize_client).run(ingest_sr.output, ctx)
        requirements = normalize_sr.output
        normalize_issues = normalize_sr.issues
    elif "normalized_requirements" in inputs:
        requirements = sorted(
            (
                NormalizedRequirement.model_validate(item)
                for item in inputs["normalized_requirements"]
            ),
            key=lambda r: r.requirement_id,
        )
        normalize_issues = []
    else:
        raise ValueError(
            "case inputs must contain exactly one of 'bom_file' or 'normalized_requirements'"
        )

    expand_issues: list[StageIssue] = []
    source_candidates: list[PrePolicyCandidate] | None = None
    source_issues: list[StageIssue] = []
    policy_candidates: list[PartCandidate] | None = None
    policy_issues: list[StageIssue] = []
    evaluate_candidates: list[PartCandidate] | None = None
    evaluate_issues: list[StageIssue] = []

    requirement_by_id = {r.requirement_id: r for r in requirements}

    if "expand" in chain:
        expand_sr = ExpandStage().run(requirements, ctx)
        expand_issues = expand_sr.issues
        expand_queries = expand_sr.output
    else:
        expand_queries = None

    if "source" in chain:
        assert expand_queries is not None
        catalog_path = repo_root / inputs["catalog_snapshot"]
        source_sr = SourceStage([FixtureAdapter([catalog_path])]).run(expand_queries, ctx)
        source_candidates = source_sr.output
        source_issues = source_sr.issues

    if "policy" in chain:
        assert source_candidates is not None
        policy_pairs = [
            (requirement_by_id[c.requirement_id], c)
            for c in source_candidates
            if c.requirement_id in requirement_by_id
        ]
        policy_sr = PolicyStage().run(PolicyStageInput(pairs=policy_pairs), ctx)
        policy_candidates = policy_sr.output
        policy_issues = policy_sr.issues

    if "evaluate" in chain:
        assert policy_candidates is not None
        evaluate_client = _fake_client(inputs, "candidate_rationale_fixture", repo_root)
        evaluate_pairs = [
            (requirement_by_id[c.requirement_id], c)
            for c in policy_candidates
            if c.requirement_id in requirement_by_id
        ]
        evaluate_sr = EvaluateStage(llm_client=evaluate_client).run(
            EvaluateStageInput(pairs=evaluate_pairs), ctx
        )
        evaluate_candidates = evaluate_sr.output
        evaluate_issues = evaluate_sr.issues

    return _ChainArtifacts(
        requirements=requirements,
        ingest_issues=ingest_issues,
        normalize_issues=normalize_issues,
        expand_issues=expand_issues,
        source_candidates=source_candidates,
        source_issues=source_issues,
        policy_candidates=policy_candidates,
        policy_issues=policy_issues,
        evaluate_candidates=evaluate_candidates,
        evaluate_issues=evaluate_issues,
        dnp_excluded=dnp_excluded,
    )


def _fake_client(inputs: dict[str, Any], fixture_key: str, repo_root: Path) -> FakeLLMClient | None:
    llm_inputs = inputs.get("llm")
    if not llm_inputs or fixture_key not in llm_inputs:
        return None
    fixture_path = repo_root / llm_inputs[fixture_key]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return FakeLLMClient(model_id="eval-fixture", default_response=fixture["response_text"])


# -------------------------------------------------------------------------- scoring


def _score_expect(expect: dict[str, Any], artifacts: _ChainArtifacts) -> list[FieldScore]:
    scores: list[FieldScore] = []
    unresolved_requirements = [r for r in artifacts.requirements if r.unresolved]
    unresolved_count = len(unresolved_requirements)
    unresolved_field_tally = Counter(f for r in unresolved_requirements for f in r.unresolved)
    category_tally = Counter(r.category.value for r in artifacts.requirements)
    requirements_sourced = sum(1 for r in artifacts.requirements if not r.unresolved)

    def add(field_name: str, passed: bool, detail: str) -> None:
        scores.append(FieldScore(field=field_name, passed=passed, detail=detail))

    if "normalized_rows" in expect:
        actual = len(artifacts.requirements)
        expected = expect["normalized_rows"]
        add("normalized_rows", actual == expected, f"expected {expected}, got {actual}")

    if "dnp_excluded" in expect:
        expected = expect["dnp_excluded"]
        add(
            "dnp_excluded",
            artifacts.dnp_excluded == expected,
            f"expected {expected}, got {artifacts.dnp_excluded}",
        )

    if "quantity_mismatch_count" in expect:
        expected = expect["quantity_mismatch_count"]
        actual = sum(1 for i in artifacts.ingest_issues if i.code == "quantity_mismatch")
        add("quantity_mismatch_count", actual == expected, f"expected {expected}, got {actual}")

    if "unresolved_min" in expect:
        expected_min = expect["unresolved_min"]
        add(
            "unresolved_min",
            unresolved_count >= expected_min,
            f"expected >= {expected_min}, got {unresolved_count}",
        )

    if "unresolved_max" in expect:
        expected_max = expect["unresolved_max"]
        add(
            "unresolved_max",
            unresolved_count <= expected_max,
            f"expected <= {expected_max}, got {unresolved_count}",
        )

    if "unresolved_field_counts" in expect:
        scores.extend(
            _score_exact_count_map(
                "unresolved_field_counts", expect["unresolved_field_counts"], unresolved_field_tally
            )
        )

    if "unresolved_field_counts_guaranteed" in expect:
        scores.extend(
            _score_min_count_map(
                "unresolved_field_counts_guaranteed",
                expect["unresolved_field_counts_guaranteed"],
                unresolved_field_tally,
            )
        )

    if "category_counts" in expect:
        scores.extend(
            _score_exact_count_map("category_counts", expect["category_counts"], category_tally)
        )

    if "category_counts_guaranteed" in expect:
        scores.extend(
            _score_min_count_map(
                "category_counts_guaranteed", expect["category_counts_guaranteed"], category_tally
            )
        )

    if "confidence_tier_counts" in expect:
        tier_tally: Counter[str] = Counter(
            confidence_tier(r.confidence.score) for r in artifacts.requirements
        )
        scores.extend(
            _score_exact_count_map(
                "confidence_tier_counts", expect["confidence_tier_counts"], tier_tally
            )
        )

    if "criticality_counts" in expect:
        criticality_tally = Counter(r.criticality.value for r in artifacts.requirements)
        scores.extend(
            _score_exact_count_map(
                "criticality_counts", expect["criticality_counts"], criticality_tally
            )
        )

    if "requirement_quantity_per_board" in expect:
        for key, expected_qty in expect["requirement_quantity_per_board"].items():
            requirement = _resolve_requirement(key, artifacts.requirements)
            field_name = f"requirement_quantity_per_board.{key}"
            if requirement is None:
                add(field_name, False, f"no requirement resolved for key {key!r}")
            else:
                add(
                    field_name,
                    requirement.quantity_per_board == expected_qty,
                    f"expected {expected_qty}, got {requirement.quantity_per_board} "
                    f"(resolved to {requirement.requirement_id})",
                )

    if "blocking_normalization_unresolved_count" in expect:
        expected = expect["blocking_normalization_unresolved_count"]
        actual = sum(
            1
            for i in artifacts.normalize_issues
            if i.severity == Severity.BLOCKING and i.code == "normalization_unresolved"
        )
        add(
            "blocking_normalization_unresolved_count",
            actual == expected,
            f"expected {expected}, got {actual}",
        )

    if "llm_fallback_unavailable_count" in expect:
        expected = expect["llm_fallback_unavailable_count"]
        actual = sum(1 for i in artifacts.normalize_issues if i.code == "llm_fallback_unavailable")
        add(
            "llm_fallback_unavailable_count",
            actual == expected,
            f"expected {expected}, got {actual}",
        )

    if "requirements_sourced" in expect:
        expected = expect["requirements_sourced"]
        add(
            "requirements_sourced",
            requirements_sourced == expected,
            f"expected {expected}, got {requirements_sourced}",
        )

    if "filled_at_tier_0_or_1_min" in expect:
        expected_min = expect["filled_at_tier_0_or_1_min"]
        actual = _count_requirements_filled_at_tiers(
            artifacts.policy_candidates or [], {SubstitutionTier.TIER_0, SubstitutionTier.TIER_1}
        )
        add(
            "filled_at_tier_0_or_1_min",
            actual >= expected_min,
            f"expected >= {expected_min}, got {actual}",
        )

    if "filled_at_tier_0_max" in expect:
        expected_max = expect["filled_at_tier_0_max"]
        actual = _count_requirements_filled_at_tiers(
            artifacts.policy_candidates or [], {SubstitutionTier.TIER_0}
        )
        add(
            "filled_at_tier_0_max",
            actual <= expected_max,
            f"expected <= {expected_max}, got {actual}",
        )

    if "tier0_candidates_total" in expect:
        expected = expect["tier0_candidates_total"]
        actual = sum(
            1
            for c in (artifacts.policy_candidates or [])
            if c.substitution_tier == SubstitutionTier.TIER_0
        )
        add("tier0_candidates_total", actual == expected, f"expected {expected}, got {actual}")

    if "evaluate_rationale_success_count" in expect:
        expected = expect["evaluate_rationale_success_count"]
        actual = sum(1 for c in (artifacts.evaluate_candidates or []) if c.rationale is not None)
        add(
            "evaluate_rationale_success_count",
            actual == expected,
            f"expected {expected}, got {actual}",
        )

    if "evaluate_blocking_count" in expect:
        expected = expect["evaluate_blocking_count"]
        actual = sum(
            1
            for i in artifacts.evaluate_issues
            if i.severity == Severity.BLOCKING and i.code == "candidate_rationale_llm_failed"
        )
        add("evaluate_blocking_count", actual == expected, f"expected {expected}, got {actual}")

    if "tier3_candidates_in_final_output" in expect:
        expected = expect["tier3_candidates_in_final_output"]
        actual = sum(
            1
            for c in (artifacts.evaluate_candidates or [])
            if c.substitution_tier == SubstitutionTier.TIER_3
        )
        add(
            "tier3_candidates_in_final_output",
            actual == expected,
            f"expected {expected}, got {actual}",
        )

    if "candidates_by_requirement" in expect:
        scores.extend(
            _score_candidates_by_requirement(
                expect["candidates_by_requirement"],
                artifacts.source_candidates or [],
                artifacts.policy_candidates or [],
            )
        )

    return scores


def _resolve_requirement(
    key: str, requirements: list[NormalizedRequirement]
) -> NormalizedRequirement | None:
    """Resolves an `expect` key to a requirement: literal `requirement_id` first,
    then a `req-<designator>-...-row` style key naming the row's first/last
    reference designator (see `requirement_quantity_per_board`'s only current user,
    `kicad_edge_cases_ingest_normalize/case.json`'s `req-r10-r12-row`)."""
    by_id = {r.requirement_id: r for r in requirements}
    if key in by_id:
        return by_id[key]
    if key.startswith("req-") and key.endswith("-row"):
        middle = key[len("req-") : -len("-row")]
        tokens = [t.upper() for t in middle.split("-") if t]
        if tokens:
            endpoints = {tokens[0], tokens[-1]}
            for requirement in requirements:
                designators = {d.upper() for d in requirement.reference_designators}
                if endpoints <= designators:
                    return requirement
    return None


def _count_requirements_filled_at_tiers(
    policy_candidates: list[PartCandidate], tiers: set[SubstitutionTier]
) -> int:
    by_requirement: dict[str, list[PartCandidate]] = defaultdict(list)
    for candidate in policy_candidates:
        by_requirement[candidate.requirement_id].append(candidate)
    return sum(
        1
        for candidates in by_requirement.values()
        if any(c.substitution_tier in tiers for c in candidates)
    )


def _score_exact_count_map(
    field_prefix: str, expected: dict[str, int], actual_tally: Counter[str]
) -> list[FieldScore]:
    scores = []
    keys = sorted(set(expected) | set(actual_tally))
    for key in keys:
        expected_count = expected.get(key, 0)
        actual_count = actual_tally.get(key, 0)
        scores.append(
            FieldScore(
                field=f"{field_prefix}.{key}",
                passed=actual_count == expected_count,
                detail=f"expected {expected_count}, got {actual_count}",
            )
        )
    return scores


def _score_min_count_map(
    field_prefix: str, expected: dict[str, int], actual_tally: Counter[str]
) -> list[FieldScore]:
    scores = []
    for key, expected_min in expected.items():
        actual_count = actual_tally.get(key, 0)
        scores.append(
            FieldScore(
                field=f"{field_prefix}.{key}",
                passed=actual_count >= expected_min,
                detail=f"expected >= {expected_min}, got {actual_count}",
            )
        )
    return scores


def _score_candidates_by_requirement(
    expected: dict[str, dict[str, Any]],
    source_candidates: list[PrePolicyCandidate],
    policy_candidates: list[PartCandidate],
) -> list[FieldScore]:
    scores: list[FieldScore] = []
    source_by_requirement: dict[str, list[PrePolicyCandidate]] = defaultdict(list)
    for source_candidate in source_candidates:
        source_by_requirement[source_candidate.requirement_id].append(source_candidate)
    policy_by_requirement: dict[str, list[PartCandidate]] = defaultdict(list)
    for policy_candidate in policy_candidates:
        policy_by_requirement[policy_candidate.requirement_id].append(policy_candidate)

    for requirement_id, spec in expected.items():
        prefix = f"candidates_by_requirement.{requirement_id}"
        req_source = source_by_requirement.get(requirement_id, [])
        req_policy = policy_by_requirement.get(requirement_id, [])
        tier3_failed_rules = {
            c.mpn: [r.rule_name for r in c.policy_results if not r.passed]
            for c in req_policy
            if c.substitution_tier == SubstitutionTier.TIER_3
        }
        policy_clean_count = sum(
            1 for c in req_policy if c.substitution_tier != SubstitutionTier.TIER_3
        )

        if "total" in spec:
            actual = len(req_source)
            scores.append(
                FieldScore(
                    f"{prefix}.total",
                    actual == spec["total"],
                    f"expected {spec['total']}, got {actual}",
                )
            )

        if "tier3_mpns" in spec:
            expected_map = spec["tier3_mpns"]
            missing = [
                mpn
                for mpn, rule in expected_map.items()
                if mpn not in tier3_failed_rules or rule not in tier3_failed_rules[mpn]
            ]
            extra = sorted(set(tier3_failed_rules) - set(expected_map))
            passed = not missing and not extra
            scores.append(
                FieldScore(
                    f"{prefix}.tier3_mpns",
                    passed,
                    f"expected exactly {expected_map}, got {tier3_failed_rules}"
                    + (f"; missing {missing}" if missing else "")
                    + (f"; unexpected extra tier-3 mpns {extra}" if extra else ""),
                )
            )

        if "tier3_mpns_if_present" in spec:
            expected_map = spec["tier3_mpns_if_present"]
            seen_mpns = {c.mpn for c in req_source}
            problems = [
                f"{mpn} present but not tier-3-rejected for rule {rule!r}"
                for mpn, rule in expected_map.items()
                if mpn in seen_mpns
                and (mpn not in tier3_failed_rules or rule not in tier3_failed_rules[mpn])
            ]
            scores.append(
                FieldScore(
                    f"{prefix}.tier3_mpns_if_present",
                    not problems,
                    "; ".join(problems) or "ok (present-and-rejected, or absent from candidates)",
                )
            )

        if "policy_clean_min" in spec:
            expected_min = spec["policy_clean_min"]
            scores.append(
                FieldScore(
                    f"{prefix}.policy_clean_min",
                    policy_clean_count >= expected_min,
                    f"expected >= {expected_min}, got {policy_clean_count}",
                )
            )

        if "policy_clean_max" in spec:
            expected_max = spec["policy_clean_max"]
            scores.append(
                FieldScore(
                    f"{prefix}.policy_clean_max",
                    policy_clean_count <= expected_max,
                    f"expected <= {expected_max}, got {policy_clean_count}",
                )
            )

    return scores
