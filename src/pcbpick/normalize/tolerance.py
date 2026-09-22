"""Tolerance parsing: explicit percent forms and per-category EIA/IEC letter tables.

Capacitor and resistor tolerance-letter tables share several letters (`B`, `C`, `D`,
`F`, `G`, `J`, `K`, `M`) with different meanings — see
`.github/skills/part-normalization/references/value-notation.md`. The caller must
always know the category before calling `parse_tolerance_letter`.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from pcbpick.contracts.enums import ComponentCategory

_RESISTOR_LETTER_PCT: dict[str, Decimal] = {
    "B": Decimal("0.1"),
    "C": Decimal("0.25"),
    "D": Decimal("0.5"),
    "F": Decimal("1"),
    "G": Decimal("2"),
    "J": Decimal("5"),
    "K": Decimal("10"),
    "M": Decimal("20"),
}

# B/C/D are absolute picofarads on capacitors, not percentages — not representable in
# `tolerance_pct`, so they are deliberately excluded here rather than misapplied.
_CAPACITOR_LETTER_PCT: dict[str, Decimal] = {
    "F": Decimal("1"),
    "G": Decimal("2"),
    "J": Decimal("5"),
    "K": Decimal("10"),
    "M": Decimal("20"),
}

# (plus_pct, minus_pct) — asymmetric, never collapsible into a single `tolerance_pct`.
_CAPACITOR_ASYMMETRIC: dict[str, tuple[Decimal, Decimal]] = {
    "Z": (Decimal("80"), Decimal("-20")),
}

_EXPLICIT_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class ToleranceResult:
    tolerance_pct: Decimal | None
    asymmetric: tuple[Decimal, Decimal] | None
    recognized: bool
    reason: str = ""


def parse_tolerance_letter(letter: str, category: ComponentCategory) -> ToleranceResult:
    """Look up a single tolerance letter in the table for `category`. Never guesses."""
    upper = letter.upper()
    if category == ComponentCategory.CAPACITOR:
        if upper in _CAPACITOR_ASYMMETRIC:
            return ToleranceResult(None, _CAPACITOR_ASYMMETRIC[upper], True)
        if upper in _CAPACITOR_LETTER_PCT:
            return ToleranceResult(_CAPACITOR_LETTER_PCT[upper], None, True)
        return ToleranceResult(
            None, None, False, f"{letter!r} is not a recognized capacitor tolerance letter"
        )
    if upper in _RESISTOR_LETTER_PCT:
        return ToleranceResult(_RESISTOR_LETTER_PCT[upper], None, True)
    return ToleranceResult(
        None, None, False, f"{letter!r} is not a recognized resistor tolerance letter"
    )


def parse_explicit_tolerance_pct(text: str) -> Decimal | None:
    """Find a bare `N%` anywhere in free text — sign prefixes (`+/-`, `±`) are optional."""
    match = _EXPLICIT_PCT_RE.search(text)
    return Decimal(match.group(1)) if match else None
