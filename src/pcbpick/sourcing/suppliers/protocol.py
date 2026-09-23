"""The one shape every supplier adapter must satisfy.

Per `.github/instructions/supplier-adapters.instructions.md`: never widen this for one
supplier's convenience. A supplier's raw response shape is normalized inside its own
adapter and never crosses this boundary — callers only ever see `CatalogHit`,
`CatalogPart`, and `SupplierOffer`.
"""

from typing import Protocol

from pcbpick.contracts.enums import SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.sourcing.types import CatalogHit, CatalogPart, SourcingQuery


class SupplierAdapter(Protocol):
    """A catalog search/detail/offer interface. The only I/O boundary a supplier gets."""

    supplier_id: SupplierId

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        """Cheap candidate lookup: one `CatalogHit` per (part, SKU) pair that matches."""
        ...

    def details(self, mpn: str) -> CatalogPart | None:
        """Full part record for an exact `mpn`, or `None` if this supplier doesn't have it."""
        ...

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        """Purchase terms for one SKU. Empty list if the SKU is unknown to this supplier."""
        ...
