---
description: "Rules for writing pipeline stages in ingest, normalize, classify, policy, sourcing, planning, exporters and pipeline: purity, artifacts, resumability, determinism."
applyTo: "src/pcbpick/{ingest,normalize,classify,policy,sourcing,planning,exporters,pipeline}/**"
---

# Pipeline Stage Rules

A stage is a pure function from one artifact to another:

```python
def run(inp: InputArtifact, ctx: StageContext) -> StageResult[OutputArtifact]:
    ...
```

## Hard requirements

- **No mutation of input.** Build and return new objects.
- **No I/O.** The only exceptions are `sourcing/suppliers/` (network) and the runner
  itself (artifact writes). If a stage needs data, it receives it via `ctx` or input.
- **No wall-clock or randomness.** Use `ctx.now` and `ctx.rng`. A run replayed from
  the same artifacts must produce identical output.
- **No config reading.** Config arrives as a typed object on `ctx.config`.
- **Deterministic ordering.** Sort explicitly before returning collections. Never rely
  on dict or set iteration order for anything that reaches an artifact.

## Failure handling

A stage does not raise on bad input data. It records the problem and continues:

```python
return StageResult(
    output=requirements,
    issues=[
        StageIssue(
            severity=Severity.BLOCKING,
            requirement_id=req.requirement_id,
            code="quantity_mismatch",
            message="BOM states qty 4, 3 reference designators listed",
        )
    ],
)
```

- `BLOCKING` — the item cannot proceed; an engineer must resolve it in the UI.
- `WARNING` — proceeds but is surfaced in the review screen.
- `INFO` — audit trail only.

Raise only for programmer errors: a malformed artifact, a contract violation, a
missing adapter. Those mean the pipeline is broken, not the data.

## The decision boundary

Arithmetic, ranking, filtering, and file generation are code. Never delegate them to
the LLM, and never accept an LLM-supplied number into a computed field.

| Stage | Never does |
|---|---|
| `normalize` | invent a value for a field the BOM does not state |
| `policy` | soften a rule because a candidate is otherwise attractive |
| `evaluate` | add, remove, or reorder candidates |
| `plan` | ask the model to compare totals |
| `export` | let unvalidated text reach a spreadsheet cell |

## Artifacts

- Every stage writes `runs/<run_id>/<seq>-<stage>.json` plus `meta.json` with input
  hash, config hash, duration, and the versions of any adapter or model used.
- Artifacts are the debugging interface. If a field would help an engineer understand
  a recommendation six months later, put it in the artifact.
- Stages must be resumable: `pcbpick resume <run_id> --from <stage>` reads the prior
  artifact and proceeds. Do not introduce dependencies on stages more than one step
  upstream except through the artifact chain.

## Adding a stage

Prefer extending an existing stage. A new stage requires a new contract type, a new
artifact, roadmap justification, and updates to the runner and the resume CLI.

## Tests

Every stage needs: a golden-path test from a fixture, a test per `BLOCKING` issue code
it can emit, and a determinism test that runs it twice and compares output bytes.
