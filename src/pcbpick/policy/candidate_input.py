"""`PrePolicyCandidate` — the subset of `PartCandidate` the policy engine consumes.

Policy-internal, not a contract type: `fixtures/policy/README.md` defines this exact
shape (`schema_version`, `requirement_id`, `mpn`, `manufacturer`, `parameters`,
`footprint`, `lifecycle`, `compliance`) as the pre-policy input. The fields
`substitution_tier`, `policy_results`, `rationale`, and `evidence` on
`PartCandidate` are this engine's *output* and are intentionally absent here — a new
contract type isn't warranted until sourcing (M4) defines candidate assembly.

`snapshot_id`/`fetched_at` are optional provenance for the volatile `lifecycle` and
`compliance` fields the engine gates on today (invariant 5: supplier facts carry
snapshot provenance). They are `None`, never a stand-in, until M4 sourcing populates
them for real.

`offers` carries every `SupplierOffer` sourcing (M4) assembled for this candidate —
see `pcbpick.sourcing.assembly.dedup_candidate_pairs` for how offers from multiple
hits of the same deduped candidate are unioned and deterministically ordered. That
milestone is complete now, so `offers` is no longer intentionally absent.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pcbpick.contracts.common import Footprint, ParameterValue
from pcbpick.contracts.enums import ComplianceTag, Lifecycle
from pcbpick.contracts.offer import SupplierOffer


class PrePolicyCandidate(BaseModel):
    """A candidate part as sourced, before any policy rule has run against it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    requirement_id: str
    mpn: str
    manufacturer: str
    parameters: dict[str, ParameterValue]
    footprint: Footprint
    lifecycle: Lifecycle
    compliance: list[ComplianceTag]
    snapshot_id: str | None = None
    fetched_at: datetime | None = None
    offers: list[SupplierOffer] = Field(default_factory=list)
