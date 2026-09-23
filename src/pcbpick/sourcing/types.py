"""Sourcing-internal types: candidate search/detail/offer shapes.

Not versioned contracts — same status as `pcbpick.policy.candidate_input.PrePolicyCandidate`.
Candidate assembly (turning a `CatalogPart`/`CatalogSku` pair into a `PartCandidate`) is not
yet defined, so promoting these to `pcbpick.contracts` would be premature per
`.github/instructions/contracts.instructions.md`'s "only add a contract field when the value
must cross a stage boundary" guidance. These types cross an *adapter* boundary, not a
pipeline-stage boundary.

Modeled as frozen Pydantic models (`extra="forbid"`), matching the rest of the codebase's
artifact style and `PrePolicyCandidate`'s precedent — not the dataclass alternative, so that
`FixtureAdapter` (and any future adapter) can load snapshot JSON via `model_validate` instead
of hand-rolling field-by-field parsing.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from pcbpick.contracts.common import Footprint, MpnRef, ParameterValue, PriceBreak
from pcbpick.contracts.enums import ComplianceTag, ComponentCategory, Lifecycle, Packaging


class SourcingQuery(BaseModel):
    """A single requirement's ask, addressed to a `SupplierAdapter.search`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    category: ComponentCategory
    parameters: dict[str, ParameterValue]
    footprint: Footprint
    specified_mpn: MpnRef | None


class CatalogHit(BaseModel):
    """One search result: enough to decide whether to fetch full details."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mpn: str
    manufacturer: str
    sku: str


class CatalogSku(BaseModel):
    """One purchasable SKU/packaging variant of a catalog part.

    `stock`/`moq`/`spq`/`lead_time_days` are `None` when the supplier does not state them —
    never a stand-in number. `price_breaks` is ascending by quantity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sku: str
    packaging: Packaging
    stock: Annotated[int, Field(ge=0)] | None
    moq: Annotated[int, Field(gt=0)] | None
    spq: Annotated[int, Field(gt=0)] | None
    price_breaks: list[PriceBreak]
    lead_time_days: Annotated[int, Field(ge=0)] | None


class CatalogPart(BaseModel):
    """Full details for one manufacturer part, as returned by `SupplierAdapter.details`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mpn: str
    manufacturer: str
    category: ComponentCategory
    parameters: dict[str, ParameterValue]
    footprint: Footprint
    lifecycle: Lifecycle
    compliance: list[ComplianceTag]
    skus: list[CatalogSku]
    snapshot_id: str
    fetched_at: datetime
