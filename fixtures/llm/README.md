# `fixtures/llm/` — prompt regression fixtures for the two sanctioned LLM call sites

Per `.github/instructions/llm-calls.instructions.md`, there are exactly two sanctioned
LLM call sites in this codebase: `normalize_fallback`
(`src/pcbpick/llm/templates/normalize_fallback.md`) and `candidate_rationale`
(`src/pcbpick/llm/templates/candidate_rationale.md`). This directory holds
file-based, before/after regression fixtures for both, extending the existing
recorded-response test pattern already used in `tests/stages/test_normalize.py` and
`tests/stages/test_evaluate.py` (both of which currently build their recorded
responses as inline `json.dumps(...)` strings) with fixture files a future prompt
change can diff against.

This directory is **fixture data only**. It does not implement a runner — see
`evals/README.md`'s "Runner requirements" section for what a consuming agent needs
to build to load these files into a `FakeLLMClient` (`src/pcbpick/llm/fakes.py`).

## Layout

```
fixtures/llm/
  README.md
  normalize_fallback/
    <case_id>.json
  candidate_rationale/
    <case_id>.json
```

## `<case_id>.json` schema

```jsonc
{
  "case_id": "string, matches the filename stem",
  "call_site": "normalize_fallback | candidate_rationale",
  "description": "what this case proves",

  "request_variables": {
    // The exact input the real call-site function builds, BEFORE it is handed to
    // `call_structured`/`FakeLLMClient.generate`. Shaped to match:
    // - normalize_fallback: `run_normalize_fallback`'s own `variables` dict
    //   (`{"row": str(raw_cells), "category_hint": category_hint or ""}`,
    //   src/pcbpick/normalize/llm_fallback.py) -- `raw_cells` is shown here as a
    //   structured dict for readability; a runner must call `str(raw_cells)` on it
    //   to reproduce the exact string `run_normalize_fallback` would send.
    // - candidate_rationale: `_requirement_prompt_data`/`_candidate_prompt_data`'s
    //   own dict shapes (src/pcbpick/sourcing/evaluate.py) -- a runner must
    //   `json.dumps(..., sort_keys=True)` each to reproduce the exact strings
    //   `EvaluateStage` would send as `variables["requirement"]`/`["candidate"]`.
  },

  "response_text": "the exact raw string a FakeLLMClient.generate(...) call would return -- feed this verbatim as FakeLLMClient(model_id=..., default_response=response_text)",

  "validates_against_response_model": true | false,
  // true: response_model.model_validate_json(response_text) succeeds.
  // false: it raises pydantic.ValidationError (covers both invalid-JSON-syntax and
  // valid-JSON-but-schema-violating responses -- pydantic v2's model_validate_json
  // wraps a JSON decode failure in the same ValidationError type call_structured
  // already catches, so both failure modes exercise the identical code path).

  "expected_call_structured_outcome": {
    "failed": true | false,
    // With FakeLLMClient (stateless, returns the same response_text on every
    // attempt), a validates_against_response_model=false case NEVER succeeds on
    // retry -- it exhausts every attempt up to max_retries and returns failed=true.
    // This is the "retry-then-degrade" path `llm-calls.instructions.md` requires
    // every template to have at least one test for.
    "attempts": "max_retries + 2 when failed=true (every attempt is spent); 1 when failed=false and the first attempt validates"
  },

  "expected_stage_issue": {
    "code": "the StageIssue.code the consuming stage records for this outcome",
    "severity": "INFO | WARNING | BLOCKING",
    "notes": "why this severity -- see the divergence note below, it is not the same for both call sites"
  }
}
```

## The severity divergence between the two call sites (read this before writing a test)

`llm-calls.instructions.md`'s general policy states a failed call "retries...then the
item is flagged BLOCKING for engineer review." The two real call sites implement this
differently, and both are correct given their actual position in the pipeline —
verified directly from `src/pcbpick/normalize/requirement_builder.py` and
`src/pcbpick/sourcing/evaluate.py`, not assumed from the instructions doc alone:

- **`normalize_fallback` failure is `INFO`, not `BLOCKING`.** `normalize_fallback` is
  only ever attempted for a row whose `category` is already `ComponentCategory.UNKNOWN`
  — which means `"category"` was already added to that requirement's `unresolved`
  list *before* the LLM call was attempted (`hint.confident == False` is the trigger
  for both the fallback attempt and the pre-existing unresolved entry). A failed
  fallback changes nothing: `category` was already unresolved, stays unresolved, and
  `NormalizeStage` already appends its own `BLOCKING normalization_unresolved` issue
  for that reason, independent of the LLM outcome. The fallback's own failure is
  logged as `INFO llm_fallback_unavailable` because it is not itself a new blocking
  condition — it is a no-op degrade on a row that was always going to block.
- **`candidate_rationale` failure is `BLOCKING`.** `EvaluateStage` only calls this for
  a candidate that has *already survived policy* (tier 0/1/2) — i.e. a candidate an
  engineer might otherwise approve. A failed rationale call means that otherwise-
  approvable candidate has no explanation attached, which is a genuinely new problem
  this call introduces (an unexplained recommendation), not a restatement of an
  existing one — hence `BLOCKING candidate_rationale_llm_failed`, exactly matching
  `tests/stages/test_evaluate.py::test_malformed_response_records_blocking_issue_and_leaves_rationale_none`.

## Cases

| file | call site | proves |
|---|---|---|
| `normalize_fallback/valid_ic_widget_row.json` | normalize_fallback | a schema-valid response (`category: null`, the model correctly declining to guess) is accepted, `unresolved` is untouched, confidence stays low |
| `normalize_fallback/malformed_invalid_json.json` | normalize_fallback | non-JSON text exhausts retries, degrades to `failed=true`, `INFO llm_fallback_unavailable` |
| `normalize_fallback/malformed_invalid_category_enum.json` | normalize_fallback | valid JSON but an invalid `ComponentCategory` string (`"widget"`) — the model inventing a category value the enum does not define — fails Pydantic enum validation the same way, same degrade path |
| `candidate_rationale/valid_nrnd_concern.json` | candidate_rationale | a schema-valid response with one concern is accepted; `concerns` surfaces as a `WARNING candidate_rationale_concern` issue per concern, never changes `substitution_tier` |
| `candidate_rationale/malformed_invalid_json.json` | candidate_rationale | non-JSON text exhausts retries, degrades to `failed=true`, `BLOCKING candidate_rationale_llm_failed`, `rationale` stays `None` |
| `candidate_rationale/malformed_extra_field.json` | candidate_rationale | valid JSON that adds an unauthorized field (`"confidence": 0.92`) — the model trying to assert something it is never allowed to decide — is rejected by `CandidateRationale`'s `extra="forbid"`, same degrade path as invalid JSON |
