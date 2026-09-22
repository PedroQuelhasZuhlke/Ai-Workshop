# Decision Log — Harness Design Session

**Date:** 2026-09-22
**Scope:** Initial design of the PCB parts picking tool, creation of the agent-facing
harness, the roadmap-to-agent factory prompts, and execution of milestone M0.
**Status:** Harness resources created; roadmap factory prompts created; M0 (contracts
and skeleton) implemented and verified, awaiting user review before M1.

---

## 1. Starting point

The only input was [pcb-parts-picking-ai-framework-summary.md](../pcb-parts-picking-ai-framework-summary.md),
which described a workshop-oriented concept: ingest a PCB BOM, classify parts, query
supplier catalogs, generate candidates with justification, compare purchasing
strategies, export supplier-friendly files.

**Reframing decision:** the workshop framing was explicitly dropped. The system is now
treated as an internal production tool used by electrical engineers to make real
purchasing decisions. This raised the bar on auditability, safety, and reproducibility
and drove nearly every subsequent decision.

## 2. Requirements elicited

| Question | Answer | Consequence |
|---|---|---|
| Language / runtime | **Python** | Pydantic v2 + FastAPI + pandas/openpyxl stack |
| Supplier data access | **None yet — fixtures first** | `SupplierAdapter` protocol defined now, `FixtureAdapter` built first, live adapters deferred to M7 |
| User interface | **Internal web app** | FastAPI + React; UI is a review-and-approval surface, not a dashboard |
| BOM sources | **Altium, KiCad, Eagle/Fusion, OrCAD/Allegro, plus ad-hoc CSV/Excel** | Column mapping is the hard problem, not parsing; needs profiles + heuristics + LLM fallback + engineer confirmation |
| Approved-parts list / ERP | **None, and out of scope** | The normalized requirement model becomes the de-facto parts vocabulary; contracts carry more weight |

## 3. Core architectural decision

**"The model reasons; the code decides."**

| Deterministic code | LLM permitted |
|---|---|
| All arithmetic (price, quantity, derating) | Interpreting an ambiguous BOM row |
| Ranking and plan selection | Mapping unknown column headers |
| Hard policy filters | Explaining why a candidate fits |
| Export file generation | Summarizing trade-offs |
| Stock, MOQ, SPQ, lead-time handling | Extracting parameters from free text |

Rationale: a procurement recommendation that cannot be reproduced byte-for-byte from
stored inputs is a defect. Exactly two LLM call sites are sanctioned
(`normalize_fallback`, `candidate_rationale`); a third requires a documented decision.

**Supporting decision:** the `policy` stage runs *before* the `evaluate` stage, so the
model never sees a candidate that violates an engineering rule and therefore cannot
argue for one.

## 4. Non-negotiable invariants agreed

1. A substitution may never reduce tolerance, voltage, current, power, or temperature
   rating below the requirement.
2. Footprint/land pattern must match exactly unless the engineer approves a design change.
3. Safety-critical parts (fuses, X/Y-class capacitors, optocouplers, isolation barriers,
   creepage-dependent parts) are never auto-substituted — agency approvals are part-specific.
4. AEC-Q100/Q200 qualification and RoHS/REACH compliance may never regress. Unknown fails closed.
5. Every supplier fact carries `snapshot_id` and `fetched_at`; stock and price are volatile
   and re-validated before export.
6. Nothing reaches an export file without a recorded engineer approval.

**Provenance rule:** if a value cannot be attributed to a source, it is `None` — never
inferred, never silently defaulted.

## 5. Design decisions with rationale

| Decision | Rationale |
|---|---|
| Pure stage pipeline, artifact per stage in `runs/<run_id>/` | Resumability and replay. An engineer reports a bad recommendation months later; the exact run is reconstructable. |
| Snapshot-addressed catalog storage, not a TTL cache | A cache that expires destroys the audit trail. Snapshots are retained and pinned per run. |
| Policy engine before LLM evaluation | Makes unsafe recommendations structurally impossible rather than merely unlikely. |
| Decision modes as pure scoring functions | Adding a mode must not touch any other stage; plan selection stays auditable. |
| `Decimal` + explicit ISO 4217 currency everywhere | Float money is a defect class; silent currency conversion is worse. |
| Unknown is `None`, never `0`/`""`/`"N/A"` | `stock`, `moq`, `spq` are load-bearing procurement values; a default produces quotes that do not match the invoice. |
| Derating factors in versioned config, not code | They are policy requiring engineering sign-off, not physics. Active version recorded in every run artifact. |
| Fixtures-first sourcing | Correctness is proved offline before the volatile part of the system is introduced. |
| Eval case required for any behavior change | The only mechanism that keeps rule and prompt tuning honest. |

