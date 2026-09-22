# `fixtures/policy/` — M3 substitution-policy score sheet

This directory is the **scoring fixture set** for the M3 policy engine
(`src/pcbpick/policy/`, not yet built at the time this fixture set was written). It is
consumed by two downstream agents:

- the agent **implementing** the policy engine, as a spec of expected behavior;
- the agent **writing tests**, which loads each pair below and asserts the engine's
  real output against the hand-verified `expected` file.

These fixtures are deliberately **not** produced by running any pcbpick code. Every
number was computed by hand from `.github/skills/substitution-policy/SKILL.md` and its
`references/category-rules.md`, and the derivation is recorded in each case's
`hand_verified_reasoning` field so a future reader can check the arithmetic without
re-deriving it.

## Layout

```
fixtures/policy/
  README.md            # this file
  manifest.json         # machine-readable index of all case ids
  cases/
    <case_id>.input.json     # one NormalizedRequirement + one PartCandidate (pre-policy)
    <case_id>.expected.json  # the hand-verified oracle for that pair
```

Each case is a **pair** of files sharing a stem, mirroring the existing
`fixtures/boms/<name>.csv` + `<name>.expected.json` convention used elsewhere in this
repo. There is no shared/batched file — every case's requirement and candidate are
self-contained, so a case can be added, removed, or hand-edited without touching any
other case.

## `*.input.json` schema

```jsonc
{
  "case_id": "string, matches the filename stem",
  "requirement": { /* NormalizedRequirement, see src/pcbpick/contracts/requirement.py */ },
  "candidate": {
    // The pre-policy subset of PartCandidate (src/pcbpick/contracts/candidate.py):
    // the fields a policy engine consumes as input. Fields the policy engine is
    // responsible for *producing* (substitution_tier, policy_results, rationale,
    // evidence, offers) are intentionally absent.
    "schema_version": "v1",
    "requirement_id": "string, matches requirement.requirement_id",
    "mpn": "string",
    "manufacturer": "string",
    "parameters": { "<name>": /* ParameterValue */ },
    "footprint": { /* Footprint */ },
    "lifecycle": "active | nrnd | eol | obsolete | unknown",
    "compliance": [ /* ComplianceTag[] */ ]
  }
}
```

`requirement` and `candidate` are shaped to validate directly against
`NormalizedRequirement` and the pre-policy subset of `PartCandidate` respectively —
load them with the real Pydantic models in tests rather than hand-rolled dicts.

### Conventions used across every case

- All physical quantities are `Decimal`-friendly JSON: numeric leaves that map to a
  `Decimal` field (`value`, `tolerance_pct`, `min`, `max`, `pitch_mm`, `length_mm`,
  `width_mm`, `height_mm`) are encoded as JSON strings (`"10000"`, `"2.2E-9"`), never
  as bare JSON numbers, so no binary-float rounding can enter the fixture.
- All values are stored in **SI base units** per the part-normalization skill:
  `ohm`, `farad`, `henry`, `volt`, `ampere`, `watt`, `celsius`, `percent`.
- `ParameterValue.source` is `"parsed"` on every requirement parameter (it came from
  the BOM/normalize stage) and `"datasheet"` on every candidate parameter (it came
  from the supplier/manufacturer record). `"engineer_entered"` is used only where a
  requirement field was explicitly set by an engineer (e.g. a `do_not_substitute`
  override's `specified_mpn`).
- A requirement's `unresolved` list is always `[]` — these fixtures represent
  requirements that already cleared normalize/classify and are ready for policy.
  Nothing here exercises the ingest/normalize stages.
- A few cases (`known_bad_temperature_range_narrower`) add parameter keys
  (`operating_temp_min`, `operating_temp_max`) beyond what
  `src/pcbpick/contracts/categories.py` lists as required/optional for that category.
  That file governs what *normalization* must fill in before a requirement is valid;
  it does not limit what a policy rule may additionally compare, so this is
  intentional, not an error.

## `*.expected.json` schema

```jsonc
{
  "case_id": "string, matches the input file's case_id",
  "outcome": "pass | fail",
  "tier": 0 | 1 | 2 | 3 | null,       // null iff outcome == "fail"
  "expected_rules": [
    {
      "rule_name": "string, e.g. 'voltage_derating', 'footprint_identity'",
      "passed": true | false,
      "reason_contains": "a substring the real PolicyResult.reason must contain"
    }
  ],
  "blocking_rule": "string | null",   // the rule_name whose failure causes outcome=='fail'; null iff outcome=='pass'
  "hand_verified_reasoning": "the derivation a human checked by hand, with the arithmetic shown"
}
```

**How the test-writing agent should use `expected_rules`:** it is the *minimum*
required subset of the real engine's exhaustive `PolicyResult[]` output (the skill
requires the engine to emit a result for every rule evaluated, not just failures).
Assert that each listed `rule_name` appears in the engine's output with the given
`passed` value, and that its `reason` **contains** `reason_contains` as a substring —
do not assert exact reason-string equality, and do not assert on rule ordering. The
real engine may emit additional passing rules not listed here (e.g. category_match on
every case); their absence from `expected_rules` is not a signal that they should be
omitted, only that this fixture doesn't need to pin them down.

