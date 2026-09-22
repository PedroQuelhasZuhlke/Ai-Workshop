---
name: part-normalization
description: 'Parse component values, tolerances, ratings and package codes into SI units. Use when implementing or debugging value parsing (4k7, 100n, 0.1uF, 1R0), EIA/RKM notation, capacitor 3-digit codes, tolerance letter codes, dielectric classes, package code conversion, or component category classification.'
---

# Part Normalization

Converts a `BomLine` into a `NormalizedRequirement` with SI-base-unit parameters and
honest confidence. Deterministic parsing first; the LLM only sees what the parser
could not handle.

## Rules

1. Every parsed value keeps `raw_text`. Display and audit use the original.
2. A value the source does not state is `None` and goes in `unresolved`. Never infer a
   voltage rating, a tolerance, or a dielectric that was not written down.
3. Parse order matters: category hint → value → tolerance → ratings → package. A
   resistor `1M` is 1 MΩ; a capacitor `1M` in EIA tolerance context means ±20%.
4. Ambiguity is recorded, not resolved by preference. Two plausible readings means
   `BLOCKING`.

## Procedure

### 1. Category hint

Combine reference designator prefix, footprint family, and description keywords. All
three agreeing gives high confidence; disagreement drops confidence and may flag.

### 2. Parse the value

See [value notation](./references/value-notation.md) for the full grammar. Handle, in
order: RKM/EIA shorthand (`4k7`, `1R0`, `2M2`), SI prefix notation (`10k`, `100nF`,
`4.7uF`), plain numbers with a unit, capacitor 3-digit codes (`104`), and bare numbers
(unit implied by category — flag these).

Store in SI base units as `Decimal`:

| Category | Base unit |
|---|---|
| resistor | `ohm` |
| capacitor | `farad` |
| inductor, ferrite bead | `henry` |
| voltage rating | `volt` |
| current rating | `ampere` |
| power rating | `watt` |
| temperature | `celsius` |

Never use binary floating point anywhere in this path. `0.1` µF must round-trip.

### 3. Parse tolerance

Explicit forms (`±1%`, `1%`, `+/-5%`), letter codes appended to a value (`103K`),
and asymmetric forms (`+80/-20%`). Letter code meaning depends on whether the part is
a resistor or a capacitor — see the reference table. Getting `K` wrong turns ±10% into
1000×.

### 4. Extract ratings and characteristics

From the value string, description, and dedicated columns:

- Voltage rating (`50V`, `WVDC`, `25VDC`)
- Power rating (`1/4W`, `0.25W`, `250mW`)
- Current rating (`2A`, `500mA`), and for inductors saturation vs RMS current
- Dielectric / temperature coefficient (`X7R`, `C0G`, `NP0`, `Y5V`)
- Temperature range (`-40..85C`, `-55°C to +125°C`)
- Qualification and compliance tokens (`AEC-Q200`, `RoHS`, `REACH`, `automotive`)

Each extracted value is tagged with where it came from: a dedicated column is higher
confidence than a substring of a free-text description.

### 5. Normalize the package

Convert to a canonical package code with an explicit dimension system. See the package
section of the [value notation reference](./references/value-notation.md). Metric and
imperial passive codes collide dangerously — always record which system was resolved
and why.

### 6. Validate against the category declaration

Each `ComponentCategory` declares required and optional parameters in
`contracts/categories.py`. A resistor without resistance is `BLOCKING`. A capacitor
without a voltage rating is `BLOCKING` — it cannot be safely sourced.

### 7. Score confidence and emit

| Confidence | Meaning |
|---|---|
| `high` | All required parameters parsed deterministically from dedicated columns |
| `medium` | Some parameters extracted from free text, all agree |
| `low` | Conflicting signals, or values recovered by LLM fallback |

Anything below `high` on a safety-critical part is `BLOCKING` regardless.

## LLM fallback

Only for rows where the deterministic parser produced nothing usable. Send the row's
raw cells and the category hint — never the whole BOM, never designators or project
identifiers. Output is a `NormalizedRequirementFragment`, schema-validated, every
field tagged `source: llm_inferred`, every field requiring engineer confirmation
before sourcing.

The model may interpret. It may not compute, convert units, or decide a package
system.

## Known traps

| Trap | Correct handling |
|---|---|
| `1M` on a capacitor | Could be 1 MΩ misfiled, 1 mF, or ±20% tolerance code. Flag. |
| `100` bare on a capacitor | Could be 100 pF (3-digit code) or 100 µF. Flag. |
| `4R7` vs `4.7R` vs `4k7` | 4.7 Ω, 4.7 Ω, 4700 Ω |
| `0603` with no system stated | 5× dimension error risk. Resolve via EDA convention, record it. |
| `X7R` vs `C0G` | Different dielectric classes. Never interchangeable. |
| `0R` / `0 Ohm` | A jumper. Valid resistance of 0, but needs a current rating, not a power rating. |
| Value in a `Comment` column that is actually an MPN | Detect MPN shape and route to `specified_mpn` |
| `µ` encoded as `μ`, `u`, or mojibake | Normalize all micro-sign variants before parsing |

## Reference

- [Value notation, tolerance codes, dielectrics and package codes](./references/value-notation.md)
