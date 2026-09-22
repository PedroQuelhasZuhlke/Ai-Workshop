---
name: supplier-export
description: 'Generate supplier BOM import files for Mouser, DigiKey and Farnell as CSV or XLSX. Use when implementing or debugging exporters, supplier upload column templates, CSV formula injection prevention, approval gating, or export validation.'
---

# Supplier Export

Produces the file an engineer uploads to a distributor's BOM tool. This is the last
stage and the only one whose output leaves the system, so it is the strictest.

## Gates before any file is produced

1. The plan must be **approved** — a recorded approval with a named engineer, a
   timestamp, and the `plan_hash`.
2. No offer in the plan may be stale. Re-validate against the supplier before writing.
3. No line may be an unreviewed tier 2 or higher substitution.
4. No DNP line may appear.
5. Every line must have a resolved order quantity satisfying MOQ and SPQ.

A failure at any gate aborts the export with a specific reason. Never produce a
partial file.

## Column templates are versioned data, not code

Supplier upload formats change. Store each as a versioned template in
`src/pcbpick/exporters/templates/<supplier>/v<N>.yaml`, with the date it was verified
against the supplier's published template and a link to that template.

**Verify the current template against the supplier's own documentation before
trusting any column list, including the ones below.** Treat these as starting points.

### Mouser

Typically accepts CSV or XLSX with:

```
Mouser Part Number, Manufacturer Part Number, Quantity, Customer Part Number
```

Either the Mouser part number or the manufacturer part number identifies the line.
Supplying both improves match rate. `Customer Part Number` is the natural place for
the reference designator list or an internal identifier.

### DigiKey

Typically accepts CSV with:

```
Quantity, Digi-Key Part Number, Manufacturer Part Number, Customer Reference
```

DigiKey part numbers carry packaging suffixes (`-1-ND` cut tape, `-2-ND` tape and
reel, `-6-ND` digi-reel). The suffix is part of the order identity — emit the exact
SKU from the offer, never a stripped base number.

### Farnell / element14

Typically accepts CSV with:

```
Order Code, Quantity, Line Note
```

Order codes are region-specific. Record which regional site the snapshot came from and
emit codes for that region only.

## Content rules

- Emit the exact `sku` from the `SupplierOffer` that the plan selected. Do not
  reconstruct, normalize, or strip it.
- Quantity is the computed `order_qty` after MOQ/SPQ. Never the raw requirement count.
- Reference designators go in the customer reference field where one exists. Truncate
  to the field's documented limit and record the truncation.
- One file per supplier. Never a combined file.
- Include a companion human-readable summary (not uploaded) listing plan hash,
  snapshot IDs, approver, and timestamp.

## Formula injection — mandatory

Any cell whose value begins with `=`, `+`, `-`, `@`, tab, or carriage return can be
interpreted as a formula by Excel, Google Sheets, and LibreOffice. BOM content is
user-supplied, so this is a live injection path into whoever opens the file.

Neutralize every cell in every exported file:

```python
_RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

def neutralize(cell: str) -> str:
    if cell and cell[0] in _RISKY_PREFIXES:
        return "'" + cell
    return cell
```

Apply to **all** cells, including ones the system generated — a manufacturer name or
description sourced from a supplier catalog is untrusted input too.

Additionally:

- Quote fields containing the delimiter, quotes, or newlines, per RFC 4180.
- Write CSV with `csv.writer` and `quoting=csv.QUOTE_MINIMAL`. Never build CSV with
  string concatenation or f-strings.
- For XLSX, write values as text where the supplier expects text. Part numbers like
  `1N4148` and `0402` must not be coerced into numbers or dates.

## Encoding and formatting

- UTF-8 with BOM for CSV, so Excel on Windows opens it correctly.
- CRLF line endings — supplier tools are more tolerant of CRLF than of LF.
- No thousands separators in quantities. No currency symbols in numeric fields.
- Decimal separator is `.` regardless of locale.

## Validation before download

1. Validate the generated rows against the supplier template's schema: required
   columns present, types correct, quantities positive integers.
2. Round-trip the file: read it back with the same parser the ingest stage uses and
   assert the parsed rows match the plan lines exactly.
3. Assert no cell begins with a risky prefix after neutralization.
4. Record the file hash in the run artifact alongside the `plan_hash`.

The round-trip test catches encoding, quoting, and coercion bugs that unit tests on
the row dictionaries cannot.

## Audit record

Every export writes an immutable record: `plan_hash`, `snapshot_ids`, supplier, file
hash, approver, approval timestamp, template version, and the exporter version. Six
months later, an engineer must be able to answer "why did we buy this part" from
stored data alone.
