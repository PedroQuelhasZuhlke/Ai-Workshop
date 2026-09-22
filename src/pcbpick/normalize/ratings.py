"""Ratings and characteristics extracted from free text: voltage, current, dielectric,
compliance tokens. Lower confidence than a dedicated column, but still `parsed`, not
`llm_inferred` — regex extraction is deterministic.
"""

import re
from decimal import Decimal

from pcbpick.contracts.enums import ComplianceTag

_VOLTAGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*V(?:AC|DC)?\b")
_CURRENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*A\b")
_DIELECTRIC_RE = re.compile(r"\b(C0G|NP0|X5R|X6S|X7R|X7S|Y5V|Z5U|U2J)\b", re.IGNORECASE)

# `non-rohs`/`leaded`/`snpb` directly contradict a RoHS assertion in the same text —
# leaded (SnPb) solder is the classic RoHS-restricted substance.
_ROHS_POSITIVE_RE = re.compile(r"\brohs\b", re.IGNORECASE)
_ROHS_NEGATIVE_RE = re.compile(r"\bnon-?rohs\b|\bleaded\b|\bsnpb\b", re.IGNORECASE)
_AEC_RE = re.compile(r"\baec[- ]?q(100|200)\b", re.IGNORECASE)


def extract_voltage_rating(text: str) -> tuple[Decimal, str] | None:
    match = _VOLTAGE_RE.search(text)
    return (Decimal(match.group(1)), match.group(0)) if match else None


def extract_current_rating(text: str) -> tuple[Decimal, str] | None:
    match = _CURRENT_RE.search(text)
    return (Decimal(match.group(1)), match.group(0)) if match else None


def extract_dielectric(text: str) -> str | None:
    match = _DIELECTRIC_RE.search(text)
    return match.group(1).upper() if match else None


def extract_compliance(text: str) -> tuple[list[ComplianceTag], bool]:
    """Returns `(tags, conflicting)`.

    `conflicting=True` means the text asserts and denies RoHS in the same breath —
    the caller must leave `compliance_required` empty and flag `unresolved` rather
    than pick a side.
    """
    positive = bool(_ROHS_POSITIVE_RE.search(text))
    negative = bool(_ROHS_NEGATIVE_RE.search(text))
    if positive and negative:
        return [], True

    tags: list[ComplianceTag] = []
    if positive:
        tags.append(ComplianceTag.ROHS)
    aec_match = _AEC_RE.search(text)
    if aec_match:
        tags.append(
            ComplianceTag.AEC_Q100 if aec_match.group(1) == "100" else ComplianceTag.AEC_Q200
        )
    return tags, False
