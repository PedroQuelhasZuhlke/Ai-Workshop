"""SupplierExport — the final artifact, generated only from an approved plan."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from pcbpick.contracts.enums import ExportFormat, SupplierId
from pcbpick.contracts.version import SCHEMA_VERSION


class SupplierExport(BaseModel):
    """A supplier-ready import file, tied to the exact approved plan it was generated from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    supplier: SupplierId
    format: ExportFormat
    rows: list[dict[str, str]]
    approved_by: str
    approved_at: datetime
    plan_hash: str
