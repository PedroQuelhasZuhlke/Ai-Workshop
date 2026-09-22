"""PurchasePlan — one complete way to buy the whole BOM under a given decision mode."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from pcbpick.contracts.common import CurrencyCode
from pcbpick.contracts.enums import DecisionMode, PlanWarningKind, SubstitutionTier, SupplierId
from pcbpick.contracts.version import SCHEMA_VERSION


class PlanLine(BaseModel):
    """One requirement resolved to a candidate, an offer, and an order quantity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    mpn: str
    manufacturer: str
    supplier: SupplierId
    sku: str
    substitution_tier: SubstitutionTier
    order_qty: Annotated[int, Field(gt=0)]
    unit_price: Annotated[Decimal, Field(ge=0)]
    extended_price: Annotated[Decimal, Field(ge=0)]
    currency: CurrencyCode
    snapshot_id: str


class PlanTotals(BaseModel):
    """Per-supplier subtotals, shipping, and the grand total for a plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: CurrencyCode
    supplier_subtotals: dict[SupplierId, Decimal]
    shipping_total: Annotated[Decimal, Field(ge=0)]
    grand_total: Annotated[Decimal, Field(ge=0)]


class UnfilledRequirement(BaseModel):
    """A requirement the plan could not fill, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: str
    reason: str


class PlanWarning(BaseModel):
    """A condition the engineer must see before approving a plan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: PlanWarningKind
    requirement_id: str | None
    message: str


class PurchasePlan(BaseModel):
    """One complete way to buy the whole BOM under a single decision mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    mode: DecisionMode
    board_quantity: Annotated[int, Field(gt=0)]
    attrition_pct: Annotated[Decimal, Field(ge=0)]
    lines: list[PlanLine]
    totals: PlanTotals
    longest_lead_time_days: Annotated[int, Field(ge=0)]
    supplier_count: Annotated[int, Field(ge=0)]
    unfilled: list[UnfilledRequirement]
    warnings: list[PlanWarning]
    snapshot_ids: list[str]
