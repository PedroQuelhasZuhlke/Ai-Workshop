"""SupplierOffer — a purchasable line from one supplier at one point in time."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from pcbpick.contracts.common import PriceBreak
from pcbpick.contracts.enums import Packaging, SupplierId
from pcbpick.contracts.version import SCHEMA_VERSION


class SupplierOffer(BaseModel):
    """One supplier's terms for one part as of a catalog snapshot. Re-validate before export."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    supplier: SupplierId
    sku: str
    packaging: Packaging
    stock: Annotated[int, Field(ge=0)] | None
    moq: Annotated[int, Field(gt=0)]
    spq: Annotated[int, Field(gt=0)]
    price_breaks: list[PriceBreak]
    lead_time_days: Annotated[int, Field(ge=0)] | None
    snapshot_id: str
    fetched_at: datetime
