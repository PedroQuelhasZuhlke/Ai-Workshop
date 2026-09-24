"""Runs: upload -> mapping confirmation -> requirement resolution -> candidate
review -> plan comparison -> approval -> export.

Every read endpoint below depends on `require_role`, so project-scoped
authorization is checked on every artifact read, not just at upload — per
`docs/architecture.md`'s security posture and this milestone's scope.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from pcbpick.api import artifact_store, orchestrator
from pcbpick.api.auth import get_owned_run, get_session, require_role
from pcbpick.api.db import ApprovalRecord as ApprovalRecordModel
from pcbpick.api.db import ExportRecord, Run, User, latest_approval
from pcbpick.api.schemas import (
    ApprovalOut,
    ExportOut,
    ExportRequest,
    MappingConfirmRequest,
    ParameterPatch,
    PlanApproveRequest,
    PlanCreateRequest,
    RequirementResolveRequest,
    RunOut,
)
from pcbpick.api.settings import Settings, get_settings
from pcbpick.contracts.common import ParameterValue
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    DecisionMode,
    ExportFormat,
    MountingType,
    SupplierId,
    ValueSource,
)
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.errors import PcbPickError
from pcbpick.ingest.mapping_store import MappingProfileStore
from pcbpick.ingest.readers import MAX_FILE_SIZE_BYTES
from pcbpick.pipeline.results import Severity, StageIssue
from pcbpick.planning.plan_hash import compute_plan_hash

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])


def _run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        project_id=run.project_id,
        source_filename=run.source_filename,
        status=run.status,
        created_at=run.created_at,
        board_quantity=run.board_quantity,
    )


def _run_dir(settings: Settings, run_id: str) -> Path:
    return settings.runs_root / run_id


def _stage_now(settings: Settings) -> datetime:
    return settings.clock_override or datetime.now(UTC)


def _issue_dicts(issues: list[StageIssue]) -> list[dict[str, object]]:
    return [
        {"severity": i.severity.value, "code": i.code, "message": i.message, "item_id": i.item_id}
        for i in issues
    ]


def _mapping_profiles_root(settings: Settings) -> Path:
    # Matches `pcbpick.pipeline.runner.DEFAULT_MAPPING_PROFILES_ROOT` so a project's
    # confirmed mapping resolves the same way whether it came from the CLI or the API.
    return Path("mapping_profiles")


def _safe_upload_filename(filename: str | None) -> str:
    """Basename-only, rejecting path separators and `.`/`..` -- an `UploadFile.filename`
    is fully client-controlled and is later used as a path segment under `run_dir`."""
    name = Path(filename or "upload.csv").name
    if not name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid upload filename")
    return name


def _safe_project_id(project_id: str) -> str:
    """Defense-in-depth for `MappingProfileStore`, which keys files by `project_id`
    directly. `require_role` already guarantees `project_id` matches an existing
    project's membership before any handler body runs, but this keeps the guard
    local to `api/` rather than relying on that alone."""
    if "/" in project_id or "\\" in project_id or project_id in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid project id")
    return project_id


def _read_upload_within_limit(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413, detail=f"upload exceeds the {MAX_FILE_SIZE_BYTES}-byte limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=RunOut)
def upload_run(
    project_id: str,
    file: UploadFile,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_role("project_id", "engineer")),
) -> RunOut:
    filename = _safe_upload_filename(file.filename)
    content = _read_upload_within_limit(file)
    run_id = uuid4().hex
    now = datetime.now(UTC)
    project_mapping = MappingProfileStore(_mapping_profiles_root(settings)).load(
        _safe_project_id(project_id)
    )
    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))

    try:
        result = orchestrator.run_ingest(filename, content, project_mapping, ctx)
    except PcbPickError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run_dir = _run_dir(settings, run_id)
    artifact_store.save_ingest_result(run_dir, result.output, result.issues)
    # Retained so `confirm_mapping` can re-run `IngestStage` with the engineer's
    # corrected mapping -- the parsed `BomLine`s alone don't carry the original grid.
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / filename).write_bytes(content)

    run = Run(
        id=run_id,
        project_id=project_id,
        created_by=user.id,
        created_at=now,
        source_filename=filename,
        status="awaiting_mapping_confirmation",
    )
    session.add(run)
    session.commit()
    return _run_out(run)


@router.get("", response_model=list[RunOut])
def list_runs(
    project_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> list[RunOut]:
    runs = session.query(Run).filter_by(project_id=project_id).order_by(Run.created_at.desc()).all()
    return [_run_out(run) for run in runs]


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> RunOut:
    return _run_out(get_owned_run(run_id, project_id, session))


@router.get("/{run_id}/mapping")
def get_mapping(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> dict[str, object]:
    get_owned_run(run_id, project_id, session)
    ingest_result, issues = artifact_store.load_ingest_result(_run_dir(settings, run_id))
    return {
        "mapping_proposal": ingest_result.mapping_proposal.model_dump(mode="json"),
        "line_count": len(ingest_result.lines),
        "issues": _issue_dicts(issues),
    }


@router.post("/{run_id}/mapping/confirm", response_model=RunOut)
def confirm_mapping(
    project_id: str,
    run_id: str,
    body: MappingConfirmRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "engineer")),
) -> RunOut:
    run = get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)

    confirmed = {k: v for k, v in body.mappings.items() if v is not None}
    MappingProfileStore(_mapping_profiles_root(settings)).save(
        _safe_project_id(project_id), confirmed
    )

    source_path = run_dir / "source" / run.source_filename
    content = source_path.read_bytes()
    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))
    reingested = orchestrator.run_ingest(run.source_filename, content, confirmed, ctx)
    artifact_store.save_ingest_result(run_dir, reingested.output, reingested.issues)

    requirements_result = orchestrator.run_normalize(
        reingested.output, orchestrator.default_llm_client(), ctx
    )
    artifact_store.save_requirements(
        run_dir, requirements_result.output, requirements_result.issues
    )

    run.status = "normalized"
    session.add(run)
    session.commit()
    return _run_out(run)


@router.get("/{run_id}/requirements")
def get_requirements(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> dict[str, object]:
    get_owned_run(run_id, project_id, session)
    requirements, issues = artifact_store.load_requirements(_run_dir(settings, run_id))
    return {
        "requirements": [r.model_dump(mode="json") for r in requirements],
        "issues": _issue_dicts(issues),
    }


def _build_parameter_value(patch: ParameterPatch) -> ParameterValue:
    return ParameterValue(
        value=patch.value,
        unit=patch.unit,
        tolerance_pct=patch.tolerance_pct,
        min=patch.min,
        max=patch.max,
        raw_text=patch.raw_text,
        source=ValueSource.ENGINEER_ENTERED,
    )


def _recompute_unresolved_issues(
    requirements: list[NormalizedRequirement], existing_issues: list[StageIssue]
) -> list[StageIssue]:
    kept = [i for i in existing_issues if i.code != "normalization_unresolved"]
    for requirement in requirements:
        if requirement.unresolved:
            kept.append(
                StageIssue(
                    severity=Severity.BLOCKING,
                    code="normalization_unresolved",
                    message=(
                        f"requirement {requirement.requirement_id} has unresolved fields: "
                        f"{', '.join(requirement.unresolved)}"
                    ),
                    item_id=requirement.requirement_id,
                )
            )
    return kept


@router.post("/{run_id}/requirements/{requirement_id}/resolve")
def resolve_requirement_route(
    project_id: str,
    run_id: str,
    requirement_id: str,
    body: RequirementResolveRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "engineer")),
) -> dict[str, object]:
    get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    requirements, issues = artifact_store.load_requirements(run_dir)

    index = next(
        (i for i, r in enumerate(requirements) if r.requirement_id == requirement_id), None
    )
    if index is None:
        raise HTTPException(status_code=404, detail="requirement not found")
    requirement = requirements[index]

    parameters = {name: _build_parameter_value(patch) for name, patch in body.parameters.items()}
    try:
        footprint_updates = None
        if body.footprint is not None:
            raw = body.footprint.model_dump(exclude_none=True)
            if "mounting" in raw:
                raw["mounting"] = MountingType(raw["mounting"])
            footprint_updates = raw
        category = ComponentCategory(body.category) if body.category is not None else None
        compliance_required = (
            [ComplianceTag(tag) for tag in body.compliance_required]
            if body.compliance_required is not None
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    updated = orchestrator.resolve_requirement(
        requirement,
        parameters=parameters or None,
        footprint_updates=footprint_updates,
        category=category,
        compliance_required=compliance_required,
    )
    requirements[index] = updated
    issues = _recompute_unresolved_issues(requirements, issues)
    artifact_store.save_requirements(run_dir, requirements, issues)
    return {"requirement": updated.model_dump(mode="json")}


@router.post("/{run_id}/source")
def source_candidates(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "engineer")),
) -> dict[str, object]:
    run = get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    requirements, _ = artifact_store.load_requirements(run_dir)

    adapters = orchestrator.default_adapters(settings.catalog_snapshot_paths)
    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))
    chain_result = orchestrator.run_sourcing_chain(
        requirements, adapters, orchestrator.default_llm_client(), ctx
    )

    artifact_store.save_candidates(run_dir, chain_result.candidates, chain_result.issues)
    run.status = "sourced"
    session.add(run)
    session.commit()
    return {
        "candidates": [c.model_dump(mode="json") for c in chain_result.candidates],
        "issues": _issue_dicts(chain_result.issues),
        "excluded_requirement_ids": chain_result.excluded_requirement_ids,
    }


@router.get("/{run_id}/candidates")
def get_candidates(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> dict[str, object]:
    get_owned_run(run_id, project_id, session)
    candidates, issues = artifact_store.load_candidates(_run_dir(settings, run_id))
    return {
        "candidates": [c.model_dump(mode="json") for c in candidates],
        "issues": _issue_dicts(issues),
    }


@router.post("/{run_id}/plans")
def create_plans(
    project_id: str,
    run_id: str,
    body: PlanCreateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "engineer")),
) -> dict[str, object]:
    run = get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    requirements, _ = artifact_store.load_requirements(run_dir)
    candidates, _ = artifact_store.load_candidates(run_dir)
    requirements_by_id = {r.requirement_id: r for r in requirements}

    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))
    result = orchestrator.run_planning(requirements_by_id, candidates, body.board_quantity, ctx)

    artifact_store.save_plans(run_dir, result.output, body.board_quantity, result.issues)
    run.status = "planned"
    run.board_quantity = body.board_quantity
    session.add(run)
    session.commit()
    return {
        "plans": [p.model_dump(mode="json") for p in result.output],
        "issues": _issue_dicts(result.issues),
    }


@router.get("/{run_id}/plans")
def get_plans(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> dict[str, object]:
    get_owned_run(run_id, project_id, session)
    plans, board_quantity, issues = artifact_store.load_plans(_run_dir(settings, run_id))
    return {
        "plans": [p.model_dump(mode="json") for p in plans],
        "board_quantity": board_quantity,
        "issues": _issue_dicts(issues),
    }


@router.post("/{run_id}/plans/{mode}/revalidate")
def revalidate_plans(
    project_id: str,
    run_id: str,
    mode: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    _user: User = Depends(require_role("project_id", "engineer")),
) -> dict[str, object]:
    """One-click re-validation: re-runs `source -> policy -> evaluate -> plan`
    against `ctx.now` at the moment of the call, refreshing stale-offer detection.

    With `FixtureAdapter`, the underlying offer data itself is pinned and does not
    change between calls -- only the freshness comparison against the new `ctx.now`
    does. A live adapter re-fetching current price/stock on every call is M7 scope.
    """
    del mode  # re-validates every mode; the caller re-fetches its plan afterward
    run = get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    requirements, _ = artifact_store.load_requirements(run_dir)
    _, board_quantity, _ = artifact_store.load_plans(run_dir)

    adapters = orchestrator.default_adapters(settings.catalog_snapshot_paths)
    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))
    chain_result = orchestrator.run_sourcing_chain(
        requirements, adapters, orchestrator.default_llm_client(), ctx
    )
    artifact_store.save_candidates(run_dir, chain_result.candidates, chain_result.issues)

    requirements_by_id = {r.requirement_id: r for r in requirements}
    plan_result = orchestrator.run_planning(
        requirements_by_id, chain_result.candidates, board_quantity, ctx
    )
    artifact_store.save_plans(run_dir, plan_result.output, board_quantity, plan_result.issues)
    session.add(run)
    session.commit()
    return {
        "plans": [p.model_dump(mode="json") for p in plan_result.output],
        "issues": _issue_dicts(plan_result.issues),
    }


def _find_plan(run_dir: Path, mode: str) -> PurchasePlan:
    plans, _, _ = artifact_store.load_plans(run_dir)
    try:
        decision_mode = DecisionMode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown decision mode {mode!r}") from exc
    plan = next((p for p in plans if p.mode == decision_mode), None)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"no plan for decision mode {mode!r}")
    return plan


@router.post("/{run_id}/plans/{mode}/approve", response_model=ApprovalOut)
def approve_plan(
    project_id: str,
    run_id: str,
    mode: str,
    body: PlanApproveRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_role("project_id", "engineer")),
) -> ApprovalOut:
    get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    plan = _find_plan(run_dir, mode)

    record = ApprovalRecordModel(
        run_id=run_id,
        decision_mode=mode,
        plan_hash=compute_plan_hash(plan),
        approved_by=user.id,
        approved_at=datetime.now(UTC),
        reviewed_high_tier_requirement_ids=json.dumps(
            sorted(body.reviewed_high_tier_requirement_ids)
        ),
        acknowledged_stale_offer_snapshot_ids=json.dumps(
            sorted(body.acknowledged_stale_offer_snapshot_ids)
        ),
        note=body.note,
    )
    session.add(record)
    session.commit()
    return ApprovalOut(
        id=record.id,
        run_id=record.run_id,
        decision_mode=record.decision_mode,
        plan_hash=record.plan_hash,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        reviewed_high_tier_requirement_ids=json.loads(record.reviewed_high_tier_requirement_ids),
        acknowledged_stale_offer_snapshot_ids=json.loads(
            record.acknowledged_stale_offer_snapshot_ids
        ),
        note=record.note,
    )


@router.get("/{run_id}/approvals", response_model=list[ApprovalOut])
def list_approvals(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> list[ApprovalOut]:
    get_owned_run(run_id, project_id, session)
    records = (
        session.query(ApprovalRecordModel)
        .filter_by(run_id=run_id)
        .order_by(ApprovalRecordModel.approved_at.desc())
        .all()
    )
    return [
        ApprovalOut(
            id=r.id,
            run_id=r.run_id,
            decision_mode=r.decision_mode,
            plan_hash=r.plan_hash,
            approved_by=r.approved_by,
            approved_at=r.approved_at,
            reviewed_high_tier_requirement_ids=json.loads(r.reviewed_high_tier_requirement_ids),
            acknowledged_stale_offer_snapshot_ids=json.loads(
                r.acknowledged_stale_offer_snapshot_ids
            ),
            note=r.note,
        )
        for r in records
    ]


@router.post("/{run_id}/plans/{mode}/export", response_model=ExportOut)
def export_plan(
    project_id: str,
    run_id: str,
    mode: str,
    body: ExportRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_role("project_id", "engineer")),
) -> ExportOut:
    get_owned_run(run_id, project_id, session)
    run_dir = _run_dir(settings, run_id)
    plan = _find_plan(run_dir, mode)

    approval = latest_approval(session, run_id, mode)
    if approval is None:
        raise HTTPException(
            status_code=409, detail=f"plan for decision mode {mode!r} has no recorded approval"
        )
    current_hash = compute_plan_hash(plan)
    if approval.plan_hash != current_hash:
        # The plan changed (e.g. a re-validation) since this approval was recorded --
        # invariant 6 requires an approval of *this exact plan*, not a stale one.
        raise HTTPException(
            status_code=409,
            detail=(
                "the approved plan hash does not match the current plan; "
                "re-approve before exporting"
            ),
        )

    ctx = orchestrator.make_stage_context(run_id, _stage_now(settings))
    result = orchestrator.run_export(
        plan,
        SupplierId(body.supplier),
        ExportFormat(body.format),
        approval.approved_by,
        approval.approved_at,
        frozenset(json.loads(approval.acknowledged_stale_offer_snapshot_ids)),
        frozenset(json.loads(approval.reviewed_high_tier_requirement_ids)),
        ctx,
    )
    if result.output is None:
        raise HTTPException(
            status_code=422,
            detail=[{"code": i.code, "message": i.message} for i in result.issues],
        )

    export_id = uuid4().hex
    artifact_store.save_export(run_dir, export_id, result.output)
    record = ExportRecord(
        id=export_id,
        run_id=run_id,
        approval_id=approval.id,
        supplier=body.supplier,
        format=body.format,
        plan_hash=current_hash,
        exported_by=user.id,
        exported_at=datetime.now(UTC),
        file_path=str(run_dir / "exports" / f"{export_id}.{body.format}"),
    )
    session.add(record)
    session.commit()
    return ExportOut(
        id=record.id,
        run_id=record.run_id,
        supplier=record.supplier,
        format=record.format,
        plan_hash=record.plan_hash,
        exported_by=record.exported_by,
        exported_at=record.exported_at,
        download_url=f"/projects/{project_id}/runs/{run_id}/exports/{export_id}/download",
    )


@router.get("/{run_id}/exports", response_model=list[ExportOut])
def list_exports(
    project_id: str,
    run_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> list[ExportOut]:
    get_owned_run(run_id, project_id, session)
    records = (
        session.query(ExportRecord)
        .filter_by(run_id=run_id)
        .order_by(ExportRecord.exported_at.desc())
        .all()
    )
    return [
        ExportOut(
            id=r.id,
            run_id=r.run_id,
            supplier=r.supplier,
            format=r.format,
            plan_hash=r.plan_hash,
            exported_by=r.exported_by,
            exported_at=r.exported_at,
            download_url=f"/projects/{project_id}/runs/{run_id}/exports/{r.id}/download",
        )
        for r in records
    ]


@router.get("/{run_id}/exports/{export_id}/download")
def download_export(
    project_id: str,
    run_id: str,
    export_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("project_id", "viewer")),
) -> FileResponse:
    get_owned_run(run_id, project_id, session)
    record = session.get(ExportRecord, export_id)
    if record is None or record.run_id != run_id:
        raise HTTPException(status_code=404, detail="export not found")
    path = Path(record.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="export file missing on disk")
    media_type = (
        "text/csv"
        if record.format == "csv"
        else ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    )
    return FileResponse(path, media_type=media_type, filename=path.name)
