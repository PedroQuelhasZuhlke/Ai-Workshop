"""Supplier catalog adapters — the only package permitted to touch the network.

See `.github/instructions/supplier-adapters.instructions.md`.
"""

from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.suppliers.protocol import SupplierAdapter

__all__ = ["FixtureAdapter", "SupplierAdapter"]
