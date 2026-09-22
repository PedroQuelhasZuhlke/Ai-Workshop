---
description: "Roadmap factory step 9/9 — M8 Evals and hardening. Builds the golden-BOM regression suite and observability, runs a full invariant audit, then closes out the roadmap."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M8 — Evals and hardening

Read `docs/roadmap.md` (section "M8 — Evals and hardening") first. Confirm M0–M7 are
complete before starting.

## Scope for this milestone

- Golden-BOM regression suite with scored expectations
- Prompt regression tracking for the two LLM call sites
- Coverage metrics: % rows auto-normalized, % requirements filled at tier 0/1
- Run replay tooling and artifact diffing
- Observability: per-stage timing, adapter error rates, LLM fallback rate

**Done when:** a prompt or rule change reports a measurable delta before merge.

## Process

1. Use `runSubagent` with `agentName: "fixture-curator"` to assemble the golden-BOM
   regression suite with scored expectations, covering every milestone's fixtures
   built so far, plus prompt regression cases for the two LLM call sites (column
   mapping fallback, normalization fallback).
2. Use `runSubagent` with `agentName: "stage-builder"` to implement run replay
   tooling, artifact diffing, coverage metrics, and per-stage/observability
   instrumentation in `pipeline/`.
3. Use `runSubagent` with `agentName: "invariant-auditor"` to run a full-codebase
   audit — this is the last gate before the roadmap is considered hardened. Fix
   anything it flags.
4. Make a small, deliberate rule or prompt change and confirm the eval suite reports a
   measurable delta, satisfying the done-when criterion.

## Review gate — STOP HERE

Summarize what was created, show the eval suite's baseline scores, and report the
final invariant-auditor findings and how each was resolved. This is the last milestone
in the roadmap — confirm with the user before considering the roadmap complete.
