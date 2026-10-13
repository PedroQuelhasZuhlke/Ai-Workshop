"""Order-quantity math: MOQ/SPQ rounding, price-break selection, and break-point
buy-up detection. Pure functions only; see
`.github/skills/procurement-math/SKILL.md`'s "Order quantity" and "Price breaks"
sections for the exact formulas this module implements.
"""

from dataclasses import dataclass
from decimal import Decimal

from pcbpick.contracts.common import PriceBreak
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.errors import ContractViolationError


def round_up_to_multiple(value: int, multiple: int) -> int:
    """Rounds `value` up to the nearest multiple of `multiple` (`multiple` must be > 0)."""
    if multiple <= 0:
        raise ContractViolationError(f"multiple must be positive, got {multiple}")
    return -(-value // multiple) * multiple


def resolve_order_qty(required_qty: int, offer: SupplierOffer) -> int:
    """`max(offer.moq, round_up_to_multiple(required_qty, offer.spq))`."""
    return max(offer.moq, round_up_to_multiple(required_qty, offer.spq))


def select_price_break(order_qty: int, price_breaks: list[PriceBreak]) -> PriceBreak | None:
    """The highest `min_qty <= order_qty` rung on the ladder, or `None` if none applies."""
    applicable = [b for b in price_breaks if b.quantity <= order_qty]
    if not applicable:
        return None
    return max(applicable, key=lambda b: b.quantity)


def compute_line_total(order_qty: int, unit_price: Decimal) -> Decimal:
    """`order_qty * unit_price`. Full precision -- rounding happens only at display."""
    return Decimal(order_qty) * unit_price


@dataclass(frozen=True)
class BuyUpOpportunity:
    """A proposed larger order that would be cheaper in total. Never applied silently."""

    new_order_qty: int
    extra_qty: int
    new_unit_price: Decimal
    new_line_total: Decimal
    saving: Decimal


def find_buy_up_opportunity(
    order_qty: int,
    line_total: Decimal,
    spq: int,
    price_breaks: list[PriceBreak],
) -> BuyUpOpportunity | None:
    """The best next-break buy-up, if ordering more would cost less in total.

    Evaluates every break above `order_qty` and returns the one with the largest
    saving; `None` if no higher break beats the current `line_total`. This is data
    for the caller to decide whether to surface -- it never adjusts `order_qty`
    itself.
    """
    best: BuyUpOpportunity | None = None
    for price_break in price_breaks:
        if price_break.quantity <= order_qty:
            continue
        candidate_qty = round_up_to_multiple(price_break.quantity, spq)
        candidate_total = compute_line_total(candidate_qty, price_break.unit_price)
        saving = line_total - candidate_total
        if saving > 0 and (best is None or saving > best.saving):
            best = BuyUpOpportunity(
                new_order_qty=candidate_qty,
                extra_qty=candidate_qty - order_qty,
                new_unit_price=price_break.unit_price,
                new_line_total=candidate_total,
                saving=saving,
            )
    return best
