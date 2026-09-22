"""Column mapping artifacts — how source BOM columns were resolved to `BomLine` fields.

Never guess: a low-confidence or absent mapping is recorded as `unresolved`, and the
`MappingProposal` is always surfaced for engineer confirmation regardless of which
tier produced it.
"""

from pydantic import BaseModel, ConfigDict, Field

from pcbpick.contracts.bom import BomLine
from pcbpick.contracts.enums import MappingMethod
from pcbpick.contracts.version import SCHEMA_VERSION


class ColumnMapping(BaseModel):
    """One target field resolved (or not) to a source column, and how."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_field: str
    source_column: str | None
    method: MappingMethod
    confidence: float = Field(ge=0.0, le=1.0)


class MappingProposal(BaseModel):
    """The column mapping resolved for one source file, always surfaced for confirmation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    source_file: str
    eda_profile: str | None
    header_row_index: int
    mappings: list[ColumnMapping]
    unmapped_columns: list[str]
    missing_required_fields: list[str]
    requires_confirmation: bool


class IngestResult(BaseModel):
    """What the `ingest` stage emits: every source row plus the mapping that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    lines: list[BomLine]
    mapping_proposal: MappingProposal
