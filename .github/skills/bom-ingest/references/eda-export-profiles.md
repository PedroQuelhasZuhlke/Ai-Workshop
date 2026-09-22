# EDA Export Profiles and Column Synonyms

Column sets vary by tool **and** by user template. Treat these as starting profiles
with confidence scoring, never as guarantees. Always confirm the resolved mapping with
the engineer.

## Altium Designer

Default BOM (BomDoc / Report Manager) headers:

```
Designator, Comment, Description, Footprint, LibRef, Quantity,
Manufacturer, Manufacturer Part Number, Supplier 1, Supplier Part Number 1
```

Notes:

- `Comment` usually carries the value (`10k`, `100nF`) but is frequently repurposed
  as a part number. Inspect the column's content, not just its name.
- `Footprint` is a library footprint name (`CAP_0402`, `RESC1608X55N`), not a bare
  package code. Extract the package with the pattern table below.
- Variant exports add a `Fitted` column with `Fitted` / `Not Fitted`.
- Multi-supplier templates repeat `Supplier N` / `Supplier Part Number N`.

## KiCad

KiCad 6 and earlier (BOM plugin CSV):

```
Ref, Qnty, Value, Cmp name, Footprint, Description, Vendor
```

KiCad 7/8/9 (built-in BOM export):

```
Reference, Value, Datasheet, Footprint, Qty, DNP, Exclude from BOM, ${FIELD}
```

Notes:

- `Footprint` is fully qualified: `Resistor_SMD:R_0603_1608Metric`. The `Metric`
  suffix disambiguates package codes — use it, it is authoritative.
- `DNP` is an explicit boolean. Trust it over comment-text heuristics.
- Custom fields (`MPN`, `Manufacturer`, `Tolerance`, `Voltage`) are common and
  user-named. These are the main target for heuristic and LLM mapping.

## Eagle / Fusion Electronics

```
Part, Value, Device, Package, Description
```

Notes:

- `Part` is the designator column — the name is misleading.
- `Value` is often empty for ICs; `Device` carries the real identity.
- `Package` is a bare package name (`C0603`, `R0805`, `SOT23-5`).
- Eagle's default BOM is one row per part, not grouped. Grouping happens downstream.

## OrCAD / Allegro

```
Item, Quantity, Reference, Part Number, PCB Footprint, Value, Description
```

Notes:

- Allegro BOM reports carry a multi-line header block before the table. Header
  detection must skip it.
- `Part Number` is usually an **internal** company part number, not an MPN. Do not
  send it to a supplier search as though it were an MPN.
- Reference lists are space-separated, not comma-separated.

## Ad-hoc CSV / Excel

The most common real case. No profile applies; rely on the synonym table, then the
LLM fallback. Expect: merged cells, a title block, a totals row at the bottom, units
embedded in headers (`Value (Ω)`), and a mix of languages.

## Column synonym table

Match case-insensitively, ignoring punctuation and whitespace.

| Target field | Synonyms |
|---|---|
| `reference_designators` | ref, refs, reference, references, designator, designators, refdes, part, item ref, position |
| `quantity` | qty, qnty, quantity, count, amount, anzahl, aantal, stk |
| `value` | value, comment, val, rating, wert, waarde |
| `description` | description, desc, comment, notes, beschreibung, omschrijving |
| `footprint` | footprint, package, pcb footprint, case, case code, pattern, housing, gehäuse |
| `manufacturer` | manufacturer, mfr, mfg, maker, brand, hersteller, fabrikant |
| `mpn` | manufacturer part number, mfr part, mfr pn, mpn, part number, partnumber, mfg p/n, type |
| `supplier` | supplier, vendor, distributor, source, leverancier |
| `supplier_pn` | supplier part number, order code, order number, sku, distributor pn, bestellnummer |
| `populate` | dnp, dni, fitted, populate, install, no load, bestücken |
| `tolerance` | tolerance, tol |
| `voltage` | voltage, voltage rating, vdc, wvdc, rated voltage, spannung |
| `power` | power, wattage, power rating, watt |
| `dielectric` | dielectric, temperature coefficient, tc, material, char |

Ambiguity to watch: `Comment` and `Description` both appear and can each hold the
value. `Part` means designator in Eagle and part number almost everywhere else.

## Reference designator prefixes

Used for validation and as an early category hint. Prefixes may carry a numeric suffix
and optional board prefix (`A1R5`).

| Prefix | Category |
|---|---|
| `R`, `RN`, `RV`, `VR`, `POT` | resistor, resistor network, variable resistor |
| `C`, `CN` | capacitor |
| `L` | inductor |
| `FB`, `FE` | ferrite bead |
| `D`, `CR`, `Z`, `ZD` | diode |
| `LED`, `DS` | LED / indicator |
| `Q`, `T`, `TR` | transistor |
| `U`, `IC`, `A` | integrated circuit |
| `Y`, `X`, `XTAL` | crystal |
| `OSC`, `G` | oscillator |
| `J`, `P`, `CN`, `CON`, `X` | connector |
| `SW`, `S` | switch |
| `K`, `RLY` | relay |
| `F`, `FU` | fuse |
| `T`, `TX` | transformer |
| `BT`, `BAT` | battery |
| `TP` | test point |
| `MH`, `H` | mechanical / mounting hole |
| `JP`, `LK` | jumper / link |
| `MOV`, `RV` | varistor |
| `ANT`, `AE` | antenna |

Collisions are real: `T` is both transistor and transformer, `X` is both crystal and
connector, `CN` is both capacitor network and connector, `RV` is both varistor and
variable resistor. Resolve with the value, footprint, and description together — never
on the prefix alone.

## Footprint string → package code

Library footprint names embed the package. Extract with patterns, then normalize:

| Pattern | Example | Package |
|---|---|---|
| `[A-Z]+_?(\d{4})$` | `CAP_0402`, `R0603` | imperial 4-digit |
| `(\d{4})Metric` | `R_0603_1608Metric` | metric, convert to imperial |
| `RESC(\d{4})` | `RESC1608X55N` | IPC metric, convert |
| `CAPC(\d{4})` | `CAPC2012X110N` | IPC metric, convert |
| `SOT-?(\d+)(-\d+)?` | `SOT23-5` | SOT family |
| `SOIC-?(\d+)` | `SOIC-8` | SOIC |
| `[QD]FN-?(\d+)` | `QFN-32` | QFN/DFN |
| `[LT]?QFP-?(\d+)` | `LQFP-64` | QFP family |

**The 0603 trap:** imperial `0603` is 1.6 × 0.8 mm; metric `0603` is 0.6 × 0.3 mm,
which is imperial `0201`. A silent misread is a 5× size error that will not fit the
land pattern. If the footprint string does not state `Metric` or an IPC prefix,
resolve using the EDA tool's convention and record which convention was applied.
