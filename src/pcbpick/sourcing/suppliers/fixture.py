"""`FixtureAdapter` — a `SupplierAdapter` backed by pinned JSON catalog snapshots.

This *is* the "I/O exception" `.github/instructions/pipeline-stages.instructions.md`
carves out for `sourcing/suppliers/`: all reading happens once, at construction, from
local files. After `__init__` returns, no method here touches the filesystem or the
network again.

An adapter stamps every offer with its `supplier` (default `SupplierId.FIXTURE`).
Passing `MOUSER`/`DIGIKEY`/`FARNELL` makes it an offline *mock* of that supplier, so
plans and exports can be exercised without live access. Every snapshot it loads must
declare that same `supplier`, so a file is never silently attributed to another one.

## Snapshot file schema

One JSON file per pinned catalog state:

```jsonc
{
  "snapshot_id": "string, stable, content-addressed-ish identifier for this pinned catalog state",
  "supplier": "fixture | mouser | digikey | farnell, must equal the adapter's supplier",
  "fetched_at": "ISO 8601 UTC timestamp, e.g. 2026-01-15T00:00:00Z",
  "parts": [
    {
      "mpn": "string",
      "manufacturer": "string, may be raw/uncanonicalized — run through normalize_manufacturer",
      "category": "one of ComponentCategory's values, e.g. 'resistor'",
      "parameters": {
        "<name>": {
          "value": "10000",
          "unit": "ohm",
          "tolerance_pct": "1",
          "raw_text": "10k",
          "source": "datasheet"
        }
      },
      "footprint": { "package_code": "0603", "mounting": "smt", "...": "Footprint fields" },
      "lifecycle": "active | nrnd | eol | obsolete | unknown",
      "compliance": ["rohs", "reach"],
      "skus": [
        {
          "sku": "string, supplier order number",
          "packaging": "cut_tape | reel | tube | tray | bulk",
          "stock": 12000,
          "moq": 1,
          "spq": 1,
          "price_breaks": [{ "quantity": 1, "unit_price": "0.0123", "currency": "USD" }],
          "lead_time_days": null
        }
      ]
    }
  ]
}
```

Numeric leaves that map to `Decimal` fields (`ParameterValue.value`/`tolerance_pct`/`min`/
`max`, `PriceBreak.unit_price`) are JSON strings, per the convention established in
`fixtures/policy/README.md` — never bare JSON numbers, so no binary-float rounding can
enter a snapshot. `stock`, `moq`, `spq`, and `lead_time_days` may be JSON `null`; they map
straight to `None` and are never defaulted to a number.

## Matching rules

- `search()`: if `query.specified_mpn` is set, match on exact (case-sensitive) `mpn`
  equality — this is what lets the tier-0 exact-MPN policy path work. Otherwise, match on
  `category` equality, plus — only when the named primary parametric key for that category
  is present with a known `.value` on *both* the query and the candidate part — exact
  equality on that value. A category with no entry in `_PRIMARY_PARAMETER_BY_CATEGORY`
  (or a query/part missing that parameter) matches on category alone. This is deliberately
  simple: full parametric range/tolerance matching is out of scope for this milestone. One
  `CatalogHit` is returned per (part, SKU) pair.
- `details()`: exact `mpn` match. If more than one loaded part shares that `mpn` (the "one
  MPN, multiple manufacturers" case), returns the first found in file-then-list order.
  `details()`'s signature is `mpn`-only, so it cannot disambiguate manufacturers on its
  own — `search()` already exposes every manufacturer sharing an MPN via distinct
  `CatalogHit`s, which is how a caller disambiguates before calling `details()` with
  enough context (e.g. cross-checking the returned `CatalogPart.manufacturer`).
- `offers()`: finds the `CatalogSku` with the exact `sku` string across every loaded part,
  and returns a list of exactly one `SupplierOffer` (or `[]` if the SKU is unknown), stamped
  with the real `snapshot_id`/`fetched_at` from the snapshot file that SKU came from and
  `supplier=<the adapter's supplier_id>`. `quantity` is accepted per the protocol but ignored: this
  adapter always returns the full pinned price-break ladder; a real supplier's adapter might
  filter by requested quantity, this one doesn't need to.

  **Known contract gap:** `contracts.offer.SupplierOffer.moq`/`.spq` are required positive
  `int`s today, but a real catalog can legitimately not state either (see the "missing
  MOQ/SPQ" fixture case). Fabricating a value to satisfy the type would violate the
  "never default stock/moq/spq" rule, so when the matched SKU's `moq` or `spq` is `None`,
  `offers()` returns `[]` rather than a fabricated offer. `search()`/`details()` still
  expose the true `None` via `CatalogSku` for this case. Widening `SupplierOffer.moq`/`.spq`
  to `int | None` is a versioned, major-bump contract change per
  `.github/instructions/contracts.instructions.md` — out of this package's scope; flagged
  for the contracts owner rather than worked around here.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pcbpick.contracts.enums import SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.suppliers.protocol import SupplierAdapter
from pcbpick.sourcing.types import CatalogHit, CatalogPart, CatalogSku, SourcingQuery

_PRIMARY_PARAMETER_BY_CATEGORY: dict[str, str] = {
    "resistor": "resistance",
    "capacitor": "capacitance",
    "inductor": "inductance",
    "crystal": "frequency",
    "oscillator": "frequency",
}


def _load_snapshot_file(path: Path, supplier: SupplierId) -> list[CatalogPart]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("supplier") != supplier.value:
        raise ValueError(
            f"snapshot {path} declares supplier {raw.get('supplier')!r}, "
            f"but the adapter is for {supplier.value!r}"
        )
    snapshot_id: str = raw["snapshot_id"]
    fetched_at = datetime.fromisoformat(raw["fetched_at"])
    parts: list[CatalogPart] = []
    for raw_part in raw["parts"]:
        merged = {
            **raw_part,
            "manufacturer": normalize_manufacturer(raw_part["manufacturer"]),
            "snapshot_id": snapshot_id,
            "fetched_at": fetched_at,
        }
        parts.append(CatalogPart.model_validate(merged))
    return parts


class FixtureAdapter(SupplierAdapter):
    """Reads one or more pinned JSON snapshot files once, at construction.

    Never touches the filesystem or the network again after `__init__` returns; see the
    module docstring for the snapshot file schema and matching rules.
    """

    def __init__(
        self, paths: list[Path] | list[str], supplier: SupplierId = SupplierId.FIXTURE
    ) -> None:
        self.supplier_id: SupplierId = supplier
        parts: list[CatalogPart] = []
        for raw_path in paths:
            parts.extend(_load_snapshot_file(Path(raw_path), supplier))
        self._parts: tuple[CatalogPart, ...] = tuple(parts)

        skus_by_sku: dict[str, tuple[CatalogPart, CatalogSku]] = {}
        for part in self._parts:
            for sku in part.skus:
                # First sku string wins if a snapshot ever repeats one across files.
                skus_by_sku.setdefault(sku.sku, (part, sku))
        self._skus_by_sku = skus_by_sku

    @classmethod
    def from_directory(
        cls,
        directory: Path | str,
        pattern: str = "*.json",
        supplier: SupplierId = SupplierId.FIXTURE,
    ) -> "FixtureAdapter":
        """Loads every file matching `pattern` in `directory`, sorted by filename.

        Sorted so that `details()`'s "first found in file order" rule is deterministic
        regardless of the operating system's directory-listing order.
        """
        return cls(sorted(Path(directory).glob(pattern)), supplier)

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        hits: list[CatalogHit] = []
        if query.specified_mpn is not None:
            target = query.specified_mpn.mpn
            for part in self._parts:
                if part.mpn == target:
                    hits.extend(self._hits_for_part(part))
            return hits

        primary_param = _PRIMARY_PARAMETER_BY_CATEGORY.get(query.category.value)
        query_param = query.parameters.get(primary_param) if primary_param else None
        query_value = query_param.value if query_param is not None else None

        for part in self._parts:
            if part.category != query.category:
                continue
            if query_value is not None and primary_param is not None:
                part_param = part.parameters.get(primary_param)
                part_value = part_param.value if part_param is not None else None
                if part_value is not None and part_value != query_value:
                    continue
            hits.extend(self._hits_for_part(part))
        return hits

    def details(self, mpn: str) -> CatalogPart | None:
        for part in self._parts:
            if part.mpn == mpn:
                return part
        return None

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del quantity  # fixture snapshots return the full ladder regardless of quantity
        found = self._skus_by_sku.get(sku)
        if found is None:
            return []
        part, catalog_sku = found
        if catalog_sku.moq is None or catalog_sku.spq is None:
            return []  # see module docstring: known SupplierOffer contract gap
        return [
            SupplierOffer(
                supplier=self.supplier_id,
                sku=catalog_sku.sku,
                packaging=catalog_sku.packaging,
                stock=catalog_sku.stock,
                moq=catalog_sku.moq,
                spq=catalog_sku.spq,
                price_breaks=catalog_sku.price_breaks,
                lead_time_days=catalog_sku.lead_time_days,
                snapshot_id=part.snapshot_id,
                fetched_at=part.fetched_at,
            )
        ]

    @staticmethod
    def _hits_for_part(part: CatalogPart) -> list[CatalogHit]:
        return [
            CatalogHit(mpn=part.mpn, manufacturer=part.manufacturer, sku=sku.sku)
            for sku in part.skus
        ]
