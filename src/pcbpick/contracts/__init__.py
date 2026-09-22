"""Domain contracts: the versioned Pydantic models every pipeline stage consumes or emits.

See `docs/data-contracts.md` for the full flow and field-level spec. Nothing outside
this package may redefine these shapes.
"""

from pcbpick.contracts.bom import BomLine
from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.categories import CATEGORY_PARAMETERS, CategoryParameterSpec
from pcbpick.contracts.common import (
    Confidence,
    Evidence,
    Footprint,
    MpnRef,
    ParameterValue,
    PriceBreak,
)
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    DecisionMode,
    ExportFormat,
    Lifecycle,
    MountingType,
    Packaging,
    PlanWarningKind,
    SubstitutionTier,
    SupplierId,
    ValueSource,
)
from pcbpick.contracts.export import SupplierExport
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.plan import (
    PlanLine,
    PlanTotals,
    PlanWarning,
    PurchasePlan,
    UnfilledRequirement,
)
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.contracts.version import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "CATEGORY_PARAMETERS",
    "CategoryParameterSpec",
    "BomLine",
    "NormalizedRequirement",
    "ParameterValue",
    "PartCandidate",
    "SupplierOffer",
    "PurchasePlan",
    "SupplierExport",
    "Footprint",
    "MpnRef",
    "Confidence",
    "PolicyResult",
    "Evidence",
    "PriceBreak",
    "PlanLine",
    "PlanTotals",
    "UnfilledRequirement",
    "PlanWarning",
    "ComponentCategory",
    "SupplierId",
    "Lifecycle",
    "Packaging",
    "SubstitutionTier",
    "Criticality",
    "ComplianceTag",
    "DecisionMode",
    "ValueSource",
    "MountingType",
    "ExportFormat",
    "PlanWarningKind",
]
