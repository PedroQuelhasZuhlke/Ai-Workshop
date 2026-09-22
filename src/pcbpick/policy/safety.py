"""Safety-critical detection: escalates `Criticality`, never relaxes it.

Per `.github/skills/substitution-policy/references/category-rules.md`, automatic
classification "may only ever *increase* criticality" over the M2 floor
(`pcbpick.classify.criticality`) and whatever is already recorded on the
`NormalizedRequirement` — an engineer-marked `do_not_substitute` always wins outright.
"""

import re

from pcbpick.contracts.enums import ComponentCategory, Criticality
from pcbpick.contracts.requirement import NormalizedRequirement

# Category-list detection: fuses are safety-critical unconditionally.
_ALWAYS_SAFETY_CATEGORIES = frozenset({ComponentCategory.FUSE})

# Description/parameter token list from category-rules.md's "By description or
# parameter token" list, plus the isolation vocabulary already used by the M2 floor.
_SAFETY_TOKEN_RE = re.compile(
    r"\b(Y1|Y2|X1|X2|VDE|UL|CSA|T[UÜ]V|ENEC|SELV|SIL|ASIL|MOV|varistor)\b"
    r"|IEC\s?60384-14|IEC\s?62368|IEC\s?61508|ISO\s?13849"
    r"|reinforced insulation|basic insulation|safety agency|line voltage|\bmains\b"
    r"|\bcreepage\b|\bclearance\b|functional safety|optocoupler|\bisolator\b|isolation",
    re.IGNORECASE,
)

_CRITICALITY_RANK: dict[Criticality, int] = {
    Criticality.STANDARD: 0,
    Criticality.SAFETY: 1,
    Criticality.DO_NOT_SUBSTITUTE: 2,
}


def detect_safety_criticality(category: ComponentCategory, searchable_text: str) -> bool:
    """True if the category or any recorded free text marks this requirement safety-critical.

    `searchable_text` should be every free-text field the requirement carries (notes,
    footprint raw text, and every parameter's `raw_text`) — safety markings like a `Y2`
    dielectric class or a `mains`-rated footprint note routinely appear outside `notes`
    alone, so restricting detection to `notes` misses them.
    """
    if category in _ALWAYS_SAFETY_CATEGORIES:
        return True
    return bool(_SAFETY_TOKEN_RE.search(searchable_text))


def _searchable_text(requirement: NormalizedRequirement) -> str:
    parts: list[str] = [requirement.notes or ""]
    parts.append(requirement.footprint.raw_text or "")
    parts.append(requirement.footprint.package_code or "")
    for param in requirement.parameters.values():
        parts.append(param.raw_text)
    return " ".join(parts)


def effective_criticality(requirement: NormalizedRequirement) -> Criticality:
    """`requirement.criticality` widened by automatic detection — never narrowed."""
    detected = detect_safety_criticality(requirement.category, _searchable_text(requirement))
    auto = Criticality.SAFETY if detected else Criticality.STANDARD
    return max(requirement.criticality, auto, key=_CRITICALITY_RANK.__getitem__)
