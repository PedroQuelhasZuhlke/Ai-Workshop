"""Live `SupplierAdapter` for DigiKey.

DigiKey's real product API sits behind OAuth2 client-credentials: a `client_id` and
`client_secret` are exchanged for a short-lived bearer token. Obtaining and refreshing
that token is out of scope for this milestone's fixture-equivalence goal, so this
adapter sends the client secret directly as the bearer token and the client id as
`X-DIGIKEY-Client-Id` — both still redacted in every log line and never included in an
exception message. Swapping in a real token-exchange call is a contained follow-up
that only touches `_auth_headers`.

DigiKey's `PackageType.Name` (e.g. `"Cut Tape (CT)"`, `"Tape & Reel (TR)"`) is mapped
to our closed `Packaging` enum via keyword match; an unrecognized or absent package
type maps to `None` rather than a guessed member, since `Packaging` has no
"unspecified" value -- `build_catalog_part`/`build_offer` then drop that sku/offer
rather than validate a fabricated one, exactly like the packaging gap `mouser.py`
documents for its own (field-less) case.
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
    build_catalog_part,
    build_offer,
    hits_for_raw_part,
    map_lifecycle,
    map_rohs_compliance,
)
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller
from pcbpick.sourcing.types import CatalogHit, CatalogPart, SourcingQuery

BASE_URL = "https://api.digikey.com/products/v4"

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
    ("tape & reel", Packaging.REEL),
    ("tape and reel", Packaging.REEL),
    ("digi-reel", Packaging.REEL),
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
    """Keyword-matches DigiKey's stated `PackageType.Name`. `None` if DigiKey stated no
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


def _raw_part_from_digikey_json(product: dict[str, Any]) -> dict[str, Any]:
    price_breaks = sorted(
        (
            {
                "quantity": int(pb["BreakQuantity"]),
                "unit_price": str(pb["UnitPrice"]),
                "currency": pb.get("Currency", "USD"),
            }
            for pb in product.get("StandardPricing", [])
        ),
        key=lambda pb: pb["quantity"],
    )
    stock_raw = product.get("QuantityAvailable")
    moq_raw = product.get("MinimumOrderQuantity")
    spq_raw = product.get("StandardPackage")
    packaging = _map_packaging(product.get("PackageType", {}).get("Name"))

    return {
        "mpn": product["ManufacturerProductNumber"],
        "manufacturer": product.get("Manufacturer", {}).get("Name", ""),
        "category": _map_category(product.get("Category", {}).get("Name")).value,
        # DigiKey's parametric attributes are supplier-shaped key/value pairs, not our
        # (value, unit, tolerance) triples; passed through as no parameters here, same as
        # Mouser/Farnell — normalize owns turning supplier text into typed values.
        "parameters": {},
        "footprint": {"raw_text": product.get("PackageType", {}).get("Name")},
        "lifecycle": map_lifecycle(product.get("ProductStatus", {}).get("Status")).value,
        "compliance": [tag.value for tag in map_rohs_compliance(product.get("RohsStatus"))],
        "skus": [
            {
                "sku": product["DigiKeyProductNumber"],
                "packaging": packaging.value if packaging is not None else None,
                "stock": int(stock_raw) if stock_raw is not None else None,
                "moq": int(moq_raw) if moq_raw is not None else None,
                "spq": int(spq_raw) if spq_raw is not None else None,
                "price_breaks": price_breaks,
                "lead_time_days": _parse_lead_time_weeks_to_days(
                    product.get("ManufacturerLeadWeeks")
                ),
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
    if "Product" in data and data["Product"] is not None:
        return [data["Product"]]
    products = data.get("Products")
    return list(products) if products else []


class DigiKeyAdapter(LiveSupplierAdapter):
    """Live `SupplierAdapter` backed by the DigiKey Product Information API."""

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
            supplier_id=SupplierId.DIGIKEY,
            http_client=http_client,
            resilient_caller=resilient_caller
            or ResilientCaller(rate_limit=RateLimitConfig(max_calls=60, period_seconds=60)),
            snapshot_dir=snapshot_dir,
            now_fn=now_fn,
            run_id=run_id,
        )
        self._credentials = credentials

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._credentials.client_secret}",
            "X-DIGIKEY-Client-Id": self._credentials.api_key,
        }

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        keyword = (
            query.specified_mpn.mpn if query.specified_mpn is not None else query.category.value
        )
        request = self._http_client.build_request(
            "GET",
            f"{BASE_URL}/search/keyword",
            params={"keyword": keyword},
            headers=self._auth_headers(),
        )
        response = self._send(request, query=keyword)
        if response is None:
            return []
        raw_parts = [_raw_part_from_digikey_json(p) for p in _extract_products(response)]
        if raw_parts:
            self._write_snapshot(raw_parts)
        hits: list[CatalogHit] = []
        for raw_part in raw_parts:
            hits.extend(hits_for_raw_part(raw_part))
        return hits

    def details(self, mpn: str) -> CatalogPart | None:
        request = self._http_client.build_request(
            "GET", f"{BASE_URL}/search/{mpn}/productdetails", headers=self._auth_headers()
        )
        response = self._send(request, query=mpn)
        if response is None:
            return None
        products = _extract_products(response)
        if not products:
            return None
        raw_part = _raw_part_from_digikey_json(products[0])
        snapshot = self._write_snapshot([raw_part])
        return build_catalog_part(
            raw_part, snapshot_id=snapshot.snapshot_id, fetched_at=snapshot.fetched_at
        )

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del quantity  # DigiKey's product-details response always returns the full price ladder
        request = self._http_client.build_request(
            "GET", f"{BASE_URL}/search/{sku}/productdetails", headers=self._auth_headers()
        )
        response = self._send(request, query=sku)
        if response is None:
            return []
        offers: list[SupplierOffer] = []
        for product in _extract_products(response):
            raw_part = _raw_part_from_digikey_json(product)
            snapshot = self._write_snapshot([raw_part])
            for raw_sku in raw_part["skus"]:
                if raw_sku["sku"] != sku:
                    continue
                offer = build_offer(
                    raw_sku,
                    supplier=SupplierId.DIGIKEY,
                    snapshot_id=snapshot.snapshot_id,
                    fetched_at=snapshot.fetched_at,
                )
                if offer is not None:
                    offers.append(offer)
        return offers
