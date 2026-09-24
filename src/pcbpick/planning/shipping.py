"""Per-supplier shipping cost. A single pure function, per
`.github/skills/procurement-math/SKILL.md`'s "Plan totals" section: flat fee, waived
above a free-shipping threshold.
"""

from decimal import Decimal

from pcbpick.planning.config import ShippingTerm


def compute_shipping_cost(term: ShippingTerm, subtotal: Decimal) -> Decimal:
    """`0` if `subtotal` clears the free-shipping threshold, else the flat fee."""
    if term.free_shipping_threshold is not None and subtotal >= term.free_shipping_threshold:
        return Decimal("0")
    return term.flat_fee
