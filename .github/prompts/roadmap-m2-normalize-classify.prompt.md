---
description: "Roadmap factory step 3/9 — M2 Normalization and classification. Builds the value parser, package code recognition, and category router, then stops for review before handing off to M3."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M2 — Normalization and classification

Read `docs/roadmap.md` (section "M2 — Normalization and classification") first.
Confirm M1 is complete — if ingest doesn't yet produce a clean requirement artifact,
stop and say so instead of proceeding.

## Scope for this milestone

- Value parser: SI prefixes, EIA shorthand (`4k7`, `100n`, `R47`), tolerance suffixes
- Package code recognition: imperial/metric passives, SOT/SOIC/QFN/BGA families
- Dielectric, lifecycle, and compliance token extraction from descriptions
- Category router with per-category required-parameter validation
- Confidence scoring and `unresolved` population
- LLM fallback for unparseable rows

**Done when:** golden BOMs normalize with zero silent errors; every ambiguity appears
in `unresolved` instead of being guessed.

## Process

1. Use `runSubagent` with `agentName: "fixture-curator"` to extend the golden BOMs
   with the messy value/package/token edge cases this milestone must survive (odd EIA
   shorthand, ambiguous tolerances, unknown package codes, conflicting compliance
   tokens).
2. Use `runSubagent` with `agentName: "stage-builder"` to implement the `normalize/`
   and `classify/` stages: the value parser, package code recognition, dielectric /
   lifecycle / compliance extraction, category router with required-parameter
   validation, confidence scoring, and `unresolved` population plus LLM fallback.
3. Run the golden-BOM tests and confirm no ambiguity was silently guessed — every one
   must land in `unresolved`.

## Review gate — STOP HERE

Summarize what was created, show the golden-BOM results, and list any row that
required a guess instead of an `unresolved` entry. **Do not start M3.** Wait for the
user's explicit approval.

Once approved, tell the user to run `/roadmap-m3-policy` to continue.
