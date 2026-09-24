"""Live `SupplierAdapter` for Farnell / element14.

Farnell's real catalog API authenticates via a `callInfo.apiKey` query-string
parameter; like `mouser.py`, this adapter sends the key as an `Authorization: Bearer`
header instead so a credential can never end up in a logged request URL.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from pcbpick.config.secrets import Credentials
from pcbpick.contracts.enums import ComponentCategory, Packaging, SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.sourcing.suppliers.live_base import (
    LiveSupplierAdapter,
    bearer_header,
    build_catalog_part,
    build_offer,
    hits_for_raw_part,
    map_lifecycle,
    map_rohs_compliance,
)
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller
from pcbpick.sourcing.types import CatalogHit, CatalogPart, SourcingQuery

BASE_URL = "https://api.element14.com/catalog/products"

_CATEGORY_KEYWORDS: tuple[tuple[str, ComponentCategory], ...] = (
    ("resistor", ComponentCategory.RESISTOR),
    ("capacitor", ComponentCategory.CAPACITOR),
    ("inductor", ComponentCategory.INDUCTOR),
    ("crystal", ComponentCategory.CRYSTAL),
    ("oscillator", ComponentCategory.OSCILLATOR),
    ("diode", ComponentCategory.DIODE),
    ("led", ComponentCategory.LED),
    ("transistor", ComponentCategory.TRANSISTOR),
    ("connector", ComponentCategory.CONNECTOR),
    ("switch", ComponentCategory.SWITCH),
    ("relay", ComponentCategory.RELAY),
    ("fuse", ComponentCategory.FUSE),
    ("transformer", ComponentCategory.TRANSFORMER),
)

_PACKAGING_KEYWORDS: tuple[tuple[str, Packaging], ...] = (
    ("cut tape", Packaging.CUT_TAPE),
    ("reel", Packaging.REEL),
    ("tube", Packaging.TUBE),
    ("tray", Packaging.TRAY),
    ("bulk", Packaging.BULK),
)


def _map_category(raw: str | None) -> ComponentCategory:
    if raw is None:
        return ComponentCategory.UNKNOWN
    lowered = raw.casefold()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in lowered:
            return category
    return ComponentCategory.UNKNOWN


def _map_packaging(raw: str | None) -> Packaging | None:
    """Keyword-matches Farnell's stated `packOption`. `None` if Farnell stated no
    recognizable packaging (missing or unrecognized text) -- never a guessed member;
    `build_catalog_part`/`build_offer` drop the sku/offer rather than validate one.
    """
    if raw is not None:
        lowered = raw.casefold()
        for keyword, packaging in _PACKAGING_KEYWORDS:
            if keyword in lowered:
                return packaging
    return None


def _parse_lead_time_weeks_to_days(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) * 7 if digits else None


def _raw_part_from_farnell_json(product: dict[str, Any]) -> dict[str, Any]:
    price_breaks = sorted(
        (
            {
                "quantity": int(pb["from"]),
                "unit_price": str(pb["cost"]),
                "currency": pb.get("currency", "USD"),
            }
            for pb in product.get("prices", [])
        ),
        key=lambda pb: pb["quantity"],
    )
    stock_raw = product.get("stock", {}).get("level")
    moq_raw = product.get("translatedMinimumOrderQuantity")
    spq_raw = product.get("translatedOrderMultiple")
    packaging = _map_packaging(product.get("packOption"))

    return {
        "mpn": product["translatedManufacturerPartNumber"],
        "manufacturer": product.get("brandName", ""),
        "category": _map_category(product.get("category")).value,
        # Farnell's attributes are description-shaped, not (value, unit, tolerance)
        # triples; passed through as no parameters — normalize owns text -> typed values.
        "parameters": {},
        "footprint": {"raw_text": product.get("translatedPackageName")},
        "lifecycle": map_lifecycle(product.get("status")).value,
        "compliance": [tag.value for tag in map_rohs_compliance(product.get("rohsStatus"))],
        "skus": [
            {
                "sku": product["sku"],
                "packaging": packaging.value if packaging is not None else None,
                "stock": int(stock_raw) if stock_raw is not None else None,
                "moq": int(moq_raw) if moq_raw is not None else None,
                "spq": int(spq_raw) if spq_raw is not None else None,
                "price_breaks": price_breaks,
                "lead_time_days": _parse_lead_time_weeks_to_days(product.get("leadStatus")),
            }
        ],
    }


def _extract_products(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        # `parse_float=Decimal` so a price literal (e.g. `0.0089`) is parsed straight
        # to `Decimal` -- it never transits through `float`, per
        # `.github/instructions/python.instructions.md`'s "float for money is a bug".
        data = json.loads(response.text, parse_float=Decimal)
    except ValueError:
        return []
    products = data.get("premierFarnellPartNumberReturn", {}).get("products")
    return list(products) if products else []


class FarnellAdapter(LiveSupplierAdapter):
    """Live `SupplierAdapter` backed by the Farnell / element14 catalog API."""

    def __init__(
        self,
        *,
        credentials: Credentials,
        http_client: httpx.Client,
        snapshot_dir: Path,
        resilient_caller: ResilientCaller | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            supplier_id=SupplierId.FARNELL,
            http_client=http_client,
            resilient_caller=resilient_caller
            or ResilientCaller(rate_limit=RateLimitConfig(max_calls=60, period_seconds=60)),
            snapshot_dir=snapshot_dir,
            now_fn=now_fn,
            run_id=run_id,
        )
        self._credentials = credentials

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        keyword = (
            query.specified_mpn.mpn if query.specified_mpn is not None else query.category.value
        )
        request = self._http_client.build_request(
            "GET",
            BASE_URL,
            params={"term": f"manuPartNum:{keyword}", "resultsSettings.responseGroup": "large"},
            headers=bearer_header(self._credentials.api_key),
        )
        response = self._send(request, query=keyword)
        if response is None:
            return []
        raw_parts = [_raw_part_from_farnell_json(p) for p in _extract_products(response)]
        if raw_parts:
            self._write_snapshot(raw_parts)
        hits: list[CatalogHit] = []
        for raw_part in raw_parts:
            hits.extend(hits_for_raw_part(raw_part))
        return hits

    def details(self, mpn: str) -> CatalogPart | None:
        request = self._http_client.build_request(
            "GET",
            BASE_URL,
            params={"term": f"manuPartNum:{mpn}", "resultsSettings.responseGroup": "large"},
            headers=bearer_header(self._credentials.api_key),
        )
        response = self._send(request, query=mpn)
        if response is None:
            return None
        products = _extract_products(response)
        if not products:
            return None
        raw_part = _raw_part_from_farnell_json(products[0])
        snapshot = self._write_snapshot([raw_part])
        return build_catalog_part(
            raw_part, snapshot_id=snapshot.snapshot_id, fetched_at=snapshot.fetched_at
        )

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del quantity  # Farnell's product response always returns the full price ladder
        request = self._http_client.build_request(
            "GET",
            BASE_URL,
            params={"term": f"id:{sku}", "resultsSettings.responseGroup": "large"},
            headers=bearer_header(self._credentials.api_key),
        )
        response = self._send(request, query=sku)
        if response is None:
            return []
        offers: list[SupplierOffer] = []
        for product in _extract_products(response):
            raw_part = _raw_part_from_farnell_json(product)
            snapshot = self._write_snapshot([raw_part])
            for raw_sku in raw_part["skus"]:
                if raw_sku["sku"] != sku:
                    continue
                offer = build_offer(
                    raw_sku,
                    supplier=SupplierId.FARNELL,
                    snapshot_id=snapshot.snapshot_id,
                    fetched_at=snapshot.fetched_at,
                )
                if offer is not None:
                    offers.append(offer)
        return offers
