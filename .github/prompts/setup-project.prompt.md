---
description: "Install and verify all dependencies for the pcbpick project (Python backend + web frontend)"
agent: "agent"
tools: ["execute", "edit"]
---
Set up this repository for local development, following the [README](../../README.md).

Do the following, in order, and report the result of each step:

1. Check whether `uv` is installed (`uv --version`). If it is not found, install it
   with `winget install --id=astral-sh.uv -e` (falling back to the official installer,
   `irm https://astral.sh/uv/install.ps1 | iex`, if `winget` is unavailable), then
   confirm `uv --version` succeeds. Requires Python 3.12+.
2. Install Python dependencies with `uv sync` (creates/updates `.venv`).
3. Install frontend dependencies: `cd web` then `npm install` (requires Node.js 18+).
4. Verify the backend setup by running `uv run pytest` from the repo root.
5. Verify the frontend setup by running `npm run lint` from `web/`.

If any step fails:
- Do not skip ahead — report the exact error output.
- Diagnose the likely cause (missing `uv`/Node, network/proxy issues, lockfile
  drift, version mismatch) and propose the smallest fix.
- Re-run only the failed step after fixing it, rather than repeating steps that
  already succeeded.

Do not start the API server or the frontend dev server as part of this setup —
only install dependencies and validate them via tests/lint. Summarize at the end
whether the environment is ready, and list any manual steps the user still needs
to take (e.g. setting `PCBPICK_DATABASE_URL` for Postgres instead of the SQLite
default).
