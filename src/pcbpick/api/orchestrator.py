"""Glue between the API layer and the existing pipeline stage classes.

Not a pipeline stage itself. The interactive upload -> mapping confirmation ->
requirement resolution -> candidate review -> plan comparison -> approval -> export
flow needs engineer input *between* stages, which the batch `PipelineRunner`
(`src/pcbpick/pipeline/runner.py`) isn't built for yet — it registers only
`ingest`+`normalize` today. This module calls each stage class directly, in the same
order `docs/architecture.md`'s stage table defines (`ingest -> normalize -> expand ->
source -> policy -> evaluate -> plan -> export`; there is no separate `resolve` stage
built yet, per `docs/decision-log.md` section 15/16 — offers are attached during
`source`/`policy` already), and returns each stage's `StageResult` unchanged for the
router layer to persist via `api.artifact_store`.

No stage class in here is modified. `resolve_requirement` is API-side merge logic —
it reuses `classify.router.missing_required_parameters`, the same pure function
`normalize` itself uses, rather than duplicating category rules.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random

from pcbpick.classify.router import missing_required_parameters
from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import ParameterValue
from pcbpick.contracts.enums import ComplianceTag, ComponentCategory, ExportFormat, SupplierId
from pcbpick.contracts.mapping import IngestResult
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.exporters.stage import ExportedFile, ExportStage, ExportStageInput
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.llm.client import LLMClient
from pcbpick.normalize.stage import NormalizeStage
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import StageIssue, StageResult
from pcbpick.planning.stage import PlanningStage, PlanningStageInput
from pcbpick.policy.stage import PolicyStage, PolicyStageInput
from pcbpick.sourcing.evaluate import EvaluateStage, EvaluateStageInput
from pcbpick.sourcing.expand import ExpandStage
from pcbpick.sourcing.stage import SourceStage
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.suppliers.protocol import SupplierAdapter


def make_stage_context(run_id: str, now: datetime) -> StageContext:
    return StageContext(run_id=run_id, now=now, rng=Random(run_id), config=PipelineConfig())


def default_adapters(catalog_snapshot_paths: tuple[str, ...]) -> list[SupplierAdapter]:
    """Fixture-only, matching M4/M5's fixtures-first precedent. Live adapters are M7."""
    return [FixtureAdapter([Path(p) for p in catalog_snapshot_paths])]


def run_ingest(
    file_name: str,
    content: bytes,
    project_mapping: dict[str, str] | None,
    ctx: StageContext,
) -> StageResult[IngestResult]:
    return IngestStage().run(
        IngestInput(file_name=file_name, content=content, project_mapping=project_mapping), ctx
    )


def run_normalize(
    ingest_result: IngestResult, llm_client: LLMClient | None, ctx: StageContext
) -> StageResult[list[NormalizedRequirement]]:
    return NormalizeStage(llm_client=llm_client).run(ingest_result, ctx)


def resolve_requirement(
    requirement: NormalizedRequirement,
    *,
    parameters: dict[str, ParameterValue] | None = None,
    footprint_updates: dict[str, object] | None = None,
    category: ComponentCategory | None = None,
    compliance_required: list[ComplianceTag] | None = None,
) -> NormalizedRequirement:
    """Merge engineer-entered values into a requirement and recompute `unresolved`.

    Every merged `ParameterValue` must already carry `source=ValueSource.ENGINEER_ENTERED`
    (enforced by the router that builds them) — this function never invents that tag.
    """
    new_parameters = {**requirement.parameters, **(parameters or {})}
    new_category = category if category is not None else requirement.category
    new_footprint = (
        requirement.footprint.model_copy(update=footprint_updates)
        if footprint_updates
        else requirement.footprint
    )
    new_compliance = (
        compliance_required if compliance_required is not None else requirement.compliance_required
    )

    unresolved = set(requirement.unresolved)
    if category is not None:
        unresolved.discard("category")
    if footprint_updates:
        unresolved = {u for u in unresolved if not u.startswith("footprint.")}
    if compliance_required is not None:
        unresolved.discard("compliance_required")
    unresolved = {u for u in unresolved if not u.startswith("parameters.")}
    unresolved.update(missing_required_parameters(new_category, new_parameters))

    return requirement.model_copy(
        update={
            "category": new_category,
            "parameters": new_parameters,
            "footprint": new_footprint,
            "compliance_required": new_compliance,
            "unresolved": sorted(unresolved),
        }
    )


@dataclass(frozen=True)
class SourcingChainResult:
    candidates: list[PartCandidate]
    issues: list[StageIssue]
    excluded_requirement_ids: list[str]


def run_sourcing_chain(
    requirements: list[NormalizedRequirement],
    adapters: list[SupplierAdapter],
    llm_client: LLMClient | None,
    ctx: StageContext,
) -> SourcingChainResult:
    """`expand -> source -> policy -> evaluate`, per `docs/architecture.md`'s stage table."""
    ready = [r for r in requirements if not r.unresolved]
    excluded = [r.requirement_id for r in requirements if r.unresolved]
    req_by_id = {r.requirement_id: r for r in ready}

    expand_result = ExpandStage().run(ready, ctx)
    source_result = SourceStage(adapters).run(expand_result.output, ctx)

    policy_pairs = [
        (req_by_id[c.requirement_id], c)
        for c in source_result.output
        if c.requirement_id in req_by_id
    ]
    policy_result = PolicyStage().run(PolicyStageInput(pairs=policy_pairs), ctx)

    evaluate_pairs = [(req_by_id[c.requirement_id], c) for c in policy_result.output]
    evaluate_result = EvaluateStage(llm_client=llm_client).run(
        EvaluateStageInput(pairs=evaluate_pairs), ctx
    )

    combined_issues = [
        *expand_result.issues,
        *source_result.issues,
        *policy_result.issues,
        *evaluate_result.issues,
    ]
    return SourcingChainResult(
        candidates=evaluate_result.output,
        issues=combined_issues,
        excluded_requirement_ids=sorted(excluded),
    )


def run_planning(
    requirements_by_id: dict[str, NormalizedRequirement],
    candidates: list[PartCandidate],
    board_quantity: int,
    ctx: StageContext,
) -> StageResult[list[PurchasePlan]]:
    pairs = [
        (requirements_by_id[c.requirement_id], c)
        for c in candidates
        if c.requirement_id in requirements_by_id
    ]
    return PlanningStage().run(PlanningStageInput(pairs=pairs, board_quantity=board_quantity), ctx)


def run_export(
    plan: PurchasePlan,
    supplier: SupplierId,
    export_format: ExportFormat,
    approved_by: str,
    approved_at: datetime,
    stale_offer_snapshot_ids: frozenset[str],
    reviewed_high_tier_requirement_ids: frozenset[str],
    ctx: StageContext,
) -> StageResult[ExportedFile | None]:
    return ExportStage().run(
        ExportStageInput(
            plan=plan,
            supplier=supplier,
            format=export_format,
            approved_by=approved_by,
            approved_at=approved_at,
            stale_offer_snapshot_ids=stale_offer_snapshot_ids,
            reviewed_high_tier_requirement_ids=reviewed_high_tier_requirement_ids,
        ),
        ctx,
    )
