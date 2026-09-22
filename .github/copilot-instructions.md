# PCB Parts Picking — Internal Engineering Tool

## What this is

An internal tool for electrical engineers that turns a PCB bill of materials into
reviewed, sourceable purchasing options. It ingests EDA exports, normalizes component
requirements, finds candidate parts across supplier catalogs, applies engineering
policy, and produces comparable purchase plans plus supplier-ready import files.

**It is a decision-support tool, not an autonomous purchaser.** Every output is a
proposal that a named engineer reviews and approves.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Models / validation | Pydantic v2 |
| API | FastAPI |
| Frontend | React + TypeScript (Vite) |
| Persistence | PostgreSQL (runs, approvals, cached offers) |
| Tables / parsing | pandas, openpyxl |
| Tests | pytest |
| Package / env | uv |

## Repository layout

```
src/pcbpick/
  contracts/      # Pydantic models + JSON Schema. Source of truth.
  ingest/         # File readers, EDA profiles, column mapping
  normalize/      # Unit/value parsing, package codes, dedup
  classify/       # Category routing
  policy/         # Derating, compatibility, substitution tiers, compliance gates
  sourcing/       # Candidate search
    suppliers/    # SupplierAdapter implementations
  planning/       # Price breaks, MOQ/SPQ, attrition, multi-supplier optimization
  exporters/      # Supplier BOM import formats
  pipeline/       # Stage runner, run artifacts, resume/replay
  api/            # FastAPI routes
  llm/            # Prompt templates, structured-output calls, validation retries
web/              # React frontend
fixtures/         # Offline catalog snapshots, sample + golden BOMs
evals/            # Golden-BOM regression suite
tests/
docs/             # Architecture and contract specs
runs/             # Local run artifacts (gitignored)
```

## The one rule that matters most

**The model reasons; the code decides.**

| Must be deterministic code | May use the LLM |
|---|---|
| Arithmetic of any kind (price, quantity, derating) | Interpreting an ambiguous BOM row |
| Ranking and plan selection | Mapping unknown column headers |
| Hard policy filters | Explaining why a candidate fits |
| Export file generation | Summarizing trade-offs between plans |
| Stock, MOQ, SPQ, lead-time handling | Extracting parameters from free-text descriptions |

If you find yourself asking the model to compute a total, compare prices, or choose a
winner, stop and write a function instead. A procurement recommendation that cannot be
reproduced byte-for-byte from stored inputs is a defect.

## Non-negotiable engineering invariants

1. A substitution may never reduce tolerance, voltage rating, current rating, power
   rating, or temperature range below the requirement.
2. Footprint/land pattern must match exactly unless the engineer explicitly approves
   a design change.
3. Safety-critical parts (fuses, Y/X-class capacitors, optocouplers, isolation
   barriers, creepage-dependent parts) are never auto-substituted — agency approvals
   are part-specific.
4. Qualification (AEC-Q100/Q200) and compliance (RoHS, REACH) may never regress.
5. Every supplier fact carries `snapshot_id` and `fetched_at`. Stock and price are
   always treated as volatile and are re-validated before export.
6. Nothing reaches an export file without a recorded engineer approval.

## Provenance

Every `PartCandidate` and `SupplierOffer` must be traceable to its origin: which
adapter, which snapshot, which query, which datasheet field. If a value cannot be
attributed, it is `None` — never inferred and never silently defaulted.

## Conventions

- Pipeline stages are pure: `(input artifact, config) -> output artifact`. No hidden
  state, no network calls outside `sourcing/suppliers/`.
- Money is `Decimal` with an explicit ISO 4217 currency. Never `float`.
- Physical quantities are stored in SI base units as `Decimal`, with the original
  string preserved for display and audit.
- Unknown is `None`. Do not use `0`, `""`, or `"N/A"` as a stand-in.
- No live network calls in tests. Ever.

## Working agreements for agents

- Read `docs/data-contracts.md` before touching anything in `contracts/`.
- Changing a contract is a breaking change: bump the schema version and update
  fixtures, evals, and dependent stages in the same change.
- Add a golden-BOM eval case alongside any change to normalization, policy, or
  planning behavior.
- Prefer extending an existing stage over adding a new one.
