"""NormalizedRequirement — what the design actually needs, independent of any supplier."""

from pydantic import BaseModel, ConfigDict

from pcbpick.contracts.common import Confidence, Footprint, MpnRef, ParameterValue
from pcbpick.contracts.enums import ComplianceTag, ComponentCategory, Criticality
from pcbpick.contracts.version import SCHEMA_VERSION


class NormalizedRequirement(BaseModel):
    """A BOM requirement resolved to SI units and a category, prior to sourcing.

    A requirement with a non-empty `unresolved` list must not proceed to sourcing
    without engineer action.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    requirement_id: str
    reference_designators: list[str]
    quantity_per_board: int
    category: ComponentCategory
    parameters: dict[str, ParameterValue]
    footprint: Footprint
    specified_mpn: MpnRef | None
    criticality: Criticality
    compliance_required: list[ComplianceTag]
    notes: str | None
    confidence: Confidence
    unresolved: list[str]


class NormalizedRequirementFragment(BaseModel):
    """The `normalize_fallback` LLM call site's output — never a full requirement.

    Only the fields the deterministic parser could not fill. Every `ParameterValue`
    in `parameters` must carry `source=ValueSource.LLM_INFERRED`; the stage that
    consumes this fragment is responsible for merging it into a `NormalizedRequirement`
    and adding the affected fields to that requirement's `unresolved` list — a
    fragment is never accepted as a substitute for engineer confirmation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    category: ComponentCategory | None
    parameters: dict[str, ParameterValue]
    footprint: Footprint | None
    compliance_required: list[ComplianceTag]
    notes: str | None
