# `evals/` — golden-BOM regression suite

This is the M8 scored-expectation eval suite required by
`.github/instructions/testing.instructions.md`'s "Golden-BOM evals" section. It is
**case data and scoring documentation only** — the Python runner that loads a case,
drives the pipeline stages, and scores the result against `expect` does not exist yet
and is explicitly out of this fixture-curator pass's scope (it belongs to the
stage-builder agent working in `src/pcbpick/pipeline/`, per this milestone's brief).
See "Runner requirements" below for what that agent needs to build to consume this
directory.

Every number in every `expect` block below was hand-derived by reading the actual
fixture bytes and the actual (already-implemented, already-tested) stage source under
`src/pcbpick/{ingest,normalize,classify,sourcing,policy}/` — never by running the
pipeline and copying its output. Where a number could not be pinned exactly without
executing code (e.g. footprint-recognition edge cases, or an exact candidate/tier
count that depends on search-matching behavior not independently documented
elsewhere), the case uses a `_min`/`_guaranteed` bound instead of an exact value, per
the skill's "coarser grain you CAN hand-verify" allowance. Every such bound states,
in `hand_verified_reasoning`, exactly which source lines or fixture lines back it.

## Layout

```
evals/
  README.md                # this file
  cases/
    <case_id>/
      case.json             # inputs + expect, self-contained
```

## `case.json` schema

```jsonc
{
  "case_id": "string, matches the directory name",
  "description": "what real-world failure mode or invariant this case exercises",
  "chain": ["ingest", "normalize", "expand", "source", "policy", "evaluate"],
  // Ordered list of stages this case's `expect` block covers. A runner stops
  // evaluating `expect` fields once it reaches the last stage named here — it is
  // not required to run stages beyond it, and doing so is out of scope for this
  // case (see `not_extended_to` below when that's a deliberate, documented gap
  // rather than simply "this case doesn't need it").

  "inputs": {
    // Exactly one of these two is present, never both:
    "bom_file": "fixtures/boms/kicad_bom.csv",
    // OR, for a case that starts mid-chain from already-hand-verified,
    // already-resolved requirements (see kicad_bom_hand_built_subset_sourcing_
    // policy_evaluate/case.json for why this exists):
    "normalized_requirements": [ /* NormalizedRequirement[], schema_version v1 */ ],

    "catalog_snapshot": "fixtures/catalogs/kicad_golden_snapshot.json",
    // present only when `chain` includes "source"

    "llm": {
      // present only when `chain` includes "normalize" (fallback) or "evaluate"
      // (rationale). Both name a fixture file under fixtures/llm/<call_site>/ whose
      // `response_text` a runner should feed a FakeLLMClient as `default_response`.
      "normalize_fallback_fixture": "fixtures/llm/normalize_fallback/valid_ic_widget_row.json",
      "candidate_rationale_fixture": "fixtures/llm/candidate_rationale/valid_nrnd_concern.json"
    }
  },

  "expect": {
    // See "Expectation vocabulary" below. Only the fields relevant to `chain` are
    // populated; others are simply absent, not null (absence means "not scored by
    // this case", not "expected to be zero").
  },

  "not_extended_to": [
    // Stages this case's BOM/snapshot pair could theoretically reach but this case
    // deliberately does not score, with a one-line reason each. Absent if `chain`
    // reaches the last stage the pipeline defines for this input shape.
  ],

  "hand_verified_reasoning": "the derivation, citing exact fixture lines/files and/or exact source lines read, for every number in `expect`. This is the field a reviewer checks before trusting the case."
}
```

## Expectation vocabulary

