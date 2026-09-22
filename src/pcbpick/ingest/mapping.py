"""Column mapping engine: named profile -> project memory -> heuristic -> LLM fallback.

Tries each tier in order and stops at the first confident match per target field (see
`.github/skills/bom-ingest/SKILL.md` step 3). The LLM fallback tier is a documented
extension point, not wired to a live model in M1 — see `docs/decision-log.md`
("Column-mapping LLM fallback deferred") for why. A target left unresolved after every
tier produces `MappingMethod.UNRESOLVED`, never a guess.
"""

from dataclasses import dataclass

from pcbpick.contracts.enums import MappingMethod
from pcbpick.ingest.profiles import EdaProfile, find_column
from pcbpick.ingest.synonyms import (
    BOM_LINE_TARGETS,
    SYNONYMS,
    normalize_header,
    normalize_header_base,
)

HEURISTIC_CONFIDENCE_UNIQUE = 0.8
HEURISTIC_CONFIDENCE_AMBIGUOUS = 0.5


@dataclass(frozen=True)
class ResolvedColumn:
    """One target field's resolution: which source column, by which tier, how sure."""

    target_field: str
    source_column: str | None
    method: MappingMethod
    confidence: float


def resolve_column_mapping(
    headers: list[str],
    eda_profile: EdaProfile | None,
    project_mapping: dict[str, str] | None,
) -> list[ResolvedColumn]:
    """Resolve every `BOM_LINE_TARGETS` entry against `headers`, one tier at a time."""
    header_set = set(headers)
    resolved: list[ResolvedColumn] = []
    for target in BOM_LINE_TARGETS:
        column = _resolve_via_profile(target, eda_profile, headers)
        if column is not None:
            resolved.append(ResolvedColumn(target, column, MappingMethod.PROFILE, 1.0))
            continue

        column = _resolve_via_project_memory(target, project_mapping, header_set)
        if column is not None:
            resolved.append(ResolvedColumn(target, column, MappingMethod.PROJECT_MEMORY, 0.95))
            continue

        column, confidence = _resolve_via_heuristic(target, headers)
        if column is not None:
            resolved.append(ResolvedColumn(target, column, MappingMethod.HEURISTIC, confidence))
            continue

        # LLM fallback extension point — not invoked in M1. See docs/decision-log.md.
        resolved.append(ResolvedColumn(target, None, MappingMethod.UNRESOLVED, 0.0))
    return resolved


def _resolve_via_profile(
    target: str, eda_profile: EdaProfile | None, headers: list[str]
) -> str | None:
    if eda_profile is None:
        return None
    profile_column = {
        "reference_designators": eda_profile.refdes_column,
        "quantity": eda_profile.quantity_column,
        "populate": eda_profile.populate_column,
    }[target]
    if profile_column is None:
        return None
    return find_column(headers, profile_column)


def _resolve_via_project_memory(
    target: str, project_mapping: dict[str, str] | None, header_set: set[str]
) -> str | None:
    if not project_mapping:
        return None
    column = project_mapping.get(target)
    if column is not None and column in header_set:
        return column
    return None


def _resolve_via_heuristic(target: str, headers: list[str]) -> tuple[str | None, float]:
    tokens = SYNONYMS[target]
    candidates = [
        header
        for header in headers
        if normalize_header(header) in tokens or normalize_header_base(header) in tokens
    ]
    if not candidates:
        return None, 0.0
    if len(candidates) == 1:
        return candidates[0], HEURISTIC_CONFIDENCE_UNIQUE
    # Ambiguous: more than one column claims this target (e.g. `Comment` and `Description`
    # both hold values in some Altium templates). Take the first in file order but at
    # reduced confidence so the proposal is flagged for engineer confirmation.
    return candidates[0], HEURISTIC_CONFIDENCE_AMBIGUOUS
