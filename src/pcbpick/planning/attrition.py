"""Assembly attrition: part-class classification and required-quantity math.

Pure functions only, per `.github/instructions/pipeline-stages.instructions.md` — no
I/O, no clock. `Decimal`/`math.ceil` throughout; no float arithmetic anywhere in this
package, per `.github/instructions/python.instructions.md`.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Footprint
from pcbpick.contracts.enums import ComponentCategory
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.planning.config import AttritionConfig, AttritionFactor

# 0805 is 2.0mm x 1.25mm; the skill doc's "<=0805" bucket is judged on the larger of
# the two footprint dimensions so a differently-oriented land pattern still classifies
# the same way.
_SMALL_PASSIVE_MAX_DIMENSION_MM = Decimal("2.0")

_PASSIVE_CATEGORIES = frozenset(
    {
        ComponentCategory.RESISTOR,
        ComponentCategory.CAPACITOR,
        ComponentCategory.INDUCTOR,
        ComponentCategory.FERRITE_BEAD,
    }
)

# Discrete SMD semiconductors get the skill doc's "small SMD semiconductors" bucket.
# ICs are handled separately (no attrition) even though they are also semiconductors.
_SMALL_SMD_SEMICONDUCTOR_CATEGORIES = frozenset(
    {
        ComponentCategory.DIODE,
        ComponentCategory.LED,
        ComponentCategory.TRANSISTOR,
    }
)


class AttritionPartClass(StrEnum):
    """The four buckets from the procurement-math skill doc's attrition table."""

    PASSIVE_SMALL = "passive_small"
    PASSIVE_LARGE = "passive_large"
    SMALL_SMD_SEMICONDUCTOR = "small_smd_semiconductor"
    NO_ATTRITION = "no_attrition"


@dataclass(frozen=True)
class PartClassResult:
    """The classification plus whether it had to fall back on missing footprint data."""

    part_class: AttritionPartClass
    used_dimension_fallback: bool


def classify_part_class(
    requirement: NormalizedRequirement, candidate: PartCandidate
) -> PartClassResult:
    """Classifies a (requirement, candidate) pair into an `AttritionPartClass`.

    Passives and small SMD semiconductors are judged by category; passives are then
    split <=0805 vs >0805 by the candidate's footprint dimensions (falling back to the
    requirement's own footprint if the candidate doesn't state them). Every other
    category (ICs, connectors, modules, mechanical, and any category the skill doc's
    table doesn't name a row for) falls into the zero-attrition bucket.
    """
    category = requirement.category
    if category in _SMALL_SMD_SEMICONDUCTOR_CATEGORIES:
        return PartClassResult(AttritionPartClass.SMALL_SMD_SEMICONDUCTOR, False)
    if category not in _PASSIVE_CATEGORIES:
        return PartClassResult(AttritionPartClass.NO_ATTRITION, False)

    dimension = _largest_dimension_mm(candidate.footprint) or _largest_dimension_mm(
        requirement.footprint
    )
    if dimension is not None:
        part_class = (
            AttritionPartClass.PASSIVE_SMALL
            if dimension <= _SMALL_PASSIVE_MAX_DIMENSION_MM
            else AttritionPartClass.PASSIVE_LARGE
        )
        return PartClassResult(part_class, False)

    # Neither footprint states a dimension. Falling back to the >0805 (lower, 5%)
    # bucket rather than assuming the larger 10% markup on no evidence at all --
    # this is a documented, deliberate fallback, not a guess at the true package.
    return PartClassResult(AttritionPartClass.PASSIVE_LARGE, True)


def _largest_dimension_mm(footprint: Footprint) -> Decimal | None:
    if footprint.length_mm is None or footprint.width_mm is None:
        return None
    return max(footprint.length_mm, footprint.width_mm)


def _factor_for(part_class: AttritionPartClass, config: AttritionConfig) -> AttritionFactor:
    match part_class:
        case AttritionPartClass.PASSIVE_SMALL:
            return config.passives_small
        case AttritionPartClass.PASSIVE_LARGE:
            return config.passives_large
        case AttritionPartClass.SMALL_SMD_SEMICONDUCTOR:
            return config.small_smd_semiconductor
        case AttritionPartClass.NO_ATTRITION:
            return config.no_attrition


def compute_required_qty(
    board_quantity: int,
    quantity_per_board: int,
    part_class: AttritionPartClass,
    config: AttritionConfig,
) -> int:
    """`ceil(board_quantity * quantity_per_board * (1 + attrition_pct))`, floored at
    `base + min_extra` pieces, per the skill doc's exact formula."""
    factor = _factor_for(part_class, config)
    base = board_quantity * quantity_per_board
    with_attrition = math.ceil(Decimal(base) * (Decimal("1") + factor.pct))
    return max(with_attrition, base + factor.min_extra)
