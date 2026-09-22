---
description: "Roadmap factory step 7/9 — M6 Web application. Builds the FastAPI + React review/approval flow, audits authorization, then stops for review before handing off to M7."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M6 — Web application

Read `docs/roadmap.md` (section "M6 — Web application") first. Confirm M5 is complete
— if deterministic plans and exports don't exist yet, stop and say so instead of
proceeding.

No pcbpick custom agent owns `api/` or `web/` directly — implement this milestone with
regular tools, following `.github/copilot-instructions.md` and
`.github/instructions/python.instructions.md` throughout. If a change also touches a
contract or a pipeline stage, delegate that specific piece to `contract-architect` or
`stage-builder` via `runSubagent` rather than editing those directories yourself.

## Scope for this milestone

- FastAPI: projects, runs, artifacts, approvals
- Upload → mapping confirmation → requirement resolution → candidate review → plan
  comparison → approval → export
- Per-line evidence display: policy results, datasheet links, snapshot age
- Stale-offer indicators and one-click re-validation
- PostgreSQL persistence, append-only approval ledger
- Project-scoped authorization on every artifact read

**Done when:** an engineer completes a real BOM without touching the CLI.

## Process

1. Implement the FastAPI routes and PostgreSQL persistence (projects, runs, artifacts,
   append-only approval ledger). If any new persisted shape belongs in `contracts/`,
   delegate that piece to `contract-architect` first.
2. Implement the React frontend flow end to end: upload → mapping confirmation →
   requirement resolution → candidate review → plan comparison → approval → export,
   with per-line evidence and stale-offer indicators.
3. Add project-scoped authorization checks on every artifact read.
4. Use `runSubagent` with `agentName: "invariant-auditor"` to review the new API layer
   specifically for missing authorization checks, approval bypass paths, and any
   export reachable without a recorded engineer approval (invariant 6). Fix anything
   it flags before moving on.
5. Walk a real BOM through the full UI flow without touching the CLI and confirm the
   done-when criterion.

## Review gate — STOP HERE

Summarize what was created, demonstrate the end-to-end flow, and report the
invariant-auditor findings and how each was resolved. **Do not start M7.** Wait for the
user's explicit approval.

Once approved, tell the user to run `/roadmap-m7-live-adapters` to continue.