| Field | Meaning | Populated by stage |
|---|---|---|
| `normalized_rows` | exact count of `NormalizedRequirement`s emitted (post-DNP-exclusion) | normalize |
| `dnp_excluded` | exact count of DNP lines excluded before normalize builds a requirement | normalize |
| `quantity_mismatch_count` | exact count of ingest rows where refdes count disagreed with the stated quantity column | ingest |
| `unresolved_min` / `unresolved_max` | bounds on how many requirements have a non-empty `unresolved` list. Equal min/max asserts an exact count. | normalize |
| `unresolved_field_counts` | exact `{dotted_field: count}` map — only present when every occurrence was traced by hand to a specific row and a specific missing/ambiguous field | normalize |
| `category_counts` | exact `{ComponentCategory.value: count}` map | normalize |
| `blocking_normalization_unresolved_count` | exact count of `BLOCKING` `normalization_unresolved` `StageIssue`s | normalize |
| `llm_fallback_unavailable_count` | exact count of `INFO` `llm_fallback_unavailable` issues (fires once per row whose category is `UNKNOWN`, regardless of whether a client is configured) | normalize |
| `requirements_sourced` | count of requirements `ExpandStage` did **not** exclude (i.e. `unresolved == []`) | expand |
| `candidates_by_requirement` | per-requirement candidate facts: `total` (candidate count from `search()`), `tier3_mpns` (candidates that must fail policy at tier 3, with the rule that rejects them), `policy_clean_min` (a safe lower bound on tier-0/1/2 survivors) | source + policy |
| `filled_at_tier_0_or_1_min` | lower bound on requirements with at least one tier-0-or-1 policy-clean candidate | policy |
| `evaluate_rationale_success_count` / `evaluate_blocking_count` | how many surviving candidates get a `rationale` vs. a `candidate_rationale_llm_failed` `BLOCKING` issue, given the `llm` fixture named in `inputs` | evaluate |

Fields absent from a given case's `expect` are not scored by that case — a runner
must not treat an absent field as an implicit assertion of `0`.

## Cases

| case_id | proves |
|---|---|
| `kicad_bom_ingest_normalize_all_unresolved` | the flagship KiCad golden BOM, run through the **real** deterministic `ingest → normalize` chain (no hand-built shortcuts), leaves every single sourceable row unresolved — because the export has no explicit tolerance/voltage/dielectric/pin-count/frequency columns and today's deterministic parser does not yet infer `frequency` or `pin_count` from free text at all. This is the reason `kicad_golden_snapshot.json`'s own consuming test (`tests/pipeline/test_sourcing_pipeline.py`) hand-builds its requirements instead of running normalize — this case is the fixture-level proof of *why*, not a workaround for it. |
| `kicad_bom_hand_built_subset_sourcing_policy_evaluate` | given already-resolved requirements for 4 of `kicad_bom.csv`'s lines (the same 4 already hand-built and reviewed in `tests/pipeline/test_sourcing_pipeline.py`), the `expand → source → policy → evaluate` chain against `kicad_golden_snapshot.json` surfaces the documented alternates/decoys at the correct tiers and rejects the documented footprint-mismatch decoys at tier 3, never sending a tier-3 candidate to the LLM. |
| `altium_bom_ingest_normalize` | a real Altium export (Comment/Description/LibRef columns, no per-parameter columns) leaves all 10 rows unresolved for the same structural reason as the KiCad case, plus two rows (`U1`, `U2`) whose category itself is unresolved — one of them (`U1`, `"Op Amp Single SOIC-8"`) specifically because the description-keyword regex requires a hyphen or no separator (`op-?amp`) and does not match a space (`"Op Amp"`), a documented, hand-verified punctuation trap. |
| `eagle_bom_ingest_normalize` | an Eagle/Fusion export where `U1`'s value is empty and its real identity is carried in `Description` (`"Dual Op-Amp"`, hyphenated — the *positive* case of the same regex trap `altium_bom` hits negatively), while every passive/LED/connector row is still unresolved for missing tolerance/voltage/dielectric/pin-count. |
| `orcad_bom_ingest_normalize` | an OrCAD/Allegro export with a 4-row title block above the real header; the same passive/connector/LED unresolved pattern holds once the header is found correctly. |
| `kicad_edge_cases_ingest_normalize` | refdes range/gap expansion and a quantity/refdes mismatch (`R10-R12` states qty 4, lists 3) survive into normalize correctly — `quantity_per_board` uses the derived refdes count (3), not the disagreeing stated quantity (4) — while every non-DNP row still lands unresolved for the same structural reason as the other three exports. |
| `normalize_edge_cases_normalize` | the full M2 edge-case suite (RKM notation, 3-digit capacitor codes, ambiguous `1M`/`104`/`103K`, unicode micro-sign variants, safety-critical fuse/Y2-capacitor classification, asymmetric `Z`-code tolerance, and the one row requiring `normalize_fallback`) scored in aggregate: exact counts per category, per confidence tier, per criticality, and of rows with a non-empty `unresolved`, all independently re-counted here from the fixture's own hand-verified per-row `expected_*` fields (not merely re-stating them, which is why `hand_verified_reasoning` shows the tally). |

## Deliberate scope limits (not gaps — see "Follow-ups" for actual gaps)

