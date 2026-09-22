"""PartCandidate — a specific manufacturer part proposed against a requirement."""

from pydantic import BaseModel, ConfigDict

from pcbpick.contracts.common import Evidence, Footprint, ParameterValue
from pcbpick.contracts.enums import ComplianceTag, Lifecycle, SubstitutionTier
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.version import SCHEMA_VERSION


class PartCandidate(BaseModel):
    """A candidate part matched to a requirement, with every policy check and offer attached."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    requirement_id: str
    mpn: str
    manufacturer: str
    parameters: dict[str, ParameterValue]
    footprint: Footprint
    lifecycle: Lifecycle
    compliance: list[ComplianceTag]
    substitution_tier: SubstitutionTier
    policy_results: list[PolicyResult]
    rationale: str | None
    evidence: list[Evidence]
    offers: list[SupplierOffer]
