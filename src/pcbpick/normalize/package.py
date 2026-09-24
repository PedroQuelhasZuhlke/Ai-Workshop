"""Footprint/package identity resolution.

Two collision classes handled explicitly, per the part-normalization skill:

- The imperial/metric passive package tables share digit strings (`0402`, `0603`)
  with completely different physical sizes. A bare code is only ambiguous for the
  codes that actually collide — most imperial sizes (`0805`, `1206`, ...) have no
  metric-table collision and are safe to resolve even without an explicit marker.
- An IPC land-pattern prefix (`RESC`/`CAPC`/`INDC`) or the literal word `Metric`
  states the system explicitly and must be trusted over a bare-code guess.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from pcbpick.contracts.enums import MountingType

# imperial code -> (metric equivalent, length_mm, width_mm)
_PASSIVE_TABLE: dict[str, tuple[str, Decimal, Decimal]] = {
    "01005": ("0402", Decimal("0.4"), Decimal("0.2")),
    "0201": ("0603", Decimal("0.6"), Decimal("0.3")),
    "0402": ("1005", Decimal("1.0"), Decimal("0.5")),
    "0603": ("1608", Decimal("1.6"), Decimal("0.8")),
    "0805": ("2012", Decimal("2.0"), Decimal("1.25")),
    "1206": ("3216", Decimal("3.2"), Decimal("1.6")),
    "1210": ("3225", Decimal("3.2"), Decimal("2.5")),
    "1812": ("4532", Decimal("4.5"), Decimal("3.2")),
    "2010": ("5025", Decimal("5.0"), Decimal("2.5")),
    "2512": ("6332", Decimal("6.3"), Decimal("3.2")),
}
_METRIC_TO_IMPERIAL: dict[str, str] = {
    metric: imperial for imperial, (metric, *_r) in _PASSIVE_TABLE.items()
}
# The only digit strings that mean different things depending on which system is
# meant — every other imperial/metric code in the table is unambiguous even bare.
_COLLIDING_CODES: frozenset[str] = frozenset(_PASSIVE_TABLE.keys()) & frozenset(
    _METRIC_TO_IMPERIAL.keys()
)

_IPC_METRIC_PREFIXES: tuple[str, ...] = ("RESC", "CAPC", "INDC")

_SEMICONDUCTOR_FAMILIES: tuple[str, ...] = (
    "SOT-223",
    "SOT-23",
    "SOT-89",
    "SOT-323",
    "SOD-123",
    "SOD-323",
    "SOD-523",
    "SOIC",
    "TSSOP",
    "MSOP",
    "SSOP",
    "DFN",
    "QFN",
    "WSON",
    "VQFN",
    "QFP",
    "LQFP",
    "TQFP",
    "BGA",
    "FBGA",
    "WLCSP",
    "TO-220",
    "TO-252",
    "DPAK",
    "TO-263",
    "D2PAK",
    "TO-247",
    "SMA",
    "SMB",
    "SMC",
)

# KiCad/Fusion-style named footprint families for connectors and test points that
# carry no IPC land-pattern prefix and no bare digit code -- recognized the same
# way as `_SEMICONDUCTOR_FAMILIES` (family name present -> package identity known,
# no dimension/mounting invented beyond what the name itself states).
_MECHANICAL_FAMILIES: tuple[str, ...] = (
    "PINHEADER",
    "PINSOCKET",
    "TESTPOINT",
)

_ISOLATED_DIGIT_RUN_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)")


@dataclass(frozen=True)
class ResolvedPackage:
    """The result of resolving a raw footprint string to a package identity."""

    package_code: str | None
    mounting: MountingType | None
    length_mm: Decimal | None
    width_mm: Decimal | None
    recognized: bool
    ambiguous_system: bool
    raw_text: str


def _passive_from_code(code: str) -> tuple[str, Decimal, Decimal]:
    """Resolve a 4/5-digit code (known to be unambiguous) to (imperial_code, L, W)."""
    if code in _PASSIVE_TABLE:
        _metric, length, width = _PASSIVE_TABLE[code]
        return code, length, width
    imperial = _METRIC_TO_IMPERIAL[code]
    _metric, length, width = _PASSIVE_TABLE[imperial]
    return imperial, length, width


def resolve_package(footprint_raw: str) -> ResolvedPackage:
    text = footprint_raw.strip()
    if not text:
        return ResolvedPackage(None, None, None, None, False, False, text)
    upper = text.upper()

    for prefix in _IPC_METRIC_PREFIXES:
        match = re.match(rf"{prefix}(\d{{4}})", upper)
        if match and match.group(1) in _METRIC_TO_IMPERIAL:
            imperial, length, width = _passive_from_code(match.group(1))
            return ResolvedPackage(imperial, MountingType.SMT, length, width, True, False, text)

    if "METRIC" in upper:
        digit_match = _ISOLATED_DIGIT_RUN_RE.search(upper)
        if digit_match and digit_match.group(1) in _METRIC_TO_IMPERIAL:
            imperial, length, width = _passive_from_code(digit_match.group(1))
            return ResolvedPackage(imperial, MountingType.SMT, length, width, True, False, text)

    digit_match = _ISOLATED_DIGIT_RUN_RE.search(upper)
    if digit_match:
        code = digit_match.group(1)
        if code in _COLLIDING_CODES:
            return ResolvedPackage(None, None, None, None, True, True, text)
        if code in _PASSIVE_TABLE or code in _METRIC_TO_IMPERIAL:
            imperial, length, width = _passive_from_code(code)
            return ResolvedPackage(imperial, MountingType.SMT, length, width, True, False, text)

    for family in _SEMICONDUCTOR_FAMILIES:
        if re.search(rf"\b{re.escape(family)}\b", upper):
            return ResolvedPackage(upper, None, None, None, True, False, text)

    for family in _MECHANICAL_FAMILIES:
        if family in upper:
            return ResolvedPackage(family, None, None, None, True, False, text)

    return ResolvedPackage(None, None, None, None, False, False, text)
