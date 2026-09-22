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
- `parameters`: only parameters you can support from the row text. Every value's
  `source` must be `"llm_inferred"`.
- `footprint`: only if the row text states a package, else `null`.
- `compliance_required`: only tags explicitly stated or unambiguously implied.
- `notes`: a short explanation of your reasoning, or `null`.

Never invent a numeric value the text does not support. Leave a field absent (not a
guessed value) when the text is genuinely silent on it.
