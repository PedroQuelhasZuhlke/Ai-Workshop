"""Contract + edge-case tests for `FarnellAdapter`. Every HTTP call goes through
`httpx.MockTransport` — no test ever reaches the real network.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from pcbpick.config.secrets import Credentials
from pcbpick.contracts.common import Footprint, MpnRef
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Lifecycle,
    SupplierId,
    ValueSource,
)
from pcbpick.sourcing.suppliers.farnell import FarnellAdapter
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller, RetryConfig
from pcbpick.sourcing.types import SourcingQuery

_CREDENTIALS = Credentials(supplier=SupplierId.FARNELL, api_key="farnell-test-key")


def _client_returning(json_body: dict[str, Any], status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _adapter(json_body: dict[str, Any], tmp_path: Path, status_code: int = 200) -> FarnellAdapter:
    return FarnellAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning(json_body, status_code),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )


def _farnell_product(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "translatedManufacturerPartNumber": "RC0603FR-0710KL",
        "brandName": "YAGEO",
        "category": "Resistors",
        "status": "Active",
        "rohsStatus": "Compliant",
        "translatedPackageName": "0603",
        "sku": "1462408",
        "stock": {"level": 8500},
        "translatedMinimumOrderQuantity": 1,
        "translatedOrderMultiple": 1,
        "leadStatus": "4 Weeks",
        "packOption": "Cut Tape",
        "prices": [
            {"from": 1, "cost": 0.012, "currency": "GBP"},
            {"from": 100, "cost": 0.009, "currency": "GBP"},
        ],
    }
    base.update(overrides)
    return base


def _response(*products: dict[str, Any]) -> dict[str, Any]:
    return {
        "premierFarnellPartNumberReturn": {
            "numberOfResults": len(products),
            "products": list(products),
        }
    }


def test_details_produces_fixture_equivalent_normalized_shape(tmp_path: Path) -> None:
    adapter = _adapter(_response(_farnell_product()), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.mpn == "RC0603FR-0710KL"
    assert part.manufacturer == "Yageo"
    assert part.lifecycle == Lifecycle.ACTIVE
    assert part.compliance == [ComplianceTag.ROHS]
    sku = part.skus[0]
    assert sku.sku == "1462408"
    assert sku.stock == 8500
    assert sku.moq == 1
    assert sku.spq == 1
    assert sku.lead_time_days == 28
    assert [pb.unit_price for pb in sku.price_breaks] == [Decimal("0.012"), Decimal("0.009")]
    assert part.snapshot_id.startswith("farnell-")
    assert part.fetched_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_missing_stock_is_none_not_zero(tmp_path: Path) -> None:
    product = _farnell_product(stock={})
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.skus[0].stock is None


def test_missing_pack_option_omits_sku_rather_than_fabricating_packaging(
    tmp_path: Path,
) -> None:
    product = _farnell_product()
    del product["packOption"]
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.skus == []
    assert adapter.offers("1462408", quantity=1) == []


def test_zero_stock_with_lead_time_is_preserved(tmp_path: Path) -> None:
    product = _farnell_product(stock={"level": 0}, leadStatus="12 Weeks")
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.skus[0].stock == 0
    assert part.skus[0].lead_time_days == 84


def test_foreign_currency_price_breaks_are_recorded_as_returned(tmp_path: Path) -> None:
    product = _farnell_product(prices=[{"from": 1, "cost": 0.0089, "currency": "EUR"}])
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert all(pb.currency == "EUR" for pb in part.skus[0].price_breaks)


def test_obsolete_lifecycle_is_mapped(tmp_path: Path) -> None:
    product = _farnell_product(status="Obsolete")
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.lifecycle == Lifecycle.OBSOLETE


def test_non_rohs_compliant_status_is_not_mapped_to_rohs(tmp_path: Path) -> None:
    product = _farnell_product(rohsStatus="Non-Compliant")
    adapter = _adapter(_response(product), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.compliance == []


def test_search_returns_hits_for_multiple_manufacturers_sharing_one_mpn(tmp_path: Path) -> None:
    littelfuse = _farnell_product(
        translatedManufacturerPartNumber="MPN-DUAL-SOURCE",
        brandName="Littelfuse Inc",
        sku="LF-DUAL-001",
    )
    bel_fuse = _farnell_product(
        translatedManufacturerPartNumber="MPN-DUAL-SOURCE",
        brandName="Bel Fuse Inc.",
        sku="BF-DUAL-001",
    )
    adapter = _adapter(_response(littelfuse, bel_fuse), tmp_path)

    hits = adapter.search(
        SourcingQuery(
            requirement_id="REQ-1",
            category=ComponentCategory.DIODE,
            parameters={},
            footprint=Footprint(package_code="SOD-123"),
            specified_mpn=MpnRef(mpn="MPN-DUAL-SOURCE", source=ValueSource.ENGINEER_ENTERED),
        )
    )

    assert {hit.manufacturer for hit in hits} == {"Littelfuse", "Bel Fuse"}
    assert {hit.sku for hit in hits} == {"LF-DUAL-001", "BF-DUAL-001"}


def test_offers_omits_offer_when_moq_or_spq_unknown(tmp_path: Path) -> None:
    product = _farnell_product(translatedMinimumOrderQuantity=None, translatedOrderMultiple=None)
    adapter = _adapter(_response(product), tmp_path)

    assert adapter.offers("1462408", quantity=100) == []


def test_offers_returns_empty_list_when_http_call_ultimately_fails(tmp_path: Path) -> None:
    fast_caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep_fn=lambda _seconds: None,
    )
    adapter = FarnellAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning({}, status_code=429),
        snapshot_dir=tmp_path,
        resilient_caller=fast_caller,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert adapter.offers("1462408", quantity=1) == []
    assert adapter.details("RC0603FR-0710KL") is None
