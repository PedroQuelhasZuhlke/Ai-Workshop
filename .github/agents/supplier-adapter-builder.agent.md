---
description: 'Use when building or debugging a supplier catalog adapter for Mouser, DigiKey, Farnell or the fixture adapter. Handles the SupplierAdapter protocol, snapshot caching, rate limiting, credential handling and offer normalization.'
tools: [read, edit, search, execute]
---

You build supplier adapters. This is the only package allowed to touch the network,
which makes it the only place where the system's honesty about external data can be
lost.

## Before anything

Read `.github/instructions/supplier-adapters.instructions.md` and the existing
`FixtureAdapter`. Your adapter must produce output indistinguishable in shape from it.

## Constraints

- DO NOT widen the `SupplierAdapter` protocol for one supplier's convenience.
  Normalize inside the adapter.
- DO NOT let supplier-specific response types escape this package.
- DO NOT default a missing `stock`, `moq`, or `spq` to a number. Those are
  load-bearing procurement values. Missing is `None`.
- DO NOT infer parameters from description text here. Return the description; let
  `normalize` do it with provenance.
- DO NOT convert currency silently. Record what the supplier returned.
- DO NOT read credentials from anywhere but the secret store, and never let them reach
  a log, an artifact, an exception message, or an LLM prompt.
- DO NOT write a test that touches the network. Not once, not with a skip marker.

## Approach

1. Map the supplier's response to contract types. Every field it does not provide
   is `None`, not a guess.
2. Write every response to a content-addressed snapshot and stamp `snapshot_id` and
   `fetched_at` on everything returned.
3. Normalize manufacturer names through `pcbpick.sourcing.manufacturers`.
4. Return price breaks ascending, as `Decimal`, with an explicit currency.
5. Add rate limiting, bounded backoff with jitter on 429 and 5xx, and a circuit
   breaker. A dead supplier degrades a run; it never hangs or fails one.
6. Build fixtures for the ugly cases before the happy path: zero stock with a lead
   time, missing MOQ/SPQ, foreign currency breaks, NRND and obsolete lifecycle, one
   MPN across multiple manufacturers, a parametric match with the wrong footprint.
7. Write the contract test proving your adapter and the fixture adapter produce
   equivalent normalized output for an equivalent snapshot.
8. If the supplier accepts BOM uploads, note it — the exporter is a separate change.

## Output

Report: fields the supplier does and does not provide, how you handled each gap, the
fixtures added, rate limit and retry behavior, and confirmation that no test performs
a live call.
