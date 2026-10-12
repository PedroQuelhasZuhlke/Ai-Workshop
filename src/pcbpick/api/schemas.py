"""API request/response models. Distinct from `pcbpick.contracts` — these describe the
HTTP surface, not persisted pipeline artifacts, and are not versioned the same way."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    role: str


class MemberAddRequest(BaseModel):
    user_id: str
    role: str = Field(pattern="^(viewer|engineer|owner)$")


class DevUserCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class DevUserOut(BaseModel):
    id: str
    display_name: str
    api_key: str
    recovery_code: str


class RecoverRequest(BaseModel):
    recovery_code: str = Field(min_length=1, max_length=200)


class RunOut(BaseModel):
    id: str
    project_id: str
    source_filename: str
    status: str
    created_at: datetime
    board_quantity: int | None = None


class MappingConfirmRequest(BaseModel):
    """Engineer-confirmed target_field -> source_column resolution. A `null` value
    means the field is intentionally left unmapped (e.g. no MPN column in the file)."""

    mappings: dict[str, str | None]


class ParameterPatch(BaseModel):
    """One engineer-entered parameter value, tagged `ValueSource.ENGINEER_ENTERED`
    downstream — never accepted as a substitute for `source: parsed`."""

    model_config = ConfigDict(extra="forbid")

    value: Decimal | None = None
    unit: str = ""
    tolerance_pct: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None
    raw_text: str


class FootprintPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_code: str | None = None
    mounting: str | None = None
    pin_count: int | None = None
    pitch_mm: Decimal | None = None
    length_mm: Decimal | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    thermal_pad: bool | None = None


class RequirementResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = None
    parameters: dict[str, ParameterPatch] = Field(default_factory=dict)
    footprint: FootprintPatch | None = None
    compliance_required: list[str] | None = None


class PlanCreateRequest(BaseModel):
    board_quantity: int = Field(gt=0)


class PlanApproveRequest(BaseModel):
    reviewed_high_tier_requirement_ids: list[str] = Field(default_factory=list)
    acknowledged_stale_offer_snapshot_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ApprovalOut(BaseModel):
    id: str
    run_id: str
    decision_mode: str
    plan_hash: str
    approved_by: str
    approved_at: datetime
    reviewed_high_tier_requirement_ids: list[str]
    acknowledged_stale_offer_snapshot_ids: list[str]
    note: str | None


class ExportRequest(BaseModel):
    supplier: str = Field(pattern="^(mouser|digikey|farnell)$")
    format: str = Field(pattern="^(csv|xlsx)$")


class ExportOut(BaseModel):
    id: str
    run_id: str
    supplier: str
    format: str
    plan_hash: str
    exported_by: str
    exported_at: datetime
    download_url: str
