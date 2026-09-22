# Implementation Roadmap

Milestones are ordered so that each one produces something an engineer can actually
use or critique. Nothing here depends on supplier API credentials until M5.

## M0 — Contracts and skeleton

- Pydantic v2 models for every type in `docs/data-contracts.md`
- JSON Schema export to `contracts/schema/v1/`
- Category parameter declarations (`categories.py`)
- Stage protocol, `StageContext`, `StageResult`, run artifact writer
- CLI: `pcbpick run <file>`, `pcbpick resume <run_id> --from <stage>`
- pytest + uv + CI

**Done when:** an empty pipeline runs end to end and writes artifacts.

## M1 — Ingest

- CSV / XLSX / XLS readers with hardened parsing
- EDA profile detection for Altium, KiCad, Eagle/Fusion, OrCAD/Allegro
- Column mapping engine: profile match → heuristic match → LLM fallback
- Reference designator expansion and validation (`R1-R4`, `C1,C3`, `U1`)
- Quantity reconciliation against refdes count, with mismatch flagged not fixed
- Mapping profiles persisted per project

**Done when:** all sample BOMs in `fixtures/boms/` ingest with correct refdes counts,
and an unknown-format file produces a mapping proposal rather than an error.

## M2 — Normalization and classification

- Value parser: SI prefixes, EIA shorthand (`4k7`, `100n`, `R47`), tolerance suffixes
- Package code recognition: imperial/metric passives, SOT/SOIC/QFN/BGA families
- Dielectric, lifecycle, and compliance token extraction from descriptions
- Category router with per-category required-parameter validation
- Confidence scoring and `unresolved` population
- LLM fallback for unparseable rows

**Done when:** golden BOMs normalize with zero silent errors; every ambiguity appears
in `unresolved` instead of being guessed.

## M3 — Policy engine

- Derating rules per category (voltage, power, current, temperature)
- Dielectric class equivalence rules
- Footprint identity checks
- Lifecycle and compliance gates
- Criticality classification (safety-critical part detection)
- Substitution tier assignment (0–3)
- `PolicyResult` emission for every rule evaluated

**Done when:** a curated set of known-bad substitutions is rejected with the correct
reason, and known-good ones pass at the correct tier.

## M4 — Sourcing against fixtures

- `SupplierAdapter` protocol
- `FixtureAdapter` + realistic catalog snapshots for the golden BOMs
- Requirement → parametric query expansion
- Candidate assembly, dedup by MPN, manufacturer name normalization
- `evaluate` stage: rationale generation with schema-validated output

**Done when:** a golden BOM produces ranked, policy-clean candidates with rationale,
fully offline.

## M5 — Planning and export

- Price-break and MOQ/SPQ order-quantity solver
- Assembly attrition for passives
- Shipping thresholds and per-supplier subtotals
- Decision modes: `lowest_cost`, `fastest_delivery`, `fewest_suppliers`, `balanced`,
  `lowest_risk`
- Multi-supplier split optimization
- Exporters for Mouser, DigiKey, Farnell (CSV/XLSX) with formula-injection neutralizing
- Plan hashing and snapshot pinning

**Done when:** the same inputs produce byte-identical plans and export files across
runs and machines.

## M6 — Web application

- FastAPI: projects, runs, artifacts, approvals
- Upload → mapping confirmation → requirement resolution → candidate review →
  plan comparison → approval → export
- Per-line evidence display: policy results, datasheet links, snapshot age
- Stale-offer indicators and one-click re-validation
- PostgreSQL persistence, append-only approval ledger
- Project-scoped authorization on every artifact read

**Done when:** an engineer completes a real BOM without touching the CLI.

## M7 — Live supplier adapters

- Mouser, DigiKey, Farnell adapters behind the existing protocol
- Credential handling via secret store
- Rate limiting, retry with backoff, circuit breaking
- Snapshot writing on every live fetch
- Freshness policy and pre-export re-validation

**Done when:** flipping `sourcing.adapters` from fixture to live changes no code
upstream of `source`.

## M8 — Evals and hardening

- Golden-BOM regression suite with scored expectations
- Prompt regression tracking for the two LLM call sites
- Coverage metrics: % rows auto-normalized, % requirements filled at tier 0/1
- Run replay tooling and artifact diffing
- Observability: per-stage timing, adapter error rates, LLM fallback rate

**Done when:** a prompt or rule change reports a measurable delta before merge.

## Sequencing notes

- M3 before M4 is deliberate. Sourcing without policy produces candidate lists that
  look impressive and are quietly unsafe.
- M5 before M6 keeps procurement math out of the UI layer permanently.
- M7 last means the volatile part of the system is the last thing introduced, on top
  of a suite that already proves correctness offline.
