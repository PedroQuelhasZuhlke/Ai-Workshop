"""Sourcing: candidate search against supplier catalogs.

Sourcing-internal types (`SourcingQuery`, `CatalogHit`, `CatalogPart`, `CatalogSku`, in
`pcbpick.sourcing.types`) are not versioned contracts — see
`pcbpick.policy.candidate_input.PrePolicyCandidate` for the precedent. Network access is
confined to `pcbpick.sourcing.suppliers` (see
`.github/instructions/supplier-adapters.instructions.md`).
"""

from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.types import CatalogHit, CatalogPart, CatalogSku, SourcingQuery

__all__ = [
    "CatalogHit",
    "CatalogPart",
    "CatalogSku",
    "SourcingQuery",
    "normalize_manufacturer",
]
