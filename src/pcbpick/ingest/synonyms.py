"""Column-header normalization and the synonym table from `eda-export-profiles.md`.

Shared by header-row detection (broad token coverage improves discrimination against
title blocks and data rows) and the heuristic column-mapping tier (narrow: only the
targets `BomLine` actually needs).
"""

import re

_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_DIGITS_RE = re.compile(r"\d+$")


def normalize_header(text: str) -> str:
    """Lower-case, strip punctuation/whitespace: 'Manufacturer Part Number' -> 'manufacturerpartnumber'."""  # noqa: E501
    return _PUNCTUATION_RE.sub("", text.lower())


def normalize_header_base(text: str) -> str:
    """`normalize_header` with a trailing digit run stripped: 'Supplier 1' -> 'supplier'."""
    return _TRAILING_DIGITS_RE.sub("", normalize_header(text))


# Targets a column can be mapped to. Only `reference_designators`, `quantity`, and
# `populate` cross into `BomLine` fields — the rest exist purely to sharpen header-row
# detection against title blocks, notes rows, and ad-hoc layouts.
SYNONYMS: dict[str, frozenset[str]] = {
    "reference_designators": frozenset(
        normalize_header(s)
        for s in (
            "ref",
            "refs",
            "reference",
            "references",
            "designator",
            "designators",
            "refdes",
            "part",
            "item ref",
            "position",
        )
    ),
    "quantity": frozenset(
        normalize_header(s)
        for s in ("qty", "qnty", "quantity", "count", "amount", "anzahl", "aantal", "stk")
    ),
    "populate": frozenset(
        normalize_header(s)
        for s in (
            "dnp",
            "dni",
            "fitted",
            "populate",
            "install",
            "no load",
            "exclude from bom",
            "bestucken",
        )
    ),
    "value": frozenset(
        normalize_header(s) for s in ("value", "comment", "val", "rating", "wert", "waarde")
    ),
    "description": frozenset(
        normalize_header(s)
        for s in ("description", "desc", "comment", "notes", "beschreibung", "omschrijving")
    ),
    "footprint": frozenset(
        normalize_header(s)
        for s in (
            "footprint",
            "package",
            "pcb footprint",
            "case",
            "case code",
            "pattern",
            "housing",
            "gehause",
        )
    ),
    "manufacturer": frozenset(
        normalize_header(s)
        for s in ("manufacturer", "mfr", "mfg", "maker", "brand", "hersteller", "fabrikant")
    ),
    "mpn": frozenset(
        normalize_header(s)
        for s in (
            "manufacturer part number",
            "mfr part",
            "mfr pn",
            "mpn",
            "part number",
            "partnumber",
            "mfg p/n",
            "type",
        )
    ),
    "supplier": frozenset(
        normalize_header(s) for s in ("supplier", "vendor", "distributor", "source", "leverancier")
    ),
    "supplier_pn": frozenset(
        normalize_header(s)
        for s in (
            "supplier part number",
            "order code",
            "order number",
            "sku",
            "distributor pn",
            "bestellnummer",
        )
    ),
    "tolerance": frozenset(normalize_header(s) for s in ("tolerance", "tol")),
    "voltage": frozenset(
        normalize_header(s)
        for s in ("voltage", "voltage rating", "vdc", "wvdc", "rated voltage", "spannung")
    ),
    "power": frozenset(normalize_header(s) for s in ("power", "wattage", "power rating", "watt")),
    "dielectric": frozenset(
        normalize_header(s)
        for s in ("dielectric", "temperature coefficient", "tc", "material", "char")
    ),
}

# Every normalized synonym token across every target — used to score header-row candidates.
ALL_HEADER_TOKENS: frozenset[str] = frozenset(
    token for tokens in SYNONYMS.values() for token in tokens
)

# Targets that resolve directly into `BomLine` fields. Everything else in `SYNONYMS`
# only sharpens header-row detection; the rest of the row lives untouched in `raw`.
BOM_LINE_TARGETS: tuple[str, ...] = ("reference_designators", "quantity", "populate")

# Only `reference_designators` is load-bearing: without it a line cannot be sourced.
REQUIRED_BOM_LINE_TARGETS: tuple[str, ...] = ("reference_designators",)


def matches_target(header: str, target: str) -> bool:
    """Whether `header` matches one of `target`'s synonyms, tolerating a trailing index digit."""
    tokens = SYNONYMS[target]
    return normalize_header(header) in tokens or normalize_header_base(header) in tokens
