---
description: "Roadmap factory step 6/9 — M5 Planning and export. Builds order-quantity math, decision modes, and supplier exporters, audits money handling, then stops for review before handing off to M6."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M5 — Planning and export

Read `docs/roadmap.md` (section "M5 — Planning and export") first. Confirm M4 is
complete — if ranked, policy-clean candidates don't exist yet, stop and say so instead
of proceeding.

## Scope for this milestone

- Price-break and MOQ/SPQ order-quantity solver
- Assembly attrition for passives
- Shipping thresholds and per-supplier subtotals
- Decision modes: `lowest_cost`, `fastest_delivery`, `fewest_suppliers`, `balanced`,
  `lowest_risk`
- Multi-supplier split optimization
- Exporters for Mouser, DigiKey, Farnell (CSV/XLSX) with formula-injection
  neutralizing
- Plan hashing and snapshot pinning

**Done when:** the same inputs produce byte-identical plans and export files across
runs and machines.

## Process

1. Use `runSubagent` with `agentName: "stage-builder"` to implement the `planning/`
   stage (price-break/MOQ/SPQ solver, attrition, shipping thresholds, decision modes,
   multi-supplier split, plan hashing) and the `exporters/` stage (Mouser, DigiKey,
   Farnell CSV/XLSX with formula-injection neutralizing).
2. Use `runSubagent` with `agentName: "invariant-auditor"` to review the new code
   specifically for `float` money, non-deterministic ordering, and unsanitized export
   cells (formula injection). Fix anything it flags before moving on.
3. Run the same inputs twice (ideally on two different runs/machines if feasible) and
   diff the plan and export outputs to confirm byte-identical determinism.

## Review gate — STOP HERE

Summarize what was created, show a sample plan per decision mode, and report the
invariant-auditor findings and how each was resolved. **Do not start M6.** Wait for the
user's explicit approval.

Once approved, tell the user to run `/roadmap-m6-web-app` to continue.
