---
description: "Roadmap factory step 8/9 — M7 Live supplier adapters. Builds Mouser/DigiKey/Farnell adapters and credential handling, audits network and secret handling, then stops for review before handing off to M8."
agent: agent
tools: [read, edit, search, execute, todo, agent]
argument-hint: "(optional) notes or constraints for this milestone"
---

# Milestone M7 — Live supplier adapters

Read `docs/roadmap.md` (section "M7 — Live supplier adapters") first. Confirm M4–M6
are complete — the `SupplierAdapter` protocol, fixture adapter, and web app must exist
before adding live adapters.

## Scope for this milestone

- Mouser, DigiKey, Farnell adapters behind the existing protocol
- Credential handling via secret store
- Rate limiting, retry with backoff, circuit breaking
- Snapshot writing on every live fetch
- Freshness policy and pre-export re-validation

**Done when:** flipping `sourcing.adapters` from fixture to live changes no code
upstream of `source`.

## Process

1. Use `runSubagent` with `agentName: "supplier-adapter-builder"` to implement the
   Mouser, DigiKey, and Farnell adapters against the existing `SupplierAdapter`
   protocol, matching `FixtureAdapter`'s output shape exactly. Include credential
   handling via the secret store, rate limiting, retry with backoff, circuit breaking,
   snapshot writing on every fetch, and the freshness/pre-export re-validation policy.
2. Use `runSubagent` with `agentName: "invariant-auditor"` to review the new adapters
   for credential leakage, missing `snapshot_id`/`fetched_at` provenance, and any live
   network call reachable from a test. This is the highest-risk milestone in the
   roadmap — treat any finding as blocking.
3. Confirm that switching `sourcing.adapters` from fixture to live requires no changes
   upstream of `source`.

## Review gate — STOP HERE

Summarize what was created, report the invariant-auditor findings and how each was
resolved, and confirm no credentials or live calls leaked into tests. **Do not start
M8.** Wait for the user's explicit approval.

Once approved, tell the user to run `/roadmap-m8-evals-hardening` to continue.
