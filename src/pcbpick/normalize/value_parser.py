"""Primary-value parsing for resistors, capacitors, and inductors.

Handles, in priority order per the part-normalization skill: category-specific
ambiguity traps, RKM/EIA shorthand, SI-prefix + explicit-unit notation, the
capacitor 3-digit pF code, and a never-guess fallback for anything else.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from pcbpick.contracts.enums import ComponentCategory
from pcbpick.normalize.text import normalize_value_text
from pcbpick.normalize.tolerance import parse_tolerance_letter

# Resistor RKM connector letters double as SI-prefix multipliers: the letter both
# marks the decimal point (RKM shorthand) and states the magnitude (SI notation) —
# the same grammar covers both per the value-notation reference.
_RESISTOR_CONNECTORS: dict[str, Decimal] = {
    "R": Decimal(1),
    "r": Decimal(1),
    "K": Decimal("1e3"),
    "k": Decimal("1e3"),
    "M": Decimal("1e6"),
    "m": Decimal("1e-3"),
    "G": Decimal("1e9"),
    "g": Decimal("1e9"),
}

# Capacitor/inductor shorthand never uses K/M/G — those letters are reserved as
# tolerance-table letters (`225K`) or would silently collide with them, so they are
# deliberately excluded here rather than accepted (see the capacitor `1M` trap).
_FARAD_HENRY_CONNECTORS: dict[str, Decimal] = {
    "p": Decimal("1e-12"),
    "n": Decimal("1e-9"),
    "u": Decimal("1e-6"),
    "U": Decimal("1e-6"),
    "m": Decimal("1e-3"),
}

# A 3-digit value with a trailing tolerance-table letter is a genuine collision on
# resistors (RKM multiplier reading vs. chip-code-plus-tolerance-letter reading) but
# not on capacitors (there is no competing capacitor RKM use of K/M as a multiplier).
_RESISTOR_TOLERANCE_LETTERS = frozenset("BCDFGJKM")
_CAPACITOR_CODE_LETTERS = frozenset("BCDFGJKMZ")

_THREE_DIGIT_LETTER_RE = re.compile(r"(\d{3})([A-Za-z])")
_PLAIN_OHM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ohm|OHM|Ω)?")
_EXPLICIT_F_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(p|n|u|U)?[fF]")
_EXPLICIT_H_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(p|n|u|U|m)?[hH]")


@dataclass(frozen=True)
class ParsedPrimary:
    """The result of parsing one BOM value string for one primary parameter."""

    value: Decimal | None
    unit: str
    tolerance_pct: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)
    reason: str = ""


def _connector_match(text: str, connectors: dict[str, Decimal]) -> Decimal | None:
    for letter, multiplier in connectors.items():
        match = re.fullmatch(rf"(\d*)({re.escape(letter)})(\d*)", text)
        if match and (match.group(1) or match.group(3)):
            whole, _letter, frac = match.groups()
            number_str = f"{whole or '0'}.{frac}" if frac else (whole or "0")
            return Decimal(number_str) * multiplier
    return None


def parse_resistance(raw_text: str) -> ParsedPrimary:
    text = normalize_value_text(raw_text)

    collision = re.fullmatch(_THREE_DIGIT_LETTER_RE, text)
    if collision and collision.group(2).upper() in _RESISTOR_TOLERANCE_LETTERS:
        digits, letter = collision.groups()
        multiplier = _RESISTOR_CONNECTORS.get(letter, _RESISTOR_CONNECTORS[letter.upper()])
        rkm_ohms = Decimal(digits) * multiplier
        code_ohms = Decimal(digits[:2]) * (Decimal(10) ** int(digits[2]))
        return ParsedPrimary(
            value=None,
            unit="ohm",
            ambiguous=True,
            candidates=[
                f"RKM shorthand '{digits}{letter}' = {rkm_ohms} ohm",
                f"chip-code '{digits[:2]}x10^{digits[2]}' + tolerance letter '{letter.upper()}' "
                f"= {code_ohms} ohm",
            ],
            reason=(
                "3-digit value with a trailing tolerance-table letter collides between "
                "RKM shorthand and a chip-resistor code+tolerance-letter marking"
            ),
        )

    connector_value = _connector_match(text, _RESISTOR_CONNECTORS)
    if connector_value is not None:
        return ParsedPrimary(connector_value, "ohm", reason="RKM shorthand")

    plain = re.fullmatch(_PLAIN_OHM_RE, text)
    if plain and plain.group(1):
        return ParsedPrimary(Decimal(plain.group(1)), "ohm", reason="plain decimal ohm value")

    return ParsedPrimary(
        None,
        "ohm",
        ambiguous=True,
        candidates=[f"unrecognized resistor value notation {raw_text!r}"],
        reason="no recognized resistor value notation",
    )


def parse_capacitance(raw_text: str) -> ParsedPrimary:
    text = normalize_value_text(raw_text)

    code = re.fullmatch(_THREE_DIGIT_LETTER_RE, text)
    if code and code.group(2).upper() in _CAPACITOR_CODE_LETTERS:
        digits, letter = code.groups()
        pf_value = Decimal(digits[:2]) * (Decimal(10) ** int(digits[2]))
        farads = pf_value * Decimal("1e-12")
        tolerance = parse_tolerance_letter(letter, ComponentCategory.CAPACITOR)
        if tolerance.asymmetric is not None:
            plus_pct, minus_pct = tolerance.asymmetric
            return ParsedPrimary(
                value=farads,
                unit="farad",
                min=farads * (Decimal(1) + minus_pct / Decimal(100)),
                max=farads * (Decimal(1) + plus_pct / Decimal(100)),
                reason="EIA 3-digit code with an asymmetric tolerance letter",
            )
        return ParsedPrimary(
            value=farads,
            unit="farad",
            tolerance_pct=tolerance.tolerance_pct,
            reason="EIA 3-digit code with a tolerance letter",
        )

    connector_value = _connector_match(text, _FARAD_HENRY_CONNECTORS)
    if connector_value is not None:
        return ParsedPrimary(connector_value, "farad", reason="RKM/SI-prefix shorthand")

    explicit = re.fullmatch(_EXPLICIT_F_RE, text)
    if explicit and explicit.group(1):
        number, prefix = explicit.groups()
        multiplier = _FARAD_HENRY_CONNECTORS[prefix] if prefix else Decimal(1)
        return ParsedPrimary(
            Decimal(number) * multiplier, "farad", reason="plain decimal with explicit unit"
        )

    return ParsedPrimary(
        None,
        "farad",
        ambiguous=True,
        candidates=[
            f"unrecognized or bare capacitor value notation {raw_text!r} "
            "(could be an EIA pF code or a literal misentry — no unit letter present)"
        ],
        reason="no recognized unambiguous capacitor value notation",
    )


def parse_inductance(raw_text: str) -> ParsedPrimary:
    text = normalize_value_text(raw_text)

    connector_value = _connector_match(text, _FARAD_HENRY_CONNECTORS)
    if connector_value is not None:
        return ParsedPrimary(connector_value, "henry", reason="RKM/SI-prefix shorthand")

    explicit = re.fullmatch(_EXPLICIT_H_RE, text)
    if explicit and explicit.group(1):
        number, prefix = explicit.groups()
        multiplier = _FARAD_HENRY_CONNECTORS[prefix] if prefix else Decimal(1)
        return ParsedPrimary(
            Decimal(number) * multiplier, "henry", reason="plain decimal with explicit unit"
        )

    return ParsedPrimary(
        None,
        "henry",
        ambiguous=True,
        candidates=[f"unrecognized inductor value notation {raw_text!r}"],
        reason="no recognized inductor value notation",
    )