`blocking_rule` identifies the one rule this case was specifically built to exercise.
For fail cases, that rule's `passed` must be `false`; other rules may also fail in a
real engine's output (e.g. a fixture built to test dielectric class doesn't rule out
the same candidate also having a lifecycle problem), but `blocking_rule` is guaranteed
to be *one* correct, checkable reason for the overall `fail`.

## Cases

| case_id | tests | expected outcome |
|---|---|---|
| `known_good_tier0_identical_mpn` | identical MPN re-offered by a second distributor | pass, tier 0 |
| `known_good_tier1_capacitor_dropin` | drop-in Class I capacitor, different manufacturer, tighter tolerance, voltage clears derating | pass, tier 1 |
| `known_good_tier2_pin_compatible_ic` | pin-compatible op-amp from a different manufacturer, parametric requirement (no specified_mpn) | pass, tier 2 |
| `known_bad_class_ii_voltage_derating` | Class II cap clears nameplate voltage but fails the 50% derated requirement | fail: `voltage_derating` |
| `known_bad_resistor_power_derating` | resistor clears nameplate power but fails the 60% derated requirement | fail: `power_derating` |
| `known_bad_inductor_isat_derating` | inductor clears nameplate peak current but fails the 1.5x Isat derating | fail: `saturation_current_derating` |
| `known_bad_temperature_range_narrower` | candidate's cold-end operating limit doesn't cover the requirement's -40°C floor | fail: `temperature_range` |
| `known_bad_dielectric_class_change` | Class I (C0G) requirement vs. Class II (X7R) candidate | fail: `dielectric_class` |
| `known_bad_footprint_mismatch` | same electrical resistor, 0805 candidate vs. required 0603 | fail: `footprint_identity` |
| `known_bad_lifecycle_obsolete` | electrically perfect match, candidate lifecycle is `obsolete` | fail: `lifecycle` |
| `known_bad_compliance_rohs_regression` | requirement needs RoHS, candidate compliance is empty (unknown) | fail: `compliance_rohs` |
| `known_bad_aec_q200_regression` | automotive requirement needs AEC-Q200, candidate lacks it | fail: `qualification_aec_q200` |
| `safety_fuse_no_auto_substitution` | electrically-superior fuse, wrong MPN | fail: `safety_critical_exact_mpn_only` |
| `safety_y2_capacitor_no_auto_substitution` | electrically-identical Y2 safety cap, wrong MPN | fail: `safety_critical_exact_mpn_only` |
| `safety_optocoupler_no_auto_substitution` | pin-compatible optocoupler, wrong MPN | fail: `safety_critical_exact_mpn_only` |
| `safety_isolation_transformer_no_auto_substitution` | matching isolation transformer, wrong MPN | fail: `safety_critical_exact_mpn_only` |
| `engineer_override_do_not_substitute` | ordinary resistor category, but engineer set `criticality: do_not_substitute` | fail: `engineer_do_not_substitute` |
| `known_bad_missing_voltage_rating_unknown` | candidate voltage rating is `null` (unknown), required field can't be verified | fail: `required_parameter_unknown` |

Every derating figure above traces to the default factor table in
`category-rules.md` (Class II capacitor voltage ≤50% of rated, resistor power ≤60% of
rated, inductor Isat ≥1.5× peak, resistor/Class I capacitor voltage ≤80% of rated).
Those factors are configuration (`config/derating.yaml`, not yet created), not
physics — if that config's defaults are ever revised by engineering sign-off, the
numbers in these fixtures must be revisited too.
