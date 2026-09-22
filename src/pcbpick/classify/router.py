"""Category hint from refdes prefix + footprint family + description keywords.

Per the part-normalization skill: all three signals agreeing gives high confidence;
disagreement drops confidence and may flag. Category must be known before value
parsing, since tolerance-letter meaning and RKM decimal-marker letters are
category-dependent (see `normalize.value_parser`).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pcbpick.contracts.categories import CATEGORY_PARAMETERS
from pcbpick.contracts.enums import ComponentCategory

# Reference designator prefix -> category, for prefixes with only one plausible
# meaning. Ambiguous prefixes (T, X, U, K/RY collisions) are deliberately absent —
# see docs/decision-log.md "Reference designator prefix collisions".
_UNAMBIGUOUS_REFDES_PREFIX: dict[str, ComponentCategory] = {
    "R": ComponentCategory.RESISTOR,
    "C": ComponentCategory.CAPACITOR,
    "L": ComponentCategory.INDUCTOR,
    "FB": ComponentCategory.FERRITE_BEAD,
    "D": ComponentCategory.DIODE,
    "Q": ComponentCategory.TRANSISTOR,
    "J": ComponentCategory.CONNECTOR,
    "P": ComponentCategory.CONNECTOR,
    "SW": ComponentCategory.SWITCH,
    "S": ComponentCategory.SWITCH,
    "F": ComponentCategory.FUSE,
    "Y": ComponentCategory.CRYSTAL,
}

# Description keyword -> category. Checked as whole-word, case-insensitive substrings.
# Ordered most-specific-first: a row matching multiple entries takes the first.
_DESCRIPTION_KEYWORDS: list[tuple[re.Pattern[str], ComponentCategory]] = [
    (re.compile(r"\bled\b", re.IGNORECASE), ComponentCategory.LED),
    (re.compile(r"\bresistor\b", re.IGNORECASE), ComponentCategory.RESISTOR),
    (re.compile(r"\bcapacitor\b", re.IGNORECASE), ComponentCategory.CAPACITOR),
    (re.compile(r"\bferrite\b", re.IGNORECASE), ComponentCategory.FERRITE_BEAD),
    (re.compile(r"\binductor\b", re.IGNORECASE), ComponentCategory.INDUCTOR),
    (re.compile(r"\bfuse\b", re.IGNORECASE), ComponentCategory.FUSE),
    (re.compile(r"\brelay\b", re.IGNORECASE), ComponentCategory.RELAY),
    (re.compile(r"\btransformer\b", re.IGNORECASE), ComponentCategory.TRANSFORMER),
    (re.compile(r"\bcrystal\b", re.IGNORECASE), ComponentCategory.CRYSTAL),
    (re.compile(r"\boscillator\b", re.IGNORECASE), ComponentCategory.OSCILLATOR),
    (re.compile(r"\bconnector\b|\bheader\b", re.IGNORECASE), ComponentCategory.CONNECTOR),
    (re.compile(r"\bswitch\b", re.IGNORECASE), ComponentCategory.SWITCH),
    (re.compile(r"\bdiode\b", re.IGNORECASE), ComponentCategory.DIODE),
    (re.compile(r"\btransistor\b|\bmosfet\b|\bbjt\b", re.IGNORECASE), ComponentCategory.TRANSISTOR),
    (re.compile(r"\bmodule\b", re.IGNORECASE), ComponentCategory.MODULE),
    (
        re.compile(r"\brf\b|\btransceiver\b|\bwireless\b|\bantenna\b", re.IGNORECASE),
        ComponentCategory.IC_RF,
    ),
    (
        re.compile(r"\bregulator\b|\bpmic\b|\bconverter\b|\bpower supply\b", re.IGNORECASE),
        ComponentCategory.IC_POWER,
    ),
    (
        re.compile(r"\bmcu\b|\bmicrocontroller\b|\blogic\b|\bdigital\b", re.IGNORECASE),
        ComponentCategory.IC_DIGITAL,
    ),
    (
        re.compile(r"\bop-?amp\b|\bamplifier\b|\banalog\b|\bcomparator\b", re.IGNORECASE),
        ComponentCategory.IC_ANALOG,
    ),
    (
        re.compile(r"\bconnector\b|\bheader\b|\bsocket\b", re.IGNORECASE),
        ComponentCategory.CONNECTOR,
    ),
]

_REFDES_PREFIX_RE = re.compile(r"^([A-Za-z]+)\d")


@dataclass(frozen=True)
class CategoryHint:
    """The category classification result plus the confidence signal behind it."""

    category: ComponentCategory
    confident: bool
    reason: str


def hint_category(reference_designator: str, description: str) -> CategoryHint:
    """Combine refdes prefix and description keywords into a category hint.

    Footprint family is intentionally not consulted here — footprint identity is
    resolved independently in `normalize.package` and does not drive category choice,
    since the same footprint family (e.g. a two-pad SMD pad) is shared by several
    categories.
    """
    prefix_match = _REFDES_PREFIX_RE.match(reference_designator)
    prefix = prefix_match.group(1).upper() if prefix_match else ""
    from_prefix = _UNAMBIGUOUS_REFDES_PREFIX.get(prefix)

    from_description: ComponentCategory | None = None
    for pattern, category in _DESCRIPTION_KEYWORDS:
        if pattern.search(description):
            from_description = category
            break

    if from_prefix is not None and from_description is not None:
        if from_prefix == from_description:
            return CategoryHint(from_prefix, True, "refdes prefix and description agree")
        # Disagreement: description is more specific (LED vs. generic diode prefix D).
        if from_prefix == ComponentCategory.DIODE and from_description == ComponentCategory.LED:
            return CategoryHint(from_description, True, "description specializes diode to LED")
        return CategoryHint(
            ComponentCategory.UNKNOWN,
            False,
            f"refdes prefix suggests {from_prefix.value}, description suggests "
            f"{from_description.value}",
        )
    if from_prefix is not None:
        return CategoryHint(from_prefix, True, "resolved from reference designator prefix")
    if from_description is not None:
        return CategoryHint(from_description, True, "resolved from description keyword")
    return CategoryHint(
        ComponentCategory.UNKNOWN, False, "no refdes prefix or description keyword matched"
    )


def missing_required_parameters(
    category: ComponentCategory, parameters: Mapping[str, object]
) -> list[str]:
    """Required parameter names (per `categories.py`) absent from `parameters`.

    Returned as dotted names (`parameters.<name>`) matching the `unresolved` convention.
    """
    spec = CATEGORY_PARAMETERS[category]
    return sorted(f"parameters.{name}" for name in spec.required if name not in parameters)
