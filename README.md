# pcbpick — PCB Parts Picking

An internal decision-support tool for electrical engineers. It turns a PCB bill of
materials (BOM) into reviewed, sourceable purchasing options: it ingests EDA exports,
normalizes component requirements, finds candidate parts across supplier catalogs,
applies engineering policy (derating, compliance, safety-critical gating), and
produces comparable purchase plans plus supplier-ready import files.

**It is a decision-support tool, not an autonomous purchaser.** Every output is a
proposal that a named engineer reviews and approves before anything is bought.

See [pcb-parts-picking-ai-framework-summary.md](pcb-parts-picking-ai-framework-summary.md)
for the original problem statement, and [docs/architecture.md](docs/architecture.md) /
[docs/data-contracts.md](docs/data-contracts.md) for the technical design.

## How it works

1. **Ingest** — read a BOM export (CSV/XLSX/XLS) from Altium, KiCad, Eagle/Fusion,
   OrCAD/Allegro or an ad-hoc spreadsheet; detect columns and expand reference
   designators (`R1-R4`, `C1,C3`, `U1`).
2. **Normalize** — parse values, tolerances, ratings and package codes into SI units;
   classify each line by component category.
3. **Policy** — apply derating, footprint-identity, lifecycle, and compliance
   (RoHS/REACH/AEC-Q) rules; flag safety-critical parts that may never be
   auto-substituted.
4. **Source** — query supplier catalogs (Mouser, DigiKey, Farnell, or an offline
   fixture catalog) for candidate parts, price breaks, and stock, all timestamped and
   attributed to a snapshot.
5. **Plan** — compute order quantities (MOQ/SPQ rounding, assembly attrition,
   shipping thresholds) and compare purchasing strategies: lowest cost, fastest
   delivery, fewest suppliers, or a balanced trade-off.
6. **Export** — generate supplier-ready BOM import files (CSV/XLSX) once an engineer
   has approved the plan.

The rule that shapes everything above: **the model reasons, the code decides.** The
LLM may interpret ambiguous input or explain a trade-off; it never computes a price,
picks a winning plan, or overrides a policy gate. See the "one rule that matters
most" section in [.github/copilot-instructions.md](.github/copilot-instructions.md)
for the full list.

## Status

All milestones in [docs/roadmap.md](docs/roadmap.md) are implemented: every stage
(`ingest`, `normalize`, `expand`, `source`, `policy`, `evaluate`, `plan`, `export`)
exists, is tested, and is exercised end-to-end by the golden-BOM eval suite
(`src/pcbpick/pipeline/eval_runner.py`) and by the FastAPI backend
(`src/pcbpick/api/orchestrator.py`), which drives the full chain for the interactive
upload → mapping → resolve → candidate review → plan comparison → approval → export
flow.

The one exception is the batch CLI runner (`src/pcbpick/pipeline/runner.py`, behind
`pcbpick run`/`resume`/`replay`): it currently registers only `ingest` and
`normalize`, by design — later stages expect engineer input between them (e.g.
resolving flagged requirements, approving a plan), which a single non-interactive
batch run doesn't model. Use the API for the full pipeline; the CLI is for
ingest/normalize-only runs and artifact inspection.

## Repository layout

```
src/pcbpick/
  contracts/      # Pydantic models + JSON Schema. Source of truth.
  ingest/         # File readers, EDA profiles, column mapping
  normalize/      # Unit/value parsing, package codes, dedup
  classify/       # Category routing
  policy/         # Derating, compatibility, substitution tiers, compliance gates
  sourcing/       # Candidate search, incl. suppliers/ (SupplierAdapter implementations)
  planning/       # Price breaks, MOQ/SPQ, attrition, multi-supplier optimization
  exporters/      # Supplier BOM import formats
  pipeline/       # Stage runner, run artifacts, resume/replay
  api/            # FastAPI routes
  llm/            # Prompt templates, structured-output calls, validation retries
  cli.py          # `pcbpick` command-line entry point
web/              # React + TypeScript (Vite) frontend
fixtures/         # Offline catalog snapshots, sample + golden BOMs
evals/            # Golden-BOM regression suite
tests/            # pytest suite
docs/             # Architecture and contract specs
runs/             # Local run artifacts (gitignored)
```

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Node.js 18+ (for the web frontend)

