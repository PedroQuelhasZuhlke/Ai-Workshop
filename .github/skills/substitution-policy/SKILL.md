---
name: substitution-policy
description: 'Decide whether a candidate part may replace a required part. Use when implementing or debugging derating rules, compatibility checks, substitution tiers, safety-critical part detection, lifecycle and RoHS/REACH/AEC-Q compliance gates, or footprint matching.'
---

# Substitution Policy

The policy engine runs **before** the LLM sees any candidate. It is pure, deterministic
code. Its job is to make unsafe recommendations structurally impossible rather than
merely unlikely.

## Output

For each candidate, emit an exhaustive `PolicyResult[]` — every rule evaluated,
pass or fail, with the compared values. Engineers need to see what was checked, not
just what failed. Then assign a `SubstitutionTier`.

```python
PolicyResult(
    rule="voltage_derating",
    outcome=Outcome.FAIL,
    required="25 V (16 V applied × 1.5 derating)",
    candidate="16 V",
    message="Rated voltage below derated requirement",
)
```

## Substitution tiers

| Tier | Meaning | Handling |
|---|---|---|
| 0 | Identical MPN, possibly different distributor or packaging | Auto-proposed |
| 1 | Drop-in equivalent: same footprint, all parameters meet or exceed, same dielectric class, same or better lifecycle | Auto-proposed, shown as substitution |
| 2 | Parametric equivalent from a different manufacturer, or a characteristic changed within the requirement envelope | Requires engineer review before it can enter a plan |
| 3 | Requires a design change: different footprint, pinout, value, or a relaxed parameter | Never proposed as a purchase option; shown only as information |

A candidate never gets a better tier than its worst rule outcome allows.

## The direction rule

**A substitution may only move parameters in the safe direction.**

| Parameter | Safe direction |
|---|---|
| Tolerance | tighter or equal |
| Voltage rating | higher or equal (after derating) |
| Current rating | higher or equal |
| Power rating | higher or equal |
| Saturation current | higher or equal |
| Temperature range | wider or equal at both ends |
| ESR (where specified) | within the stated window — **not** simply lower |
| Capacitance / resistance / inductance | within stated tolerance of nominal |

Two traps: "better" is not always safe. Lower ESR can destabilize an LDO that requires
a minimum ESR for compensation. A tighter-tolerance crystal load capacitance changes
oscillator pull. When a parameter has a specified window rather than a minimum, treat
the window as a hard constraint in both directions.

## Hard gates — fail, never warn

1. **Footprint identity.** Land pattern must match exactly. Package family alone is
   not a match; pin count, pitch, body size and thermal pad must all agree. A
   footprint mismatch is tier 3, always.
2. **Safety-critical parts.** Never auto-substituted at any tier above 0. See the
   detection list in [category rules](./references/category-rules.md). Agency
   approvals (UL, IEC, VDE, CSA, TÜV) are granted to a specific part from a specific
   manufacturer — an electrically identical part without the same approval fails the
   compliance obligation.
3. **Qualification regression.** If the requirement states AEC-Q100 or AEC-Q200, a
   non-qualified candidate fails. Qualification may never be lost.
4. **Compliance regression.** RoHS and REACH status may never go from compliant to
   non-compliant or unknown. Unknown is a failure, not a pass.
5. **Dielectric class change.** Class I ↔ Class II is a fail. See the dielectric rules
   in the part-normalization skill reference.
6. **Unknown parameter on a required field.** A candidate whose rated voltage is
   unknown cannot pass a voltage check. Missing data fails closed.

## Derating

Derating factors are **configurable policy**, not physics, and the defaults must be
signed off by engineering. They live in `config/derating.yaml`, are versioned, and the
active version is recorded in every run artifact.

Apply derating to the *requirement*, then compare the candidate against the derated
requirement. Never derate the candidate's rating.

See [category rules](./references/category-rules.md) for the default factor table.

## Lifecycle

| Candidate lifecycle | Effect |
|---|---|
| `active` | Pass |
| `nrnd` | Pass with `WARNING`, penalized in `lowest_risk` mode |
| `eol` | Pass with `WARNING` only if stock covers the build; otherwise fail |
| `obsolete` | Fail |
| `unknown` | Pass with `WARNING`, never eligible for tier 0 or 1 |

## Evaluation order

Run cheap deterministic gates first so expensive checks never run on doomed
candidates:

1. Category match
2. Footprint identity
3. Criticality gate (safety-critical → tier 0 only)
4. Hard parameter comparisons with derating applied
5. Dielectric / material class
6. Qualification and compliance
7. Lifecycle
8. Tier assignment

## What the LLM may add afterwards

Only prose. It receives the requirement, the surviving candidate, and the full
`PolicyResult[]`, and writes a rationale plus any concerns it notices. It cannot
change a tier, overturn an outcome, or resurrect a rejected candidate. If the model's
prose contradicts a `PolicyResult`, the `PolicyResult` is authoritative and the
contradiction is a bug worth logging.

## Reference

- [Per-category rules, derating defaults, and safety-critical detection](./references/category-rules.md)
