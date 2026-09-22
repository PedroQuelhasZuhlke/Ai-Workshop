---
name: procurement-math
description: 'Compute order quantities, price breaks, MOQ/SPQ rounding, assembly attrition, shipping thresholds and multi-supplier splits. Use when implementing or debugging the planning stage, decision modes (lowest cost, fastest delivery, fewest suppliers, balanced, lowest risk), or plan totals.'
---

# Procurement Math

All of this is deterministic code. The LLM is never involved in any calculation on
this page, and never selects a plan.

## Money rules

- `Decimal` only, with an explicit ISO 4217 currency on every amount.
- Never mix currencies in an arithmetic operation. If offers arrive in different
  currencies, either convert with a recorded rate and rate date, or keep the plans
  separate. Never convert silently.
- Round only at presentation. Intermediate math keeps full precision.
- Rounding mode is `ROUND_HALF_UP` at 2 decimal places for display totals, applied
  once, at the end.

## Order quantity

Required quantity per requirement:

```
need = ceil(board_quantity × quantity_per_board × (1 + attrition_pct))
```

Attrition covers assembly losses — pick-and-place setup, tombstoning, rework. Applied
to passives and small SMD parts, not to expensive ICs, connectors, or modules. Default
factors are configuration, not hardcoded:

| Part class | Default attrition |
|---|---|
| Passives ≤ 0805 | 10%, minimum 10 extra pieces |
| Passives > 0805 | 5%, minimum 5 extra pieces |
| Small SMD semiconductors | 5%, minimum 3 extra pieces |
| ICs, connectors, modules, mechanical | 0% |

Minimum-extra-pieces matters for prototype runs: 10% of 4 parts is 0, which leaves no
margin for a single mishandled component.

Then apply supplier packaging constraints:

```
order_qty = max(offer.moq, round_up_to_multiple(need, offer.spq))
```

MOQ and SPQ are independent. SPQ (standard pack quantity) means the supplier ships
whole packs — a 4000-piece reel is 4000 pieces even if MOQ is 1. Ignoring SPQ produces
quotes that do not match the actual invoice. If either is `None`, the offer cannot be
used for an authoritative plan; flag it.

## Price breaks

Price breaks are ascending `(min_qty, unit_price)` tuples. The unit price is the price
for the whole order at that quantity, not a marginal rate.

```
applicable = max(b for b in breaks if b.min_qty <= order_qty)
line_total = order_qty × applicable.unit_price
```

**Break-point buy-up:** ordering *more* is sometimes cheaper in total. Always evaluate
the next break above the computed quantity:

```
for b in breaks where b.min_qty > order_qty:
    candidate_qty = round_up_to_multiple(b.min_qty, spq)
    if candidate_qty × b.unit_price < line_total:
        propose buy-up
```

A buy-up is proposed with the extra quantity and the saving shown explicitly. It is
never applied silently — surplus inventory is a real cost the tool cannot see.

## Plan totals

Computed per supplier, then aggregated:

- Line subtotals
- Supplier subtotal
- Shipping: flat, tiered, or waived above a free-shipping threshold (configuration
  per supplier)
- Handling or small-order fees
- Duties and VAT are **out of scope** unless configured; when omitted, label the total
  explicitly as excluding them. Never present an ambiguous total.

The grand total is the sum of supplier totals. Record each component separately in the
artifact — an engineer comparing plans needs to see where the money went.

## Lead time

`longest_lead_time_days` across all lines gates the build. For a stocked line, lead
time is 0 and stock must cover `order_qty`. For a partially stocked line, either split
across suppliers or take the backorder lead time; record which.

A line where no supplier can cover the quantity is an `UnfilledRequirement` with the
shortfall stated. It is never quietly reduced to available stock.

## Decision modes

Each mode is a pure scoring function over the same candidate/offer matrix. Adding a
mode must not require changing any other stage.

| Mode | Objective | Tie-breakers |
|---|---|---|
| `lowest_cost` | Minimize grand total including shipping | Fewer suppliers, then shorter lead time |
| `fastest_delivery` | Minimize longest lead time | Then total cost |
| `fewest_suppliers` | Minimize supplier count | Then total cost |
| `balanced` | Weighted score over normalized cost, lead time, supplier count, risk | Then total cost |
| `lowest_risk` | Tier 0/1 only, active lifecycle, stock ≥ 2 × order quantity, fresh offers | Then total cost |

Tie-breakers must produce a total order. Two plans with identical scores must resolve
deterministically — fall back to a stable sort on plan hash. Non-deterministic plan
selection is a defect.

`balanced` weights live in configuration and are recorded in the plan artifact. A plan
whose weights are not reproducible is not auditable.

## Multi-supplier split

Minimizing per-line cost independently usually loses to consolidation once shipping
and minimum-order fees are counted.

Approach:

1. Build the candidate offer matrix: requirement × supplier × offer.
2. For each viable supplier subset (bounded — typically ≤ 3 suppliers), assign each
   line to its cheapest offer within the subset.
3. Add shipping, handling, and free-shipping thresholds per supplier in the subset.
4. Discard subsets that cannot fill every requirement.
5. Score under the active decision mode.

Enumerate subsets exhaustively when the supplier count is small; this is not a problem
that needs a solver at three or four suppliers. If the supplier count grows, replace
with an explicit optimizer — never with a heuristic that cannot explain its choice.

## Reproducibility requirements

- Same inputs and same snapshot IDs must produce byte-identical plans on any machine.
- Sort keys must be total. Never depend on dict or set ordering.
- The plan records: derating config version, attrition config version, shipping config
  version, all `snapshot_ids`, and the currency and any conversion rates used.
- `plan_hash` covers everything needed to reproduce the plan. The approval ledger
  references it.

## Stale data

An offer older than `config.sourcing.freshness_window` is marked stale. Stale offers:

- may appear in exploratory plans, clearly flagged,
- may never appear in an approved export,
- must be re-fetched and the plan recomputed before approval completes.

Stock and price are always volatile. The plan is a proposal about a moment in time,
and the artifact records which moment.
