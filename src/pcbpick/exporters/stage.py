"""The `export` pipeline stage: turns an approved `PurchasePlan` into a supplier-ready
import file. The last, strictest stage -- see
`.github/skills/supplier-export/SKILL.md`. Every gate in `validation.py` runs before
any row is written; a failure aborts with `BLOCKING` issues and no output, never a
partial file.

Purity note: no I/O, no clock, no RNG. `approved_at` always comes from
`ExportStageInput.approved_at`, the real recorded approval time -- `ctx.now` is never
substituted for it.
"""

from dataclasses import dataclass, field
from datetime import datetime

from pcbpick.contracts.enums import ExportFormat, PlanWarningKind, SupplierId
from pcbpick.contracts.export import SupplierExport
from pcbpick.contracts.plan import PlanLine, PurchasePlan
from pcbpick.errors import ContractViolationError
from pcbpick.exporters.csv_writer import write_csv
from pcbpick.exporters.templates_io import load_template
from pcbpick.exporters.validation import validate_for_export
from pcbpick.exporters.xlsx_writer import write_xlsx
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult
from pcbpick.planning.plan_hash import compute_plan_hash


@dataclass(frozen=True)
class ExportStageInput:
    """One supplier's export request against one plan, plus the recorded approval and
    the caller's review determinations for the validation gates.

    `stale_offer_snapshot_ids` is the engineer's acknowledged-override set from the
    approval record (`api/db.py`'s `ApprovalRecord.acknowledged_stale_offer_snapshot_ids`).
    Despite its name (kept for compatibility with the already-shipped API/DB/web
    layers), it is matched against `PlanLine.requirement_id`, not `snapshot_id` --
    see `exporters.validation.check_no_stale_offers`'s docstring for why. Its empty
    default means no override is granted: every `PlanWarningKind.STALE_OFFER`
    warning on the plan still blocks export unless its requirement is explicitly
    acknowledged here."""

    plan: PurchasePlan
    supplier: SupplierId
    format: ExportFormat
    approved_by: str
    approved_at: datetime
    stale_offer_snapshot_ids: frozenset[str] = field(default_factory=frozenset)
    reviewed_high_tier_requirement_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ExportedFile:
    """The structured artifact plus the actual downloadable file bytes -- `rows` on
    `SupplierExport` is typed `list[dict[str, str]]`, not raw file bytes, so both are
    surfaced separately to the caller."""

    export: SupplierExport
    file_bytes: bytes


def _row_for_line(supplier: SupplierId, line: PlanLine) -> dict[str, str]:
    match supplier:
        case SupplierId.MOUSER:
            return {
                "Mouser Part Number": line.sku,
                "Manufacturer Part Number": line.mpn,
                "Quantity": str(line.order_qty),
                "Customer Part Number": line.requirement_id,
            }
        case SupplierId.DIGIKEY:
            return {
                "Digi-Key Part Number": line.sku,
                "Manufacturer Part Number": line.mpn,
                "Quantity": str(line.order_qty),
                "Customer Reference": line.requirement_id,
            }
        case SupplierId.FIXTURE:
            raise ContractViolationError("fixture is not a real export destination")


def _acknowledged_stale_issues(inp: ExportStageInput) -> list[StageIssue]:
    """One `INFO` issue per stale-offer requirement this export actually relied on
    the engineer's acknowledgment to pass -- `validate_for_export` already blocked
    every *unacknowledged* one, so every id here reached export on an explicit,
    recorded override rather than silently."""
    stale_requirement_ids = {
        warning.requirement_id
        for warning in inp.plan.warnings
        if warning.kind == PlanWarningKind.STALE_OFFER and warning.requirement_id is not None
    }
    overridden = sorted(stale_requirement_ids & inp.stale_offer_snapshot_ids)
    return [
        StageIssue(
            severity=Severity.INFO,
            code="exported_with_acknowledged_stale_offer",
            message=(
                f"requirement {requirement_id} had a stale offer; exported anyway on "
                f"{inp.approved_by}'s acknowledged override from the approval record"
            ),
            item_id=requirement_id,
        )
        for requirement_id in overridden
    ]


class ExportStage:
    """Generates one supplier's import file from an approved, validated `PurchasePlan`."""

    name = "export"

    def run(self, inp: ExportStageInput, ctx: StageContext) -> StageResult[ExportedFile | None]:
        del ctx  # export needs no clock or randomness; approved_at is the caller's

        failures = validate_for_export(
            inp.plan,
            inp.approved_by,
            inp.approved_at,
            inp.stale_offer_snapshot_ids,
            inp.reviewed_high_tier_requirement_ids,
        )
        if failures:
            issues = [
                StageIssue(
                    severity=Severity.BLOCKING, code="export_validation_failed", message=reason
                )
                for reason in failures
            ]
            return StageResult(output=None, issues=issues)

        template = load_template(inp.supplier)
        selected_lines = sorted(
            (line for line in inp.plan.lines if line.supplier == inp.supplier),
            key=lambda line: line.requirement_id,
        )
        rows = [_row_for_line(inp.supplier, line) for line in selected_lines]

        if inp.format == ExportFormat.CSV:
            file_bytes = write_csv(rows, template.columns)
        else:
            file_bytes = write_xlsx(rows, template.columns)

        export = SupplierExport(
            supplier=inp.supplier,
            format=inp.format,
            rows=rows,
            approved_by=inp.approved_by,
            approved_at=inp.approved_at,
            plan_hash=compute_plan_hash(inp.plan),
        )
        issues = [
            StageIssue(
                severity=Severity.INFO,
                code="export_template_version",
                message=(
                    f"export stage used {inp.supplier.value} template version "
                    f"{template.version} ({template.verified_date})"
                ),
            )
        ]
        issues.extend(_acknowledged_stale_issues(inp))
        return StageResult(output=ExportedFile(export=export, file_bytes=file_bytes), issues=issues)
