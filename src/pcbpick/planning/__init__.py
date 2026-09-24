"""Planning: turns priced, policy-scored candidates into one `PurchasePlan` per
`DecisionMode`. Every rule here is deterministic code -- see
`.github/skills/procurement-math/SKILL.md`; the LLM is never involved in any
computation in this package.
"""

from pcbpick.planning.attrition import (
    AttritionPartClass,
    PartClassResult,
    classify_part_class,
    compute_required_qty,
)
from pcbpick.planning.config import (
    DEFAULT_ATTRITION_CONFIG,
    DEFAULT_BALANCED_WEIGHTS,
    DEFAULT_PLANNING_CONFIG,
    DEFAULT_SHIPPING_CONFIG,
    AttritionConfig,
    BalancedWeights,
    PlanningConfig,
    ShippingConfig,
)
from pcbpick.planning.order_quantity import (
    BuyUpOpportunity,
    compute_line_total,
    find_buy_up_opportunity,
    resolve_order_qty,
    round_up_to_multiple,
    select_price_break,
)
from pcbpick.planning.plan_hash import compute_plan_hash
from pcbpick.planning.stage import PlanningStage, PlanningStageInput, PlanningStagePair

__all__ = [
    "DEFAULT_ATTRITION_CONFIG",
    "DEFAULT_BALANCED_WEIGHTS",
    "DEFAULT_PLANNING_CONFIG",
    "DEFAULT_SHIPPING_CONFIG",
    "AttritionConfig",
    "AttritionPartClass",
    "BalancedWeights",
    "BuyUpOpportunity",
    "PartClassResult",
    "PlanningConfig",
    "PlanningStage",
    "PlanningStageInput",
    "PlanningStagePair",
    "ShippingConfig",
    "classify_part_class",
    "compute_line_total",
    "compute_plan_hash",
    "compute_required_qty",
    "find_buy_up_opportunity",
    "resolve_order_qty",
    "round_up_to_multiple",
    "select_price_break",
]
