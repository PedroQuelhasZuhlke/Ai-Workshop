---
description: "Roadmap factory step 5/9 — M4 Sourcing against fixtures. Builds the SupplierAdapter protocol, FixtureAdapter, and candidate evaluation, then stops for review before handing off to M5."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M4 — Sourcing against fixtures

Read `docs/roadmap.md` (section "M4 — Sourcing against fixtures") first. Confirm M3 is
complete — if `PolicyResult`s aren't being emitted yet, stop and say so instead of
proceeding. This ordering (policy before sourcing) is deliberate per the roadmap's
sequencing notes.

## Scope for this milestone

- `SupplierAdapter` protocol
- `FixtureAdapter` + realistic catalog snapshots for the golden BOMs
- Requirement → parametric query expansion
- Candidate assembly, dedup by MPN, manufacturer name normalization
- `evaluate` stage: rationale generation with schema-validated output

**Done when:** a golden BOM produces ranked, policy-clean candidates with rationale,
fully offline.

## Process

1. Use `runSubagent` with `agentName: "supplier-adapter-builder"` to define the
   `SupplierAdapter` protocol and implement `FixtureAdapter` against it.
2. Use `runSubagent` with `agentName: "fixture-curator"` to build realistic catalog
   snapshots (with `snapshot_id` / `fetched_at` provenance) covering the golden BOMs,
   including out-of-stock, multiple price breaks, and near-duplicate MPN cases.
3. Use `runSubagent` with `agentName: "stage-builder"` to implement requirement →
   parametric query expansion, candidate assembly with MPN dedup and manufacturer name
   normalization, and the `evaluate` stage's schema-validated rationale generation.
4. Run the golden-BOM tests offline and confirm every candidate is policy-clean before
   ranking.

## Review gate — STOP HERE

Summarize what was created, show ranked candidates with rationale for a golden BOM,
and confirm no network calls occurred. **Do not start M5.** Wait for the user's
explicit approval.

Once approved, tell the user to run `/roadmap-m5-planning-export` to continue.
