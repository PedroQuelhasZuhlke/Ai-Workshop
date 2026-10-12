# `demo/` — offline mock suppliers and a demo BOM

Data the **app** uses when live suppliers are off, plus a BOM to try it with. It is not
test input: test and eval fixtures live in [`fixtures/`](../fixtures). Tests and the
`mock_suppliers_demo_bom_through_policy` eval case do read these files, so they stay
verified when normalization or policy changes — editing them can fail those tests.

```
demo/
  boms/mock_suppliers_demo.csv
  catalogs/mock_mouser.json     # supplier: mouser
  catalogs/mock_digikey.json    # supplier: digikey
  catalogs/mock_farnell.json    # supplier: farnell
```

Wired in by `DEFAULT_MOCK_SUPPLIER_SNAPSHOTS` in `src/pcbpick/api/settings.py`. Each catalog
declares its own `supplier`, and `FixtureAdapter(..., supplier=...)` refuses a file that
declares another, so offers are always stamped with the right supplier.

## Try it

Start the app (`./scripts/start-dev.ps1`) and upload `demo/boms/mock_suppliers_demo.csv`. Every
row resolves without manual edits, so you can go straight to candidate review and plan
comparison. Only parts in the mock catalogs can be found.

## The data is fictional

Hand-authored: SKUs are `MOCK-<MOU|DKR|FAR>-...`, and prices, stock, MOQ and SPQ are invented.
Never order from them. Parameter values for shared MPNs are copied from
`fixtures/catalogs/kicad_golden_snapshot.json`.

Footprints deliberately use the form `normalize/package.py` emits (`0603`, `0402`, `0805`,
`mounting`, `length_mm`, `width_mm`; `SOIC-8` for the op-amp, nothing else) rather than the
IPC-style `RESC1608X55N` + `pin_count` + `height_mm` form the golden snapshot uses, because
`footprint_identity` compares every `Footprint` field exactly and the demo BOM goes through
the real normalizer. `fetched_at` is the fixed `2026-01-15T00:00:00Z`, so offers read as
stale against the wall clock in the app and approval needs the stale-offer acknowledgement.

| What it exercises | Where |
|---|---|
| One MPN, three suppliers, different price/stock/MOQ | `RC0603FR-0710KL`, `LM358DR` |
| Same MPN with two SKUs (cut tape + reel, MOQ/SPQ 5000) | DigiKey `RC0603FR-0710KL` |
| A part only one supplier carries | Farnell `CRCW0603100RFKEA` |
| Zero stock with a lead time | Mouser `ERJ-3EKF1001V` (56 d) |
| Offer priced in EUR (excluded from a USD plan) | Farnell `CL10B104KB8NNNC` |
| Wrong-footprint decoys for parametric rows | `RC0805FR-074K7L`, `GRM155R71C104KA88D` |
| MOQ/SPQ above 1 | Farnell (10, 10 / 5, 5) |
| A price where splitting suppliers beats consolidating | Mouser `LM358DR` at 100 pcs |
| A row whose MPN no catalog carries (no candidates) | `RC0603FR-072K2L` |