## Setup

```powershell
# install Python dependencies (creates .venv)
uv sync

# install frontend dependencies
cd web
npm install
cd ..
```

## Usage

### Command line

Run the `ingest` → `normalize` stages against a BOM file and get back a run id (see
[Status](#status) for why the CLI stops there):

```powershell
uv run pcbpick run path/to/bom.csv
```

Resume a run from a specific stage after fixing an upstream issue:

```powershell
uv run pcbpick resume <run_id> --from normalize
```

Replay a run's stage chain and verify the stored artifacts are still reproducible
byte-for-byte (fails with a non-zero exit code on divergence):

```powershell
uv run pcbpick replay <run_id>
```

Run artifacts are written under `./runs/<run_id>/` by default; override with
`--runs-root` or the `PCBPICK_RUNS_ROOT` environment variable.

### API + web app

Start the FastAPI backend:

```powershell
uv run uvicorn pcbpick.api.app:app --reload
```

The API listens on `http://localhost:8000` (health check at `/health`) and defaults
to a local SQLite database (`PCBPICK_DATABASE_URL` to override, e.g. for Postgres).

Start the frontend dev server:

```powershell
cd web
npm run dev
```

The web app runs on `http://localhost:5173` and expects the API at
`http://localhost:8000` (allowed via CORS by default).

Or start everything together with LLM assistance enabled in one step:

```powershell
./scripts/start-dev.ps1
```

This starts Ollama and its [Open WebUI](https://github.com/open-webui/open-webui)
management UI in Docker (`docker compose up -d ollama open-webui`, pulling the model
into the container on first run), then opens the backend and frontend each in their
own window with `PCBPICK_USE_LLM=1` set. Requires Docker Desktop (or another Docker
engine) to be installed and running; if `docker` isn't found, it's skipped and the
LLM-assisted stages degrade gracefully as usual. Open WebUI is available afterward at
`http://localhost:3000` for browsing/pulling models and chatting with them directly.

### Optional: LLM-assisted normalize/evaluate

The two sanctioned LLM call sites (`normalize_fallback`, `candidate_rationale`, see
[.github/instructions/llm-calls.instructions.md](.github/instructions/llm-calls.instructions.md))
have no client configured by default — those stages degrade gracefully (an `INFO` or
`BLOCKING` issue, never a crash) instead of calling a model. To enable them locally
against a free, no-API-key [Ollama](https://ollama.com) server, `./scripts/start-dev.ps1`
does this for you (see above). To do it by hand instead:

```powershell
# once: start Ollama (+ Open WebUI) in Docker and pull a model into the container
docker compose up -d ollama open-webui
docker exec pcbpick-ollama ollama pull llama3.2:3b

# set before starting the API
$env:PCBPICK_USE_LLM = "1"
uv run uvicorn pcbpick.api.app:app --reload
```

No Docker? Install [Ollama](https://ollama.com) locally instead (`ollama pull
llama3.2:3b`) — the backend also auto-starts a local `ollama serve` if it finds the
executable on `PATH` and nothing is already listening on `PCBPICK_OLLAMA_BASE_URL`.

`PCBPICK_OLLAMA_MODEL` (default `llama3.2:3b`) and `PCBPICK_OLLAMA_BASE_URL` (default
`http://localhost:11434`) override the model and server address. Never set
`PCBPICK_USE_LLM` in tests — it would add a live network call, which
[.github/instructions/testing.instructions.md](.github/instructions/testing.instructions.md)
forbids.

## Testing

```powershell
# Python: unit tests and golden-BOM evals
uv run pytest

# lint / type-check
uv run ruff check .
uv run mypy

# frontend
cd web
npm run lint
```

No test in this repository makes live network calls — supplier data comes from
fixture snapshots under `fixtures/catalogs/`.
