# normalize_fallback

Interpret one BOM row the deterministic parser could not resolve. You are not asked
to compute, convert units, rank, or decide a package system — only to interpret free
text and propose values a human engineer will confirm.

## Input

- `row`: the raw cell values for this row, with reference designators, project name,
  and file path already stripped.
- `category_hint`: the category the deterministic classifier arrived at, or `null` if
  it could not determine one.

## Output

Return a single JSON object matching `NormalizedRequirementFragment`:

- `category`: your best guess at the `ComponentCategory`, or `null` if you cannot tell.
  Must be exactly one of: `resistor`, `capacitor`, `inductor`, `ferrite_bead`, `diode`,
  `led`, `transistor`, `ic_analog`, `ic_digital`, `ic_power`, `ic_rf`, `crystal`,
  `oscillator`, `connector`, `switch`, `relay`, `fuse`, `transformer`, `mechanical`,
  `module`, `unknown`.
- `parameters`: a JSON **object** (never a list) keyed by parameter name, e.g.
  `"supply_voltage"` or `"frequency"`. Include a parameter only if the row text supports
  it; otherwise leave it out. Use `{}` when nothing is supported. Each value is an
  object with:
  - `value`: the number as a string in SI base units (volts, hertz, ohms, farads, ...),
    or `null` if the text names the parameter but gives no number.
  - `unit`: the SI unit name, e.g. `"volt"`.
  - `raw_text`: the exact, non-empty text from the row this came from.
  - `source`: always `"llm_inferred"`.
- `footprint`: only if the row text states a package, else `null`. An object with
  optional `package_code`, `mounting` (exactly `"smt"` or `"tht"`), `pin_count` and
  `raw_text`; omit fields the text does not state.
- `compliance_required`: a list of tags, each exactly one of `rohs`, `reach`,
  `aec_q100`, `aec_q200`. Only tags explicitly stated or unambiguously implied; `[]`
  if none.
- `notes`: a short explanation of your reasoning, or `null`.

Example output for a row with description `"LDO regulator 3.3V SOT-23-5"`:

```json
{
  "category": "ic_power",
  "parameters": {
    "output_voltage": {
      "value": "3.3",
      "unit": "volt",
      "raw_text": "3.3V",
      "source": "llm_inferred"
    }
  },
  "footprint": {"package_code": "SOT-23-5", "mounting": "smt", "raw_text": "SOT-23-5"},
  "compliance_required": [],
  "notes": "Described as an LDO regulator with a 3.3V output."
}
```

Example output for a row that says nothing usable:

```json
{
  "category": null,
  "parameters": {},
  "footprint": null,
  "compliance_required": [],
  "notes": null
}
```

Never invent a numeric value the text does not support. Leave a field absent (not a
guessed value) when the text is genuinely silent on it. Never use an empty string as a
placeholder for `value`, `unit` or `raw_text`.
