---
description: "Roadmap factory step 2/9 — M1 Ingest. Builds BOM readers, EDA profile detection, and column mapping, then stops for review before handing off to M2."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M1 — Ingest

Read `docs/roadmap.md` (section "M1 — Ingest") first. Confirm M0 is complete — if the
contracts and stage protocol don't exist yet, stop and say so instead of proceeding.

## Scope for this milestone

- CSV / XLSX / XLS readers with hardened parsing
- EDA profile detection for Altium, KiCad, Eagle/Fusion, OrCAD/Allegro
- Column mapping engine: profile match → heuristic match → LLM fallback
- Reference designator expansion and validation (`R1-R4`, `C1,C3`, `U1`)
- Quantity reconciliation against refdes count, with mismatch flagged not fixed
- Mapping profiles persisted per project

**Done when:** all sample BOMs in `fixtures/boms/` ingest with correct refdes counts,
and an unknown-format file produces a mapping proposal rather than an error.

## Process

1. Use `runSubagent` with `agentName: "fixture-curator"` to build or extend
   `fixtures/boms/` with sample exports for Altium, KiCad, Eagle/Fusion, OrCAD/Allegro,
   plus at least one adversarial/unknown-format file and refdes edge cases
   (`R1-R4`, `C1,C3`, ranges with gaps, quantity mismatches).
2. Use `runSubagent` with `agentName: "stage-builder"` to implement the `ingest/`
   stage: readers, profile detection, the three-tier column mapping engine, refdes
   expansion/validation, quantity reconciliation, and per-project mapping profile
   persistence.
3. Run the tests against every fixture and confirm the done-when criterion, including
   the unknown-format-produces-a-proposal case.

## Review gate — STOP HERE

Summarize what was created, show the test results per fixture, and flag any BOM that
didn't ingest cleanly. **Do not start M2.** Wait for the user's explicit approval.

Once approved, tell the user to run `/roadmap-m2-normalize-classify` to continue.
