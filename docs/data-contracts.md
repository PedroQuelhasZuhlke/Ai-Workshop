# Data Contracts

The contract layer is the spine of the system. Every pipeline stage consumes one
contract type and emits another. Stages are replaceable; contracts are not.

All models live in `src/pcbpick/contracts/` as Pydantic v2 models and are exported to
JSON Schema in `contracts/schema/v<N>/` for the frontend and for cross-version
validation of stored run artifacts.

## Flow

```
RawBomFile
  -> BomLine[]                (ingest)
  -> NormalizedRequirement[]  (normalize + classify)
  -> SourcingQuery[]          (requirement expansion)
  -> PartCandidate[]          (sourcing)
  -> PartCandidate[]          (policy filter + tiering)
  -> SupplierOffer[]          (offer resolution)
  -> PurchasePlan[]           (planning, one per decision mode)
  -> SupplierExport[]         (export, after approval)
```

## Core types

### `BomLine`
Faithful representation of one row as it appeared in the source file. Never cleaned.

| Field | Type | Notes |
|---|---|---|
| `row_index` | `int` | Position in source file |
| `raw` | `dict[str, str]` | Original cells, keyed by original header |
| `reference_designators` | `list[str]` | Split and expanded (`R1-R4` → `R1,R2,R3,R4`) |
| `quantity` | `int \| None` | As stated; recomputed from refdes count during normalization |
| `source_file` | `str` | |
| `mapping_profile` | `str` | Which EDA profile produced this mapping, or `"unknown"` |
| `populate` | `bool` | `False` for a DNP / do-not-populate line — kept in the artifact, excluded from sourcing |

`raw` is retained for the life of the run. It is the audit anchor.

### `ColumnMapping` / `MappingProposal` / `IngestResult`
How the `ingest` stage resolved (or failed to resolve) the columns `BomLine` needs.

| Field | Type | Notes |
|---|---|---|
| `ColumnMapping.target_field` | `str` | `reference_designators` \| `quantity` \| `populate` |
| `ColumnMapping.source_column` | `str \| None` | `None` when unresolved |
| `ColumnMapping.method` | `MappingMethod` | `profile` \| `project_memory` \| `heuristic` \| `llm_fallback` \| `unresolved` |
| `ColumnMapping.confidence` | `float` | `0.0`–`1.0` |
| `MappingProposal.eda_profile` | `str \| None` | Matched profile name, or `None` |
| `MappingProposal.header_row_index` | `int` | Row the real header was found on |
| `MappingProposal.mappings` | `list[ColumnMapping]` | One per target field |
| `MappingProposal.missing_required_fields` | `list[str]` | Non-empty blocks the file from proceeding unattended |
| `MappingProposal.requires_confirmation` | `bool` | Always surfaced in the UI regardless of which tier resolved it |
| `IngestResult.lines` | `list[BomLine]` | |
| `IngestResult.mapping_proposal` | `MappingProposal` | |

`ingest` never guesses: an unresolved required field produces `MappingProposal` with
`requires_confirmation=True` and empty `reference_designators`/`quantity` on every
affected line, not an exception and not an inferred column.

### `NormalizedRequirement`
What the design actually needs, independent of any supplier.

| Field | Type | Notes |
|---|---|---|
| `requirement_id` | `str` | Stable within a run |
| `reference_designators` | `list[str]` | |
| `quantity_per_board` | `int` | Derived from refdes count |
| `category` | `ComponentCategory` | Enum — see below |
| `parameters` | `dict[str, ParameterValue]` | Category-specific, SI base units |
| `footprint` | `Footprint` | Package code + mounting + dimensions if known |
| `specified_mpn` | `MpnRef \| None` | Designer's chosen part, if any |
| `criticality` | `Criticality` | `standard` \| `safety` \| `do_not_substitute` |
| `compliance_required` | `list[ComplianceTag]` | RoHS, REACH, AEC-Q200, ... |
| `notes` | `str \| None` | Free text from the BOM |
| `confidence` | `Confidence` | Normalization confidence + reasons |
| `unresolved` | `list[str]` | Fields that need engineer input |

A requirement with a non-empty `unresolved` list must not proceed to sourcing without
engineer action. It is surfaced in the UI, not silently dropped.

### `ParameterValue`
Every parameter is a value with provenance, not a bare number.

| Field | Type |
|---|---|
| `value` | `Decimal \| None` |
| `unit` | `str` (SI base, e.g. `ohm`, `farad`, `henry`, `volt`, `watt`) |
| `tolerance_pct` | `Decimal \| None` |
| `min` / `max` | `Decimal \| None` — for range requirements |
| `raw_text` | `str` — exactly as it appeared |
| `source` | `parsed` \| `llm_inferred` \| `engineer_entered` \| `datasheet` |

