"""Contract + edge-case tests for `DigiKeyAdapter`. Every HTTP call goes through
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
from pcbpick.sourcing.suppliers.digikey import DigiKeyAdapter
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller, RetryConfig
from pcbpick.sourcing.types import SourcingQuery

_CREDENTIALS = Credentials(
    supplier=SupplierId.DIGIKEY, api_key="digikey-client-id", client_secret="digikey-client-secret"
)


def _client_returning(json_body: dict[str, Any], status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _adapter(json_body: dict[str, Any], tmp_path: Path, status_code: int = 200) -> DigiKeyAdapter:
    return DigiKeyAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning(json_body, status_code),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )


def _digikey_product(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ManufacturerProductNumber": "GRM188R71H104KA93D",
        "Manufacturer": {"Name": "MURATA MANUFACTURING"},
        "Category": {"Name": "Capacitors"},
        "ProductStatus": {"Status": "Active"},
        "RohsStatus": "RoHS Compliant",
        "PackageType": {"Name": "Tape & Reel (TR)"},
        "DigiKeyProductNumber": "490-1234-1-ND",
        "QuantityAvailable": 20000,
        "MinimumOrderQuantity": 1,
        "StandardPackage": 1,
        "ManufacturerLeadWeeks": "6 Weeks",
        "StandardPricing": [
            {"BreakQuantity": 1, "UnitPrice": 0.0089, "Currency": "USD"},
            {"BreakQuantity": 1000, "UnitPrice": 0.0065, "Currency": "USD"},
        ],
    }
    base.update(overrides)
    return base


def test_details_produces_fixture_equivalent_normalized_shape(tmp_path: Path) -> None:
    adapter = _adapter({"Product": _digikey_product()}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.mpn == "GRM188R71H104KA93D"
    assert part.manufacturer == "Murata"
    assert part.lifecycle == Lifecycle.ACTIVE
    assert part.compliance == [ComplianceTag.ROHS]
    sku = part.skus[0]
    assert sku.sku == "490-1234-1-ND"
    assert sku.stock == 20000
    assert sku.moq == 1
    assert sku.spq == 1
    assert sku.lead_time_days == 42  # 6 weeks * 7
    assert [pb.unit_price for pb in sku.price_breaks] == [Decimal("0.0089"), Decimal("0.0065")]
    assert part.snapshot_id.startswith("digikey-")
    assert part.fetched_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_missing_stock_is_none_not_zero(tmp_path: Path) -> None:
    product = _digikey_product()
    del product["QuantityAvailable"]
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.skus[0].stock is None


def test_missing_package_type_omits_sku_rather_than_fabricating_packaging(
    tmp_path: Path,
) -> None:
    product = _digikey_product()
    del product["PackageType"]
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.skus == []
    assert adapter.offers("490-1234-1-ND", quantity=1) == []


def test_zero_stock_with_lead_time_is_preserved(tmp_path: Path) -> None:
    product = _digikey_product(QuantityAvailable=0, ManufacturerLeadWeeks="13 Weeks")
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.skus[0].stock == 0
    assert part.skus[0].lead_time_days == 91


def test_foreign_currency_price_breaks_are_recorded_as_returned(tmp_path: Path) -> None:
    product = _digikey_product(
        StandardPricing=[{"BreakQuantity": 1, "UnitPrice": 0.0075, "Currency": "GBP"}]
    )
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert all(pb.currency == "GBP" for pb in part.skus[0].price_breaks)


def test_obsolete_lifecycle_is_mapped(tmp_path: Path) -> None:
    product = _digikey_product(ProductStatus={"Status": "Discontinued"})
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.lifecycle == Lifecycle.OBSOLETE


def test_non_rohs_compliant_status_is_not_mapped_to_rohs(tmp_path: Path) -> None:
    product = _digikey_product(RohsStatus="Non-RoHS Compliant")
    adapter = _adapter({"Product": product}, tmp_path)

    part = adapter.details("GRM188R71H104KA93D")

    assert part is not None
    assert part.compliance == []


def test_search_returns_hits_for_multiple_manufacturers_sharing_one_mpn(tmp_path: Path) -> None:
    littelfuse = _digikey_product(
        ManufacturerProductNumber="MPN-DUAL-SOURCE",
        Manufacturer={"Name": "Littelfuse Inc"},
        DigiKeyProductNumber="LF-DUAL-001-ND",
    )
    bel_fuse = _digikey_product(
        ManufacturerProductNumber="MPN-DUAL-SOURCE",
        Manufacturer={"Name": "Bel Fuse Inc."},
        DigiKeyProductNumber="BF-DUAL-001-ND",
    )
    adapter = _adapter({"Products": [littelfuse, bel_fuse]}, tmp_path)

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
    assert {hit.sku for hit in hits} == {"LF-DUAL-001-ND", "BF-DUAL-001-ND"}


def test_offers_omits_offer_when_moq_or_spq_unknown(tmp_path: Path) -> None:
    product = _digikey_product(MinimumOrderQuantity=None, StandardPackage=None)
    adapter = _adapter({"Product": product}, tmp_path)

    assert adapter.offers("490-1234-1-ND", quantity=100) == []


def test_offers_returns_empty_list_when_http_call_ultimately_fails(tmp_path: Path) -> None:
    fast_caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep_fn=lambda _seconds: None,
    )
    adapter = DigiKeyAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning({}, status_code=503),
        snapshot_dir=tmp_path,
        resilient_caller=fast_caller,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert adapter.offers("490-1234-1-ND", quantity=1) == []
    assert adapter.details("GRM188R71H104KA93D") is None
