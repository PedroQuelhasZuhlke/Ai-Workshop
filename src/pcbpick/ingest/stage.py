"""The `ingest` pipeline stage: turns raw BOM file bytes into `IngestResult`.

Purity note: the only I/O this stage performs is decoding bytes already handed to it
by the runner (see `pcbpick.ingest.readers`) — no disk access, no clock, no
randomness. The runner reads the source file and any persisted project mapping
*before* calling `run`.
"""

from dataclasses import dataclass

from pcbpick.contracts.bom import BomLine
from pcbpick.contracts.enums import MappingMethod
from pcbpick.contracts.mapping import ColumnMapping, IngestResult, MappingProposal
from pcbpick.ingest.header import find_header_row
from pcbpick.ingest.mapping import (
    HEURISTIC_CONFIDENCE_UNIQUE,
    ResolvedColumn,
    resolve_column_mapping,
)
from pcbpick.ingest.profiles import match_eda_profile
from pcbpick.ingest.quantity import has_quantity_mismatch, parse_quantity
from pcbpick.ingest.readers import read_grid
from pcbpick.ingest.refdes import expand_reference_designators, find_duplicate_designators
from pcbpick.ingest.synonyms import REQUIRED_BOM_LINE_TARGETS
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult

# Do-not-populate markers trusted verbatim wherever they appear, per the bom-ingest
# skill's DNP detection step — checked case-insensitively against a whole cell.
_DNP_MARKERS = frozenset(
    {
        "dnp",
        "dni",
        "nf",
        "np",
        "do not populate",
        "do not install",
        "not fitted",
        "unfitted",
        "no load",
    }
)

# A row with fewer than this many populated cells is treated as a spacer or a
# trailing notes/title-block row, not a component line — see readme note in
# `.github/skills/bom-ingest/SKILL.md` on trailing notes rows breaking the read.
_MIN_POPULATED_CELLS_FOR_DATA_ROW = 2


@dataclass(frozen=True)
class IngestInput:
    """What the runner hands the ingest stage: bytes already read from disk."""

    file_name: str
    content: bytes
    project_mapping: dict[str, str] | None = None


class IngestStage:
    """Reads a BOM export and emits `BomLine`s plus the mapping proposal that produced them."""

    name = "ingest"

    def run(self, inp: IngestInput, ctx: StageContext) -> StageResult[IngestResult]:
        del ctx  # ingest needs no clock or randomness
        grid = read_grid(inp.file_name, inp.content)
        header_row_index = find_header_row(grid)
        headers = grid[header_row_index]
        header_to_index = {header: index for index, header in enumerate(headers)}

        profile_match = match_eda_profile(headers)
        eda_profile = profile_match[0] if profile_match else None
        eda_profile_name = eda_profile.name if eda_profile else None
        mapping_profile_label = eda_profile_name or "unknown"

        resolved = resolve_column_mapping(headers, eda_profile, inp.project_mapping)
        resolved_by_target = {column.target_field: column for column in resolved}

        lines: list[BomLine] = []
        issues: list[StageIssue] = []
        row_index = 0
        for row in grid[header_row_index + 1 :]:
            if not _looks_like_data_row(row):
                continue
            line, row_issues = _build_bom_line(
                row_index=row_index,
                row=row,
                headers=headers,
                header_to_index=header_to_index,
                resolved_by_target=resolved_by_target,
                source_file=inp.file_name,
                mapping_profile=mapping_profile_label,
            )
            lines.append(line)
            issues.extend(row_issues)
            row_index += 1

        duplicates = find_duplicate_designators([line.reference_designators for line in lines])
        if duplicates:
            issues.append(
                StageIssue(
                    severity=Severity.BLOCKING,
                    code="duplicate_reference_designator",
                    message=f"designators appear on more than one line: {', '.join(duplicates)}",
                )
            )

        proposal = _build_mapping_proposal(
            inp.file_name, eda_profile_name, header_row_index, headers, resolved
        )
        if proposal.requires_confirmation:
            missing = ", ".join(proposal.missing_required_fields) or "none - low confidence"
            issues.append(
                StageIssue(
                    severity=Severity.BLOCKING,
                    code="mapping_requires_confirmation",
                    message=(
                        f"column mapping for {inp.file_name} needs engineer confirmation "
                        f"(missing: {missing})"
                    ),
                )
            )

        return StageResult(
            output=IngestResult(lines=lines, mapping_proposal=proposal), issues=issues
        )


