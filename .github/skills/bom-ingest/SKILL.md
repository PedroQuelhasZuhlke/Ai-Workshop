---
name: bom-ingest
description: 'Parse and column-map BOM exports from Altium, KiCad, Eagle/Fusion, OrCAD/Allegro and ad-hoc CSV/Excel. Use when implementing or debugging BOM file reading, header detection, EDA profile matching, reference designator expansion, quantity reconciliation, or DNP/do-not-populate handling.'
---

# BOM Ingest

Turns an arbitrary BOM export into `BomLine[]` without losing or inventing anything.
The hard problem is not parsing — it is column mapping across tools that agree on
nothing.

## Principles

1. **Never clean the source.** `BomLine.raw` holds the original cells verbatim. All
   interpretation happens downstream where it can be attributed.
2. **Propose, never guess.** An unrecognized layout produces a mapping proposal the
   engineer confirms. It does not silently pick a column.
3. **Disagreement is data.** If stated quantity conflicts with reference designator
   count, record both and flag it. Do not pick a winner.

## Procedure

### 1. Read the file

- CSV: sniff delimiter (`,` `;` `\t` `|`) and encoding (UTF-8, UTF-8-BOM, cp1252).
  European exports frequently use `;` with `,` as the decimal separator.
- XLSX/XLS: `openpyxl` with `data_only=True`. Reject external links and formulas.
  Enforce limits on file size, sheet count, and row count.
- If multiple sheets, pick by name heuristic (`BOM`, `Bill of Materials`, `Parts`),
  otherwise ask.

### 2. Locate the header row

Exports routinely carry a title block, logo rows, or project metadata above the real
header. Scan the first ~30 rows and score each as a header candidate by: proportion of
non-empty cells, presence of known header tokens, and whether the row below it looks
like data. Record the chosen row index in the artifact.

### 3. Match an EDA profile

Try in order, stopping at the first confident match:

1. **Named profile** — see [EDA export profiles](./references/eda-export-profiles.md)
2. **Project memory** — a mapping previously confirmed for this project
3. **Heuristic** — token matching against the synonym table in the reference
4. **LLM fallback** — only for headers nothing else resolved, one call for the whole
   header row, output tagged `llm_inferred`

Always surface the final mapping for confirmation, whatever produced it. Persist the
confirmed mapping against the project so the next revision is one click.

### 4. Expand reference designators

Split on `,` `;` and whitespace, then expand ranges:

| Input | Output |
|---|---|
| `R1-R4` | `R1 R2 R3 R4` |
| `C1,C3,C7` | `C1 C3 C7` |
| `R1..R3` | `R1 R2 R3` |
| `U1` | `U1` |

Ranges only expand when the prefix matches on both ends and both suffixes are numeric.
`R1-C4` is an error, not a range. Validate the prefix against the designator table in
the reference to get an early category hint.

Duplicate designators **across the whole BOM** are a `BLOCKING` issue — two lines
claiming `R5` means the export is wrong or the BOM has variants.

### 5. Reconcile quantity

`quantity_per_board` is derived from the reference designator count, not from the
stated quantity column. If they disagree, keep the derived value and emit a
`quantity_mismatch` warning carrying both numbers.

If a line has no designators at all (common for mechanical items, adhesives, or
"1 off" entries), fall back to the stated quantity and mark the line
`quantity_source: stated`.

### 6. Detect DNP lines

Do-not-populate lines must be carried through, not dropped — engineers need to see
them, and they must never appear in a purchase plan.

Signals: a `DNP` / `Fitted` / `Populate` / `Install` column; a value or comment of
`DNP`, `DNI`, `NF`, `NP`, `Do Not Populate`, `Do Not Install`, `Not Fitted`,
`Unfitted`, `No Load`; KiCad's explicit `DNP` and `Exclude from BOM` fields.

Mark the line `populate: False` and exclude it from sourcing. Keep it in the artifact.

### 7. Emit

One `BomLine` per source row, in file order, with `row_index`, `raw`,
`reference_designators`, `quantity`, `mapping_profile`, and any issues.

## Common failure modes

| Symptom | Cause |
|---|---|
| Every row unmapped | Header row misdetected — title block above it |
| Quantities all 1 | Range designators not expanded |
| Values become dates | Excel autoformatted `1-10` or `4-7`; read with `data_only` and treat as text |
| Missing last rows | Trailing notes row broke the read; scan to true end |
| Duplicate MPNs across lines | Assembly variants in one file — needs an explicit variant column |
| Mojibake in manufacturer names | cp1252 read as UTF-8; sniff encoding |

## Reference

- [EDA export profiles and column synonyms](./references/eda-export-profiles.md)