`llm_inferred` values are always flagged in the UI and never satisfy a hard policy
check on their own.

### `ComponentCategory`
`resistor`, `capacitor`, `inductor`, `ferrite_bead`, `diode`, `led`, `transistor`,
`ic_analog`, `ic_digital`, `ic_power`, `ic_rf`, `crystal`, `oscillator`, `connector`,
`switch`, `relay`, `fuse`, `transformer`, `mechanical`, `module`, `unknown`.

Each category declares its required and optional parameters in
`src/pcbpick/contracts/categories.py`. Normalization validates against that declaration.

### `PartCandidate`
A specific manufacturer part proposed against a requirement.

| Field | Type | Notes |
|---|---|---|
| `requirement_id` | `str` | |
| `mpn` | `str` | |
| `manufacturer` | `str` | Normalized name |
| `parameters` | `dict[str, ParameterValue]` | From catalog/datasheet |
| `footprint` | `Footprint` | |
| `lifecycle` | `Lifecycle` | `active` \| `nrnd` \| `eol` \| `obsolete` \| `unknown` |
| `compliance` | `list[ComplianceTag]` | |
| `substitution_tier` | `SubstitutionTier` | 0–3, see policy docs |
| `policy_results` | `list[PolicyResult]` | Every rule evaluated, pass/fail + reason |
| `rationale` | `str \| None` | LLM-authored, human-readable |
| `evidence` | `list[Evidence]` | Datasheet URL, catalog field, snapshot id |
| `offers` | `list[SupplierOffer]` | |

`policy_results` is exhaustive by design — engineers need to see what was checked,
including what passed.

### `SupplierOffer`
A purchasable line from one supplier, at one point in time.

| Field | Type | Notes |
|---|---|---|
| `supplier` | `SupplierId` | `mouser` \| `digikey` \| `farnell` \| `fixture` |
| `sku` | `str` | Supplier order number |
| `packaging` | `Packaging` | `cut_tape` \| `reel` \| `tube` \| `tray` \| `bulk` |
| `stock` | `int \| None` | |
| `moq` | `int` | Minimum order quantity |
| `spq` | `int` | Standard pack quantity — order must be a multiple |
| `price_breaks` | `list[PriceBreak]` | `(qty, unit_price, currency)` ascending |
| `lead_time_days` | `int \| None` | For non-stock |
| `snapshot_id` | `str` | Which catalog snapshot this came from |
| `fetched_at` | `datetime` | UTC |

An offer older than the configured freshness window is marked stale and must be
re-fetched before it can appear in an approved export.

### `PurchasePlan`
One complete way to buy the whole BOM.

| Field | Type | Notes |
|---|---|---|
| `mode` | `DecisionMode` | See below |
| `board_quantity` | `int` | |
| `attrition_pct` | `Decimal` | Assembly overage applied to passives |
| `lines` | `list[PlanLine]` | requirement → candidate → offer → order qty |
| `totals` | `PlanTotals` | Per-supplier subtotal, shipping, grand total, currency |
| `longest_lead_time_days` | `int` | Gates the build date |
| `supplier_count` | `int` | |
| `unfilled` | `list[UnfilledRequirement]` | With the reason it could not be filled |
| `warnings` | `list[PlanWarning]` | Stale offers, NRND parts, tier-2+ substitutions |
| `snapshot_ids` | `list[str]` | Every snapshot the plan depends on |

### `DecisionMode`
`lowest_cost`, `fastest_delivery`, `fewest_suppliers`, `balanced`,
`lowest_risk` (prefers active lifecycle, high stock, tier-0/1 only).

Modes are scoring configurations over the same candidate matrix, implemented as pure
functions in `src/pcbpick/planning/`. Adding a mode must not require touching any
other stage.

### `SupplierExport`
The final artifact. Generated only from an approved plan.

| Field | Type |
|---|---|
| `supplier` | `SupplierId` |
| `format` | `csv` \| `xlsx` |
| `rows` | `list[dict[str, str]]` |
| `approved_by` | `str` |
| `approved_at` | `datetime` |
| `plan_hash` | `str` — hash of the plan this was generated from |

## Versioning rules

- Contracts are versioned as a set: `schema_version` on every run artifact.
- Additive optional fields → minor bump, no migration.
- Removing, renaming, or retyping a field → major bump plus a migration for stored
  run artifacts and a refresh of all fixtures and evals.
- Never reuse a field name with different semantics. Add a new one and deprecate.