def _looks_like_data_row(row: list[str]) -> bool:
    return sum(1 for cell in row if cell.strip()) >= _MIN_POPULATED_CELLS_FOR_DATA_ROW


def _build_bom_line(
    *,
    row_index: int,
    row: list[str],
    headers: list[str],
    header_to_index: dict[str, int],
    resolved_by_target: dict[str, ResolvedColumn],
    source_file: str,
    mapping_profile: str,
) -> tuple[BomLine, list[StageIssue]]:
    raw = {
        header: (row[index] if index < len(row) else "")
        for header, index in header_to_index.items()
    }

    refdes_column = resolved_by_target["reference_designators"].source_column
    refdes_raw = raw.get(refdes_column, "") if refdes_column else ""
    designators, range_errors = expand_reference_designators(refdes_raw)

    quantity_column = resolved_by_target["quantity"].source_column
    stated_quantity = parse_quantity(raw.get(quantity_column)) if quantity_column else None

    populate = _is_populated(row, header_to_index, resolved_by_target["populate"].source_column)

    issues: list[StageIssue] = []
    for error in range_errors:
        issues.append(
            StageIssue(
                severity=Severity.WARNING,
                code="invalid_refdes_range",
                message=error,
                item_id=f"row-{row_index}",
            )
        )
    if has_quantity_mismatch(stated_quantity, designators):
        issues.append(
            StageIssue(
                severity=Severity.WARNING,
                code="quantity_mismatch",
                message=(
                    f"stated quantity {stated_quantity} disagrees with "
                    f"{len(designators)} reference designator(s)"
                ),
                item_id=f"row-{row_index}",
            )
        )

    line = BomLine(
        row_index=row_index,
        raw=raw,
        reference_designators=designators,
        quantity=stated_quantity,
        source_file=source_file,
        mapping_profile=mapping_profile,
        populate=populate,
    )
    return line, issues


def _is_populated(row: list[str], header_to_index: dict[str, int], dnp_column: str | None) -> bool:
    if dnp_column is not None:
        index = header_to_index[dnp_column]
        cell = row[index] if index < len(row) else ""
        if cell.strip():
            return False
    return not any(cell.strip().lower() in _DNP_MARKERS for cell in row)


def _build_mapping_proposal(
    file_name: str,
    eda_profile_name: str | None,
    header_row_index: int,
    headers: list[str],
    resolved: list[ResolvedColumn],
) -> MappingProposal:
    mappings = [
        ColumnMapping(
            target_field=column.target_field,
            source_column=column.source_column,
            method=column.method,
            confidence=column.confidence,
        )
        for column in resolved
    ]
    used_columns = {column.source_column for column in resolved if column.source_column}
    unmapped_columns = [header for header in headers if header not in used_columns]
    missing_required_fields = [
        column.target_field
        for column in resolved
        if column.target_field in REQUIRED_BOM_LINE_TARGETS
        and column.method == MappingMethod.UNRESOLVED
    ]
    requires_confirmation = bool(missing_required_fields) or any(
        column.method != MappingMethod.UNRESOLVED
        and column.confidence < HEURISTIC_CONFIDENCE_UNIQUE
        for column in resolved
    )
    return MappingProposal(
        source_file=file_name,
        eda_profile=eda_profile_name,
        header_row_index=header_row_index,
        mappings=mappings,
        unmapped_columns=unmapped_columns,
        missing_required_fields=missing_required_fields,
        requires_confirmation=requires_confirmation,
    )