## 6. Domain knowledge captured

Packaged into skills so agents inherit it rather than rediscovering it:

- **Column mapping ambiguity** — `Comment` vs `Description` both holding the value;
  `Part` meaning designator in Eagle and part number elsewhere; OrCAD `Part Number`
  being an internal number, not an MPN.
- **Reference designator prefix collisions** — `T` (transistor/transformer),
  `X` (crystal/connector), `CN` (capacitor network/connector), `RV` (varistor/variable resistor).
- **The 0603 trap** — imperial `0603` is 1.6 × 0.8 mm, metric `0603` is imperial `0201`.
  A silent misread is a 5× dimension error. Resolution system must be recorded.
- **Tolerance letter codes differ between resistors and capacitors** — `B`/`C`/`D` are
  absolute picofarads on capacitors and percentages on resistors. Category must be known first.
- **Dielectric classes** — Class I ↔ Class II substitution is a hard fail; Class II
  MLCCs lose substantial capacitance under DC bias, worse in smaller packages, so a
  case-size reduction at equal value and voltage is *not* a drop-in.
- **"Better" is not always safe** — lower ESR can destabilize an LDO requiring minimum
  ESR; crystal load capacitance mismatch prevents start-up. Windowed parameters are
  hard constraints in both directions.

---

## 7. M1 — Ingest (2026-09-22)

**Scope implemented:** hardened CSV/XLSX readers, header-row detection, EDA profile
matching (Altium, KiCad modern/legacy, Eagle/Fusion, OrCAD/Allegro), a four-tier
column-mapping engine, reference-designator expansion/validation, quantity
reconciliation, DNP handling, and per-project mapping persistence.

