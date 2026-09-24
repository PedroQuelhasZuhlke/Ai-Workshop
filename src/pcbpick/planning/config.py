"""Versioned configuration for the planning stage, mirroring
`policy/derating_config.py`'s pattern: a `_CONFIG_VERSION` string per config, a frozen
dataclass, and a `DEFAULT_*_CONFIG` instance. Bumping a version string is required
whenever a factor below changes, so a plan artifact can always point at the exact
table that produced it (see `.github/skills/procurement-math/SKILL.md`'s
"Reproducibility requirements").

These defaults are **proposed**, not engineering-signed-off numbers, same status as
`DEFAULT_DERATING_CONFIG`.
"""

from dataclasses import dataclass
from decimal import Decimal

from pcbpick.contracts.enums import SupplierId
from pcbpick.errors import ContractViolationError

ATTRITION_CONFIG_VERSION = "attrition-2026.09-proposed-v1"
SHIPPING_CONFIG_VERSION = "shipping-2026.09-proposed-v1"
BALANCED_WEIGHTS_VERSION = "balanced-weights-2026.09-proposed-v1"


@dataclass(frozen=True)
class AttritionFactor:
    """One part class's assembly-overage factor: `pct` plus a floor on extra pieces."""

    pct: Decimal
    min_extra: int
    description: str


@dataclass(frozen=True)
class AttritionConfig:
    """One versioned snapshot of every attrition factor `planning/attrition.py` applies.

    Per-part-class factors from `.github/skills/procurement-math/SKILL.md`'s table.
    """

    version: str
    passives_small: AttritionFactor
    passives_large: AttritionFactor
    small_smd_semiconductor: AttritionFactor
    no_attrition: AttritionFactor


DEFAULT_ATTRITION_CONFIG = AttritionConfig(
    version=ATTRITION_CONFIG_VERSION,
    passives_small=AttritionFactor(
        Decimal("0.10"), 10, "passives <=0805: 10%, minimum 10 extra pieces"
    ),
    passives_large=AttritionFactor(
        Decimal("0.05"), 5, "passives >0805: 5%, minimum 5 extra pieces"
    ),
    small_smd_semiconductor=AttritionFactor(
        Decimal("0.05"), 3, "small SMD semiconductors: 5%, minimum 3 extra pieces"
    ),
    no_attrition=AttritionFactor(
        Decimal("0"), 0, "ICs, connectors, modules, mechanical: no attrition"
    ),
)


@dataclass(frozen=True)
class ShippingTerm:
    """One supplier's shipping terms: a flat fee, waived above a subtotal threshold.

    `currency` is an ISO 4217 code, plain `str` here (not the validated `CurrencyCode`
    contract alias) — this is static developer configuration, not data crossing a
    contract boundary.
    """

    flat_fee: Decimal
    free_shipping_threshold: Decimal | None
    currency: str


@dataclass(frozen=True)
class ShippingConfig:
    """One versioned snapshot of shipping terms, one entry per known `SupplierId`."""

    version: str
    terms_by_supplier: dict[SupplierId, ShippingTerm]


DEFAULT_SHIPPING_CONFIG = ShippingConfig(
    version=SHIPPING_CONFIG_VERSION,
    terms_by_supplier={
        SupplierId.MOUSER: ShippingTerm(Decimal("8.00"), Decimal("65.00"), "USD"),
        SupplierId.DIGIKEY: ShippingTerm(Decimal("7.50"), Decimal("50.00"), "USD"),
        SupplierId.FARNELL: ShippingTerm(Decimal("9.00"), Decimal("60.00"), "USD"),
        SupplierId.FIXTURE: ShippingTerm(Decimal("5.00"), Decimal("50.00"), "USD"),
    },
)


@dataclass(frozen=True)
class BalancedWeights:
    """Normalized weights for the `balanced` decision mode. Must sum to 1 (see below).

    Recorded (via `version`) so a `balanced` plan is auditable: two runs with the
    same weight version scored the same normalized dimensions the same way.
    """

    version: str
    cost: Decimal
    lead_time: Decimal
    supplier_count: Decimal
    risk: Decimal

    def __post_init__(self) -> None:
        total = self.cost + self.lead_time + self.supplier_count + self.risk
        if total != Decimal("1"):
            raise ContractViolationError(
                f"BalancedWeights must sum to 1, got {total} (version {self.version})"
            )


DEFAULT_BALANCED_WEIGHTS = BalancedWeights(
    version=BALANCED_WEIGHTS_VERSION,
    cost=Decimal("0.4"),
    lead_time=Decimal("0.3"),
    supplier_count=Decimal("0.2"),
    risk=Decimal("0.1"),
)


@dataclass(frozen=True)
class PlanningConfig:
    """Bundles every versioned planning config plus the offer-freshness window."""

    attrition: AttritionConfig = DEFAULT_ATTRITION_CONFIG
    shipping: ShippingConfig = DEFAULT_SHIPPING_CONFIG
    balanced_weights: BalancedWeights = DEFAULT_BALANCED_WEIGHTS
    freshness_window_days: int = 90


DEFAULT_PLANNING_CONFIG = PlanningConfig()