- No case in this suite reaches `plan` or `export`. The only fixture with a paired
  catalog snapshot is `kicad_bom` / `kicad_golden_snapshot.json`, and its real
  normalize output is 100% unresolved (see the first case above) — nothing from it
  is sourceable, so nothing from it is planable either. The
  `kicad_bom_hand_built_subset` case reaches `evaluate` but stops there: hand-tracing
  the price-break/MOQ/SPQ/attrition/shipping-threshold arithmetic across even 8
  candidates by hand, to the standard of certainty this suite requires, was judged not
  achievable in this pass without executing the planning code — inventing a plausible-
  looking total would be exactly the anti-pattern `testing.instructions.md` forbids.
  See "Follow-ups for the stage-builder agent" below.
- `unresolved_field_counts` is only asserted for `kicad_bom` and
  `normalize_edge_cases` (fixtures with no footprint-recognition ambiguity in the
  rows being counted). `altium_bom`/`eagle_bom`/`orcad_bom` use `unresolved_min`
  instead, because whether `RESC1608X55N`/`R0603`/`SOIC8`-style footprint text
  resolves cleanly depends on `normalize/package.py` logic this pass did not trace
  line-by-line — the *guaranteed* unresolved reasons (missing tolerance/voltage/
  dielectric/pin-count/frequency) are asserted as a lower bound, never as an exact
  total, so a footprint-parsing regression would not be falsely absolved by this case
  but also would not be falsely blamed on it.

## Runner requirements for the stage-builder agent

To consume `evals/cases/*/case.json`, the runner needs, at minimum:

1. A loader that takes a `case.json` path, builds the `StageContext` (fixed `now`,
   seeded `rng`, per `.github/instructions/pipeline-stages.instructions.md`), and
   either runs `IngestStage` + `NormalizeStage` against `inputs.bom_file`, or
   parses `inputs.normalized_requirements` directly into `NormalizedRequirement`
   objects (Pydantic `model_validate`) and skips straight to `expand`, depending on
   which key is present.
2. A `FakeLLMClient` wired from `inputs.llm.*_fixture`, reading that fixture's
   `response_text` verbatim as `default_response` — see
   `fixtures/llm/README.md` for that file's schema.
3. A scorer that walks the fields actually present in `expect` (per the vocabulary
   table above) and reports pass/fail per field, not just an aggregate pass/fail for
   the whole case — a single wrong count should not hide behind nine right ones.
4. Because `expect` fields are heterogeneous per case (ingest-only cases don't
   populate `candidates_by_requirement`; the hand-built-subset case doesn't populate
   `quantity_mismatch_count`), the scorer must skip absent fields rather than treat
   them as asserting zero/empty.
5. Tracked-metrics reporting per `testing.instructions.md`'s "Tracked metrics"
   section (% rows normalized without LLM fallback, % requirements filled at tier
   0/1, count of `BLOCKING` issues, plan-total delta) should be computed from the
   same run this scorer already performs, not a second pass.

## Follow-ups for the stage-builder / fixture-curator agents

- **No eval case in this suite exercises `plan` or `export`.** Closing this requires
  either (a) a new, small, hand-computable planning fixture — e.g. a single
  resistor requirement with 2 offers and simple price breaks, chosen specifically so
  the lowest-cost/fastest-delivery/fewest-suppliers totals can be added up on paper
  in one sitting — or (b) accepting a coarser planning eval that only asserts
  `plan_modes` ran and produced a non-empty `PurchasePlan` per mode plus determinism
  (byte-identical across two runs), without pinning exact totals. Recommend (a) for
  at least one case, since `testing.instructions.md`'s own example case includes a
  pinned `lowest_cost_total_eur`.
- **`unknown_format.xlsx`** (the M1 unmapped-format fixture) has no eval case here.
  It is exercised by `tests/stages/test_ingest.py`-style unit tests already; an eval
  case would mostly duplicate that unless paired with a mapping-confirmation +
  re-run flow that doesn't exist yet (M6 web app territory), so it was left out
  rather than added as decoration.
- **`kicad_bom_hand_built_subset`'s `candidates_by_requirement` for `req-u1` and
  `req-y1`** uses `policy_clean_min: 1` rather than an exact count, because (unlike
  the resistor/capacitor parametric searches, which `fixtures/catalogs/README.md`'s
  own "Validation performed" section independently confirms return exactly 4 and 5
  candidates respectively) no committed source documents the exact candidate count
  a parametric IC or crystal `search()` call returns. If the stage-builder agent can
  confirm the exact counts by running the code, tightening these two bounds to exact
  values (and adding the corresponding tier-3 MPNs, if any beyond `LM358P`) would
  strengthen this case with no fixture-data change required.