**Contract additions:** `ColumnMapping`, `MappingProposal`, `IngestResult` (the
`ingest` stage's actual output — `BomLine[]` plus the mapping that produced them);
`MappingMethod` enum; `BomLine.populate: bool = True` (additive, default preserves
existing semantics). `architecture.md`'s stage table updated to match.

**Decision: column-mapping LLM fallback deferred, not skipped.** The roadmap calls
for a three-tier mapping engine ending in an LLM fallback. `llm-calls.instructions.md`
sanctions exactly two call sites (`normalize_fallback`, `candidate_rationale`) and
requires a documented decision to add a third — and no `src/pcbpick/llm/` package,
provider client, or prompt-template infrastructure exists yet (that lands with
`normalize`'s fallback in M2). Building a third live call site ahead of that
plumbing, untested against a real provider, would violate "structured output only"
and "no live model calls in tests" for a feature nothing yet depends on. Resolution:
the mapping engine has four tiers — profile → project memory → heuristic → LLM
fallback — where the last is a documented extension point (`MappingMethod.LLM_FALLBACK`
exists in the enum, resolution falls through to `UNRESOLVED` today). When M2 wires
`src/pcbpick/llm/`, column-mapping can reuse that plumbing instead of duplicating it.
An unresolved required field never blocks the pipeline with an exception — it
produces a `MappingProposal` with `requires_confirmation=True` and empty
`reference_designators`/`quantity`, exactly the "propose, never guess" behavior the
`bom-ingest` skill requires.

**Decision: mapping-profile persistence is read-through only in M1.** `pcbpick run`
accepts an optional `--project-id` that loads a previously confirmed mapping via
`MappingProfileStore` (JSON on disk, keyed by project id) so a repeat BOM revision
resolves at `MappingMethod.PROJECT_MEMORY` confidence instead of re-guessing. The
store's `save()` is not called anywhere yet — persisting an *unconfirmed* heuristic
guess as though an engineer approved it would itself be a guess. Wiring `save()` to
an actual confirmation action is a M6 (web app) concern.

**Decision: `.xls` (legacy binary) reader deferred.** The roadmap lists CSV/XLSX/XLS.
No fixture exercises `.xls` and no library in the dependency set parses it without
adding `xlrd` for a code path nothing tests. `readers.read_grid` raises
`IngestFileError` for it today rather than shipping unexercised code.

- **Tantalum voltage derating (≤50%)** reflects an ignition failure mode.
- **SPQ is independent of MOQ** — suppliers ship whole packs; ignoring SPQ produces
  quotes that do not match the invoice.
- **Break-point buy-up** — ordering more is sometimes cheaper in total, but is proposed
  explicitly, never applied silently, because surplus inventory is a cost the tool cannot see.
- **CSV formula injection** — cells beginning `=`, `+`, `-`, `@`, tab, CR are an
  injection path into whoever opens the export. All cells neutralized, including
  system-generated ones sourced from supplier catalogs.

## 7. Artifacts created

**Always-on context**
- [.github/copilot-instructions.md](../.github/copilot-instructions.md)

**Specifications**
- [docs/data-contracts.md](./data-contracts.md) — artifact types, provenance, versioning rules
- [docs/architecture.md](./architecture.md) — stage graph, adapter protocol, LLM boundary, security posture
- [docs/roadmap.md](./roadmap.md) — milestones M0–M8

**Path-scoped instructions**
- [python.instructions.md](../.github/instructions/python.instructions.md) — `**/*.py`
- [contracts.instructions.md](../.github/instructions/contracts.instructions.md) — `src/pcbpick/contracts/**`
- [pipeline-stages.instructions.md](../.github/instructions/pipeline-stages.instructions.md) — stage packages
- [supplier-adapters.instructions.md](../.github/instructions/supplier-adapters.instructions.md) — `src/pcbpick/sourcing/suppliers/**`
- [llm-calls.instructions.md](../.github/instructions/llm-calls.instructions.md) — `src/pcbpick/llm/**`
- [testing.instructions.md](../.github/instructions/testing.instructions.md) — `{tests,evals,fixtures}/**`

**Skills**
- `bom-ingest` + `references/eda-export-profiles.md`
- `part-normalization` + `references/value-notation.md`
- `substitution-policy` + `references/category-rules.md`
- `procurement-math`
- `supplier-export`

**Agents**
- `contract-architect`, `stage-builder`, `supplier-adapter-builder`, `fixture-curator`, `invariant-auditor`

## 8. Open items and risks

| Item | Status | Owner |
|---|---|---|
| Derating factors in `category-rules.md` are **proposed defaults** | Require engineering authority sign-off before first production use; must move to versioned `config/derating.yaml` | Engineering |
| Supplier upload column templates (Mouser, DigiKey, Farnell) | **Unverified** — must be checked against current published templates and stored with a verified-date | Whoever builds M5 exporters |
| Supplier API credentials | Not yet available; gates M7 | — |
| Package-system convention per EDA tool | Needs confirmation for tools that do not state `Metric` or use IPC prefixes | Engineering |
| Currency handling across suppliers | Decision recorded (no silent conversion) but exchange-rate source not chosen | — |
| Duties and VAT | Out of scope by default; totals must be explicitly labelled as excluding them | — |
| Assembly attrition defaults | Proposed (10% / 5% / 0% by part class with minimum extra pieces); needs sign-off | Engineering |

## 9. Sequencing rationale

- **M3 (policy) before M4 (sourcing)** — sourcing without policy produces candidate
  lists that look impressive and are quietly unsafe.
- **M5 (planning) before M6 (web app)** — keeps procurement math out of the UI layer permanently.
- **M7 (live adapters) last** — the volatile part of the system is introduced on top of
  a suite that already proves correctness offline.

## 10. Next action

M1 — Ingest (BOM readers, EDA profile detection, column mapping). Not started. Run
`/roadmap-m1-ingest` once M0 is reviewed and approved.

## 11. Roadmap-to-agent mapping

Each roadmap milestone was mapped to the custom agent(s) that own its scope:

| Milestone | Primary agent(s) |
|---|---|
| M0 — Contracts and skeleton | `contract-architect` (contracts only; stage protocol/CLI built directly, no agent owns runner scaffolding) |
| M1 — Ingest | `fixture-curator` (sample BOMs) → `stage-builder` (ingest stage) |
| M2 — Normalization and classification | `fixture-curator` → `stage-builder` |
| M3 — Policy engine | `fixture-curator` → `stage-builder` → `invariant-auditor` (safety-core review) |
| M4 — Sourcing against fixtures | `supplier-adapter-builder` (protocol + `FixtureAdapter`) → `fixture-curator` (catalog snapshots) → `stage-builder` (evaluate stage) |
| M5 — Planning and export | `stage-builder` → `invariant-auditor` (money/export-injection review) |
| M6 — Web application | No dedicated pcbpick agent — built directly; contract/stage-shaped pieces delegated out; `invariant-auditor` reviews authorization |
| M7 — Live supplier adapters | `supplier-adapter-builder` → `invariant-auditor` (credential/network review — highest risk milestone) |
| M8 — Evals and hardening | `fixture-curator` (golden-BOM suite) → `stage-builder` (replay/observability) → `invariant-auditor` (full audit) |

Rule of thumb recorded for future milestones: `contracts/` → `contract-architect`;
any of `ingest/normalize/classify/policy/sourcing/planning/exporters/pipeline` →
`stage-builder`; `sourcing/suppliers/` → `supplier-adapter-builder`; test
data/eval cases → `fixture-curator`; safety/determinism review → `invariant-auditor`.

## 12. Roadmap factory prompts

Nine chained prompt files were created in `.github/prompts/`, one per milestone:
`roadmap-m0-contracts-skeleton.prompt.md` through `roadmap-m8-evals-hardening.prompt.md`.

Each prompt:
- reads the matching roadmap section and checks the prior milestone is actually done
  before starting
- delegates to the milestone's owning agent(s) (section 11) via `runSubagent`, in order
- runs an `invariant-auditor` pass where safety, money, or security risk is highest
- ends with an explicit **STOP** review gate — never auto-continues — and names the
  exact next slash command to run once the user approves

This turns the roadmap into a manually-gated pipeline: one milestone per session,
reviewed by the user before the next is started. Recorded in repo memory
(`/memories/repo/roadmap-factory.md`) so future sessions know the chain exists.

## 13. M0 execution evidence

**Scaffold built directly** (no agent owns pipeline/CLI scaffolding):
- `pyproject.toml` — uv + hatchling, `[dependency-groups] dev` (pytest, ruff, mypy,
  jsonschema), ruff/mypy config
- `.gitignore`, `.github/workflows/ci.yml` (uv sync → ruff → mypy → pytest)
- `src/pcbpick/errors.py` — `PcbPickError`, `RunNotFoundError`, `StageNotFoundError`,
  `ContractViolationError`
- `src/pcbpick/pipeline/` — `context.py` (`StageContext`, `PipelineConfig`),
  `results.py` (`Severity`, `StageIssue`, `StageResult`), `stage.py` (`Stage`
  protocol), `models.py` (`RunManifest`, `StageMeta`), `runner.py`
  (`PipelineRunner`, empty `STAGES` list — first entries land in M1)
- `src/pcbpick/cli.py` — `pcbpick run <file>`, `pcbpick resume <run_id> --from <stage>`
- `tests/pipeline/test_runner.py`, `tests/unit/test_cli.py`

**Contract layer delegated to `contract-architect`** under `src/pcbpick/contracts/`:
all enums (`ComponentCategory`, `SupplierId`, `Lifecycle`, `Packaging`,
`SubstitutionTier`, `Criticality`, `ComplianceTag`, `DecisionMode`, `ValueSource`, plus
`MountingType`/`ExportFormat`/`PlanWarningKind`); core models (`BomLine`,
`NormalizedRequirement`, `ParameterValue`, `PartCandidate`, `SupplierOffer`,
`PurchasePlan` + `PlanLine`/`PlanTotals`/`UnfilledRequirement`/`PlanWarning`,
`SupplierExport`, `PolicyResult`, `Footprint`, `MpnRef`, `Confidence`, `Evidence`,
`PriceBreak`); `categories.py` (required/optional parameters per category);
`version.py` (`SCHEMA_VERSION = "v1"`); JSON Schema generated and committed under
`src/pcbpick/contracts/schema/v1/` via `export_schema.py`; `migrations/` placeholder.
All models `frozen=True, extra="forbid"`, `Decimal` for money/physical quantities,
`snapshot_id`/`fetched_at` mandatory on `SupplierOffer`. Tests added under
`tests/contracts/` (round-trip, frozen/forbid-extra, schema-matches-regeneration).

**Fixes applied during verification** (found by running the real toolchain, not by
inspection alone):
- 3 ruff violations in the hand-written pipeline code — `StrEnum` instead of
  `str, Enum`, PEP 695 generic syntax (`class StageResult[OutputT]`) instead of
  `Generic[TypeVar]`, `datetime.UTC` instead of `datetime.timezone.utc`
- Missing `tests/__init__.py` and subpackage `__init__.py` files — contract tests use
  `from tests.contracts.conftest import ...`, which failed collection without them
- `[tool.uv] dev-dependencies` (deprecated) migrated to `[dependency-groups] dev`

**Verification performed** (via `uv`, per the project's "no bare `pip`" convention):
- `uv sync` — resolved and installed cleanly
- `uv run ruff check .` — all checks passed
- `uv run mypy` (strict) — no issues in 23 source files
- `uv run pytest -q` — **95/95 passed**, including the 7 pipeline/CLI tests
- Manual CLI walkthrough: `pcbpick run <sample.csv>` created
  `runs/<run_id>/meta.json` with correct `source_file_sha256` and empty `stages: []`;
  `pcbpick resume <run_id> --from ingest` failed cleanly with `StageNotFoundError`
  (no stages registered yet), confirming the resume plumbing without real stage logic

**Done-when criterion met:** an empty pipeline runs end to end and writes artifacts.
Nothing was committed or pushed to git — file changes only, pending user review.
