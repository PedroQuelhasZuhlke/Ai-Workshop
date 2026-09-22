---
description: "Rules for building supplier catalog adapters (Mouser, DigiKey, Farnell, fixture) in src/pcbpick/sourcing/suppliers: the adapter protocol, snapshot caching, credentials, rate limits, stale data."
applyTo: "src/pcbpick/sourcing/suppliers/**"
---

# Supplier Adapter Rules

This is the only package permitted to make network calls.

## The protocol

Every adapter implements exactly this. Do not widen it for one supplier's convenience;
normalize inside the adapter instead.

```python
class SupplierAdapter(Protocol):
    supplier_id: SupplierId

    def search(self, query: SourcingQuery) -> list[CatalogHit]: ...
    def details(self, mpn: str) -> CatalogPart | None: ...
    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]: ...
```

Supplier-specific response shapes never escape this package. The rest of the system
sees only contract types.

## Snapshots, not caches

Every response is written to a content-addressed snapshot in `fixtures/catalogs/` or
the configured snapshot store, and every returned object carries `snapshot_id` and
`fetched_at`.

This exists so a run can be replayed against the exact catalog state it saw. A
"cache" that expires and disappears defeats the audit trail — snapshots are retained.

## Data honesty

- A field the supplier does not return is `None`. Never default `stock` to `0`, `moq`
  to `1`, or `spq` to `1`. Those are load-bearing procurement numbers.
- Do not infer parameters from a description string in the adapter. Return the
  description; let `normalize` handle it with proper provenance tagging.
- Manufacturer names are normalized through `pcbpick.sourcing.manufacturers`. `TI`,
  `Texas Instruments`, and `TEXAS INSTRUMENTS` must resolve to one canonical name.
- Price breaks are returned ascending by quantity, as `Decimal` with an explicit
  currency. If the supplier returns a different currency than requested, record it as
  returned — never convert silently.

## Resilience

- Rate limit per adapter using the configured budget. Respect `Retry-After`.
- Exponential backoff with jitter on 429 and 5xx. Bounded retries.
- Circuit-break after repeated failures and return a recorded adapter failure rather
  than hanging the run. A dead supplier degrades a run; it does not fail it.
- Every request and response is logged with the run id, the query, and the
  `snapshot_id` — but never with credentials.

## Credentials

- Read from the secret store via `pcbpick.config.secrets`. Never from a literal, never
  from a committed file, never from a run artifact.
- API keys and tokens must never appear in logs, artifacts, exception messages, or LLM
  prompts.
- Redact `Authorization` headers in any diagnostic output.

## Testing

- **No live network calls in tests. Ever.** Tests use `FixtureAdapter` or recorded
  snapshots.
- Every live adapter needs a contract test proving it produces the same normalized
  output as the fixture adapter for an equivalent snapshot.
- Include fixtures for the ugly cases: missing stock, zero stock with a lead time,
  price breaks in a foreign currency, obsolete lifecycle, an MPN that matches multiple
  manufacturers.

## Adding a new supplier

1. Implement the protocol with a new `SupplierId` enum member.
2. Add snapshot fixtures covering the cases above.
3. Add the exporter format in `src/pcbpick/exporters/` if the supplier accepts BOM
   uploads.
4. Do not touch any stage outside `sourcing/` — if you need to, the abstraction is
   wrong and should be fixed instead.
