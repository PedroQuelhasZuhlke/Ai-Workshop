"""Live `SupplierAdapter` for Mouser Electronics.

Mouser's real search API authenticates via an `apiKey` query-string parameter; this
adapter deliberately sends the key as an `Authorization: Bearer` header instead, so a
credential can never end up in a logged request URL — nothing to redact from a URL
that never carried the secret to begin with. Translating to Mouser's real
query-string form, if ever required, belongs at the transport layer, not here.

Mouser's JSON gives per-part pricing/stock/MOQ/SPQ but no packaging-variant field, so
every part maps to exactly one candidate `CatalogSku` keyed by `MouserPartNumber` —
but with no real signal to say whether it's cut tape, reel, tube, or bulk, and
`Packaging` has no "unspecified" member, that sku's `packaging` is left `None` and
`live_base.build_catalog_part`/`build_offer` drop it rather than validate a guessed
enum value. `search()` still surfaces the part via `CatalogHit` (which carries no
packaging field), but `details()`/`offers()` cannot expose a purchasable line for it
until `Packaging` gets an "unspecified" member — a contract change flagged for the
contracts owner, not worked around here.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from pcbpick.config.secrets import Credentials
from pcbpick.contracts.enums import ComponentCategory, SupplierId
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

BASE_URL = "https://api.mouser.com/api/v1"

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


def _map_category(raw: str | None) -> ComponentCategory:
    if raw is None:
        return ComponentCategory.UNKNOWN
    lowered = raw.casefold()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in lowered:
            return category
    return ComponentCategory.UNKNOWN


def _price_str(raw_price: str) -> str | None:
    """Mouser quotes prices like `"$0.0123"`; strips only the currency symbol, never
    rounds. `None` if the string doesn't parse as a `Decimal` at all (e.g. `"Call for
    Price"`) -- never `"0"`, which would fabricate a free part that could win a
    lowest-cost comparison outright.
    """
    stripped = raw_price.strip().lstrip("$")
    try:
        Decimal(stripped)
    except InvalidOperation:
        return None
    return stripped


def _parse_lead_time_days(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def _raw_part_from_mouser_json(part: dict[str, Any]) -> dict[str, Any]:
    price_breaks = sorted(
        (
            {
                "quantity": int(pb["Quantity"]),
                "unit_price": price_str,
                "currency": pb.get("Currency", "USD"),
            }
            for pb in part.get("PriceBreaks", [])
            if (price_str := _price_str(pb["Price"])) is not None
        ),
        key=lambda pb: pb["quantity"],
    )
    stock_raw = part.get("AvailabilityInStock")
    moq_raw = part.get("Min")
    spq_raw = part.get("Mult")

    return {
        "mpn": part["ManufacturerPartNumber"],
        "manufacturer": part.get("Manufacturer", ""),
        "category": _map_category(part.get("Category")).value,
        # Mouser's attributes are description-shaped, not (name, value, unit) triples;
        # parsing them here would be inferring parameters from text — normalize's job.
        "parameters": {},
        "footprint": {"raw_text": part.get("Case") or part.get("Package")},
        "lifecycle": map_lifecycle(part.get("LifecycleStatus")).value,
        "compliance": [tag.value for tag in map_rohs_compliance(part.get("ROHSStatus"))],
        "skus": [
            {
                "sku": part["MouserPartNumber"],
                # No packaging field exists in Mouser's response at all (unlike
                # DigiKey/Farnell, which at least state a package-type string to
                # keyword-match) -- `None` here, never a guessed `Packaging` member.
                "packaging": None,
                "stock": int(stock_raw) if stock_raw not in (None, "") else None,
                "moq": int(moq_raw) if moq_raw not in (None, "") else None,
                "spq": int(spq_raw) if spq_raw not in (None, "") else None,
                "price_breaks": price_breaks,
                "lead_time_days": _parse_lead_time_days(part.get("LeadTime")),
            }
        ],
    }


def _extract_parts(response: httpx.Response) -> list[dict[str, Any]]:
    try:
        data = response.json()
    except ValueError:
        return []
    parts = data.get("SearchResults", {}).get("Parts")
    return list(parts) if parts else []


class MouserAdapter(LiveSupplierAdapter):
    """Live `SupplierAdapter` backed by the Mouser Electronics search API."""

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
            supplier_id=SupplierId.MOUSER,
            http_client=http_client,
            resilient_caller=resilient_caller
            or ResilientCaller(rate_limit=RateLimitConfig(max_calls=30, period_seconds=60)),
            snapshot_dir=snapshot_dir,
            now_fn=now_fn,
            run_id=run_id,
        )
        self._credentials = credentials

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        keyword = (
            query.specified_mpn.mpn if query.specified_mpn is not None else query.category.value
        )
        body = json.dumps({"SearchByKeywordRequest": {"keyword": keyword, "records": 50}}).encode()
        request = self._http_client.build_request(
            "POST",
            f"{BASE_URL}/search/keyword",
            headers=bearer_header(self._credentials.api_key),
            content=body,
        )
        response = self._send(request, query=keyword)
        if response is None:
            return []
        raw_parts = [_raw_part_from_mouser_json(p) for p in _extract_parts(response)]
        if raw_parts:
            self._write_snapshot(raw_parts)
        hits: list[CatalogHit] = []
        for raw_part in raw_parts:
            hits.extend(hits_for_raw_part(raw_part))
        return hits

    def details(self, mpn: str) -> CatalogPart | None:
        request = self._http_client.build_request(
            "GET",
            f"{BASE_URL}/search/partnumber/{mpn}",
            headers=bearer_header(self._credentials.api_key),
        )
        response = self._send(request, query=mpn)
        if response is None:
            return None
        raw_json_parts = _extract_parts(response)
        if not raw_json_parts:
            return None
        raw_part = _raw_part_from_mouser_json(raw_json_parts[0])
        snapshot = self._write_snapshot([raw_part])
        return build_catalog_part(
            raw_part, snapshot_id=snapshot.snapshot_id, fetched_at=snapshot.fetched_at
        )

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del quantity  # Mouser's per-part response always returns the full price-break ladder
        request = self._http_client.build_request(
            "GET",
            f"{BASE_URL}/search/partnumber/{sku}",
            headers=bearer_header(self._credentials.api_key),
        )
        response = self._send(request, query=sku)
        if response is None:
            return []
        offers: list[SupplierOffer] = []
        for raw_json_part in _extract_parts(response):
            raw_part = _raw_part_from_mouser_json(raw_json_part)
            snapshot = self._write_snapshot([raw_part])
            for raw_sku in raw_part["skus"]:
                if raw_sku["sku"] != sku:
                    continue
                offer = build_offer(
                    raw_sku,
                    supplier=SupplierId.MOUSER,
                    snapshot_id=snapshot.snapshot_id,
                    fetched_at=snapshot.fetched_at,
                )
                if offer is not None:
                    offers.append(offer)
        return offers
