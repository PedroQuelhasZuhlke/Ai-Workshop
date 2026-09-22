---
description: "Roadmap factory step 4/9 — M3 Policy engine. Builds derating, substitution tiers, and compliance gates, audits them for safety invariants, then stops for review before handing off to M4."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M3 — Policy engine

Read `docs/roadmap.md` (section "M3 — Policy engine") first. Confirm M2 is complete —
if normalized/classified requirements don't exist yet, stop and say so instead of
proceeding.

This milestone builds the safety core of the system: read
`.github/copilot-instructions.md` invariants 1–4 again before starting.

## Scope for this milestone

- Derating rules per category (voltage, power, current, temperature)
- Dielectric class equivalence rules
- Footprint identity checks
- Lifecycle and compliance gates
- Criticality classification (safety-critical part detection)
- Substitution tier assignment (0–3)
- `PolicyResult` emission for every rule evaluated

**Done when:** a curated set of known-bad substitutions is rejected with the correct
reason, and known-good ones pass at the correct tier.

## Process

1. Use `runSubagent` with `agentName: "fixture-curator"` to build the curated
   known-bad / known-good substitution cases this milestone is scored against,
   including at least one safety-critical part (fuse, Y/X-class cap, optocoupler,
   isolation barrier) that must never auto-substitute.
2. Use `runSubagent` with `agentName: "stage-builder"` to implement the `policy/`
   stage: derating rules, dielectric equivalence, footprint identity checks, lifecycle
   and compliance gates, criticality classification, substitution tier assignment, and
   `PolicyResult` emission for every rule evaluated.
3. Use `runSubagent` with `agentName: "invariant-auditor"` to review the new policy
   code specifically for violations of invariants 1–4 (tolerance/rating/temperature
   regressions, footprint mismatches, safety-critical auto-substitution, compliance
   regression). This is a read-only review — fix anything it flags before moving on.

## Review gate — STOP HERE

Summarize what was created, show the pass/reject results for every curated case, and
report the invariant-auditor findings and how each was resolved. **Do not start M4.**
Wait for the user's explicit approval.

Once approved, tell the user to run `/roadmap-m4-sourcing-fixtures` to continue.
