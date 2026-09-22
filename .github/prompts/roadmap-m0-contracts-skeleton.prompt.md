---
description: "Roadmap factory step 1/9 — M0 Contracts and skeleton. Scaffolds contracts, JSON Schema, stage protocol, and CLI, then stops for review before handing off to M1."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M0 — Contracts and skeleton

Read `docs/roadmap.md` (section "M0 — Contracts and skeleton") and
`docs/data-contracts.md` before doing anything else.

## Scope for this milestone

- Pydantic v2 models for every type in `docs/data-contracts.md`
- JSON Schema export to `contracts/schema/v1/`
- Category parameter declarations (`categories.py`)
- Stage protocol, `StageContext`, `StageResult`, run artifact writer
- CLI: `pcbpick run <file>`, `pcbpick resume <run_id> --from <stage>`
- pytest + uv + CI

**Done when:** an empty pipeline runs end to end and writes artifacts.

## Process

1. Use `runSubagent` with `agentName: "contract-architect"` to implement every
   contract model and the JSON Schema export listed above, versioned as `v1`. Give it
   the full list of types from `docs/data-contracts.md`.
2. Implement the stage protocol, `StageContext`/`StageResult`, run artifact writer, and
   CLI yourself — no agent owns this scaffolding. Keep it minimal; no real stage logic
   belongs here yet.
3. Wire up pytest, `uv`, and CI.
4. Run the test suite and exercise `pcbpick run` against a no-op pipeline to confirm
   the done-when criterion.

## Review gate — STOP HERE

Summarize what was created, show the test results, and list anything skipped or
deferred. **Do not start M1.** Wait for the user's explicit approval of this milestone.

Once approved, tell the user to run `/roadmap-m1-ingest` to continue.
