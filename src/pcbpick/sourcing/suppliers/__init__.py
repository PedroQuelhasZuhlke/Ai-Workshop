"""Supplier catalog adapters — the only package permitted to touch the network.

See `.github/instructions/supplier-adapters.instructions.md`.
"""

from pcbpick.sourcing.suppliers.digikey import DigiKeyAdapter
from pcbpick.sourcing.suppliers.farnell import FarnellAdapter
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.suppliers.mouser import MouserAdapter
from pcbpick.sourcing.suppliers.protocol import SupplierAdapter

__all__ = [
    "DigiKeyAdapter",
    "FarnellAdapter",
    "FixtureAdapter",
    "MouserAdapter",
    "SupplierAdapter",
]
