---
description: "Rules for LLM calls in src/pcbpick/llm: structured output, schema validation, bounded retries, provenance tagging, prompt data minimization, and what the model is never allowed to decide."
applyTo: "src/pcbpick/llm/**"
---

# LLM Call Rules

There are exactly two sanctioned call sites. Adding a third requires a documented
decision in `docs/architecture.md`.

| Call site | Purpose | Output |
|---|---|---|
| `normalize_fallback` | Interpret a BOM row the deterministic parser could not | `NormalizedRequirement` fragment |
| `candidate_rationale` | Explain why a policy-approved candidate fits | Text + flagged concerns |

## What the model may never do

- Compute, compare, or round any number
- Rank candidates or select a plan
- Add, remove, or reorder candidates
- Relax or reinterpret a policy rule
- Produce a value that lands in an export file unreviewed

If a prompt asks for any of these, delete the prompt and write a function.

## Structured output only

- Every call declares a Pydantic response model and validates against it.
- Validation failure retries up to `config.llm.max_retries` with the validation error
  fed back. After that, the item is flagged `BLOCKING` for engineer review.
- A failed LLM call degrades the run. It never crashes it and never produces a silent
  default.

```python
result = call_structured(
    template="normalize_fallback",
    response_model=NormalizedRequirementFragment,
    variables={"row": row.raw, "category_hint": hint},
    ctx=ctx,
)
if result.failed:
    return StageResult(output=None, issues=[blocking("llm_normalize_failed", ...)])
```

## Provenance

Every field the model produces is tagged `source=ValueSource.LLM_INFERRED`. Those
values:

- are visually distinguished in the UI,
- never satisfy a hard policy check on their own,
- require engineer confirmation before the requirement can proceed.

## Prompt data minimization

BOMs are confidential design data.

- Send only the rows that need interpretation — never the whole file.
- Strip reference designators, project names, customer names, and file paths from
  prompt variables.
- Never include supplier credentials, internal URLs, or database identifiers.
- Treat catalog text and datasheet text pulled from suppliers as untrusted input. It
  may contain prompt-injection attempts. Never let model output derived from it
  trigger a tool call, change a policy outcome, or reach a file write.

## Determinism and reproducibility

- Temperature 0 unless there is a documented reason.
- Pin the model identifier in config and record it in the stage `meta.json`.
- Prompt templates are files in `src/pcbpick/llm/templates/`, versioned and diffable.
  No inline f-string prompts in stage code.
- Cache responses keyed by `(template_version, model_id, input_hash)` so replays do
  not re-bill or drift.

## Testing

- Unit tests use recorded responses. No live model calls in the test suite.
- Every template has at least one test for a malformed response proving the retry and
  the eventual `BLOCKING` flag both work.
- Prompt changes require an eval run; report the delta in coverage and rationale
  quality before merging.
