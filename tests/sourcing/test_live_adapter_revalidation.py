"""Tests for `LiveSupplierAdapter.revalidate_if_stale`, the pre-export re-validation
entry point (task item 5). Uses `FarnellAdapter` as the representative live adapter
(it states a real packaging field, unlike Mouser's response shape — see
`mouser.py`'s module docstring for that gap); the method itself lives on the shared
base class.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx

from pcbpick.config.secrets import Credentials
from pcbpick.contracts.common import PriceBreak
from pcbpick.contracts.enums import Packaging, SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.sourcing.suppliers.farnell import FarnellAdapter

_CREDENTIALS = Credentials(supplier=SupplierId.FARNELL, api_key="farnell-test-key")

_FRESH_RESPONSE = {
    "premierFarnellPartNumberReturn": {
        "numberOfResults": 1,
        "products": [
            {
                "translatedManufacturerPartNumber": "RC0603FR-0710KL",
                "brandName": "Yageo",
                "sku": "1462408",
                "translatedMinimumOrderQuantity": 1,
                "translatedOrderMultiple": 1000,
                "stock": {"level": 999},
                "packOption": "Cut Tape",
                "prices": [{"from": 1, "cost": 0.02, "currency": "GBP"}],
            }
        ],
    }
}


def _stale_offer(fetched_at: datetime) -> SupplierOffer:
    return SupplierOffer(
        supplier=SupplierId.FARNELL,
        sku="1462408",
        packaging=Packaging.CUT_TAPE,
        stock=100,
        moq=1,
        spq=1000,
        price_breaks=[PriceBreak(quantity=1, unit_price=Decimal("0.031"), currency="GBP")],
        lead_time_days=None,
        snapshot_id="old-snapshot",
        fetched_at=fetched_at,
    )


def _adapter_for_revalidation(tmp_path: Path, now: datetime) -> FarnellAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_FRESH_RESPONSE, request=request)

    return FarnellAdapter(
        credentials=_CREDENTIALS,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        snapshot_dir=tmp_path,
        now_fn=lambda: now,
    )


def test_revalidate_if_stale_returns_original_offer_when_still_fresh(tmp_path: Path) -> None:
    now = datetime(2026, 3, 1, tzinfo=UTC)
    adapter = _adapter_for_revalidation(tmp_path, now)
    offer = _stale_offer(fetched_at=now - timedelta(days=1))

    result = adapter.revalidate_if_stale(
        offer, quantity=100, now=now, max_age=timedelta(days=90)
    )

    assert result == offer  # unchanged: not stale, so no re-fetch happened


def test_revalidate_if_stale_refetches_when_past_max_age(tmp_path: Path) -> None:
    now = datetime(2026, 3, 1, tzinfo=UTC)
    adapter = _adapter_for_revalidation(tmp_path, now)
    offer = _stale_offer(fetched_at=now - timedelta(days=91))

    result = adapter.revalidate_if_stale(
        offer, quantity=100, now=now, max_age=timedelta(days=90)
    )

    assert result is not None
    assert result.snapshot_id != "old-snapshot"  # a real, freshly written snapshot
    assert result.fetched_at == now
    assert result.stock == 999  # the re-fetched value, not the stale one


def test_revalidate_if_stale_returns_none_when_refetch_finds_nothing(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"premierFarnellPartNumberReturn": {"numberOfResults": 0, "products": []}},
            request=request,
        )

    now = datetime(2026, 3, 1, tzinfo=UTC)
    adapter = FarnellAdapter(
        credentials=_CREDENTIALS,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        snapshot_dir=tmp_path,
        now_fn=lambda: now,
    )
    offer = _stale_offer(fetched_at=now - timedelta(days=91))

    result = adapter.revalidate_if_stale(
        offer, quantity=100, now=now, max_age=timedelta(days=90)
    )

    assert result is None

