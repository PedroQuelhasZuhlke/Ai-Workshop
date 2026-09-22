"""BomLine — a faithful, uncleaned representation of one BOM row."""

from pydantic import BaseModel, ConfigDict

from pcbpick.contracts.version import SCHEMA_VERSION


class BomLine(BaseModel):
    """One row exactly as it appeared in the source file. Never cleaned — the audit anchor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    row_index: int
    raw: dict[str, str]
    reference_designators: list[str]
    quantity: int | None
    source_file: str
    mapping_profile: str
