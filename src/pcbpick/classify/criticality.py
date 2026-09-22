"""Baseline safety-criticality classification.

M2 sets a conservative floor so `NormalizedRequirement.criticality` — a required field
— is never left unset. `policy` (M3) owns the full criticality/substitution-tier
model; this module only flags the cases explicit in the repo's non-negotiable
invariants (fuses; Y/X-class EMI suppression capacitors; optocouplers/isolation
barriers) so nothing safety-critical can slip through as `standard` by default.
"""

import re

from pcbpick.contracts.enums import ComponentCategory, Criticality

_Y_X_CLASS_RE = re.compile(r"\b[YX][1-4]\b", re.IGNORECASE)
_ISOLATION_RE = re.compile(r"\boptocoupler\b|\bisolator\b|\bisolation\b", re.IGNORECASE)


def determine_criticality(category: ComponentCategory, description: str) -> Criticality:
    if category == ComponentCategory.FUSE:
        return Criticality.SAFETY
    if category == ComponentCategory.CAPACITOR and _Y_X_CLASS_RE.search(description):
        return Criticality.SAFETY
    if _ISOLATION_RE.search(description):
        return Criticality.SAFETY
    return Criticality.STANDARD
