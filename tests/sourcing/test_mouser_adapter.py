"""Contract + edge-case tests for `MouserAdapter`, per
`.github/instructions/supplier-adapters.instructions.md` and
`.github/instructions/testing.instructions.md`. Every HTTP call goes through
`httpx.MockTransport` — no test ever reaches the real network.

Mouser's response never states a packaging field at all (unlike DigiKey/Farnell,
which at least state a package-type string to keyword-match), so every sku's
`packaging` is `None` and `details()`/`offers()` honestly omit the sku/offer rather
than validate a guessed `Packaging` member (see `mouser.py`'s module docstring for
the full contract-gap explanation). The stock/moq/spq/price-break/lead-time field
mappings are still real behavior worth covering, so those are exercised directly
against the private `_raw_part_from_mouser_json` mapping function rather than through
`details()`/`offers()`, which cannot expose a sku for any Mouser part until
`Packaging` gets an "unspecified" member.
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
from pcbpick.sourcing.suppliers.mouser import MouserAdapter, _raw_part_from_mouser_json
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller, RetryConfig
from pcbpick.sourcing.types import SourcingQuery

_CREDENTIALS = Credentials(supplier=SupplierId.MOUSER, api_key="mouser-test-key")


def _client_returning(json_body: dict[str, Any], status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _adapter(json_body: dict[str, Any], tmp_path: Path, status_code: int = 200) -> MouserAdapter:
    return MouserAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning(json_body, status_code),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )


def _mouser_part(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ManufacturerPartNumber": "RC0603FR-0710KL",
        "Manufacturer": "YAGEO",
        "Category": "Resistors",
        "LifecycleStatus": "Active",
        "ROHSStatus": "RoHS Compliant",
        "Case": "0603",
        "MouserPartNumber": "603-RC0603FR-0710KL",
        "AvailabilityInStock": "12000",
        "Min": "1",
        "Mult": "1000",
        "LeadTime": "45 Days",
        "PriceBreaks": [
            {"Quantity": 1000, "Price": "$0.0031", "Currency": "USD"},
            {"Quantity": 10000, "Price": "$0.0022", "Currency": "USD"},
        ],
    }
    base.update(overrides)
    return base


def _search_response(*parts: dict[str, Any]) -> dict[str, Any]:
    return {"SearchResults": {"Parts": list(parts)}}


def test_details_produces_fixture_equivalent_normalized_shape(tmp_path: Path) -> None:
    adapter = _adapter(_search_response(_mouser_part()), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.mpn == "RC0603FR-0710KL"
    assert part.manufacturer == "Yageo"  # normalized via normalize_manufacturer
    assert part.lifecycle == Lifecycle.ACTIVE
    assert part.compliance == [ComplianceTag.ROHS]
    # No packaging signal in Mouser's response -> no sku can be honestly validated.
    assert part.skus == []
    assert part.snapshot_id.startswith("mouser-")
    assert part.fetched_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_details_returns_none_for_empty_search_results(tmp_path: Path) -> None:
    adapter = _adapter(_search_response(), tmp_path)

    assert adapter.details("NOT-A-REAL-MPN") is None


def test_raw_mapping_reports_missing_stock_as_none_not_zero() -> None:
    part_json = _mouser_part()
    del part_json["AvailabilityInStock"]

    raw = _raw_part_from_mouser_json(part_json)

    assert raw["skus"][0]["stock"] is None


def test_raw_mapping_preserves_zero_stock_with_lead_time() -> None:
    part_json = _mouser_part(AvailabilityInStock="0", LeadTime="90 Days")

    raw = _raw_part_from_mouser_json(part_json)

    assert raw["skus"][0]["stock"] == 0
    assert raw["skus"][0]["lead_time_days"] == 90


def test_raw_mapping_records_foreign_currency_price_breaks_as_returned() -> None:
    part_json = _mouser_part(
        PriceBreaks=[{"Quantity": 1, "Price": "$0.0089", "Currency": "EUR"}]
    )

    raw = _raw_part_from_mouser_json(part_json)

    assert all(pb["currency"] == "EUR" for pb in raw["skus"][0]["price_breaks"])


def test_raw_mapping_parses_moq_spq_and_ascending_price_breaks() -> None:
    raw = _raw_part_from_mouser_json(_mouser_part())

    sku = raw["skus"][0]
    assert sku["sku"] == "603-RC0603FR-0710KL"
    assert sku["moq"] == 1
    assert sku["spq"] == 1000
    assert [pb["unit_price"] for pb in sku["price_breaks"]] == ["0.0031", "0.0022"]
    quantities = [pb["quantity"] for pb in sku["price_breaks"]]
    assert quantities == sorted(quantities)
    assert all(Decimal(pb["unit_price"]) > 0 for pb in sku["price_breaks"])


def test_raw_mapping_drops_unparseable_price_rather_than_fabricating_zero() -> None:
    part_json = _mouser_part(
        PriceBreaks=[
            {"Quantity": 1, "Price": "Call for Price", "Currency": "USD"},
            {"Quantity": 1000, "Price": "$0.0022", "Currency": "USD"},
        ]
    )

    raw = _raw_part_from_mouser_json(part_json)

    assert [pb["unit_price"] for pb in raw["skus"][0]["price_breaks"]] == ["0.0022"]


def test_obsolete_lifecycle_is_mapped(tmp_path: Path) -> None:
    part_json = _mouser_part(LifecycleStatus="Obsolete")
    adapter = _adapter(_search_response(part_json), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.lifecycle == Lifecycle.OBSOLETE


def test_non_rohs_compliant_status_is_not_mapped_to_rohs(tmp_path: Path) -> None:
    part_json = _mouser_part(ROHSStatus="Non-RoHS Compliant")
    adapter = _adapter(_search_response(part_json), tmp_path)

    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.compliance == []


def test_search_returns_hits_for_multiple_manufacturers_sharing_one_mpn(tmp_path: Path) -> None:
    littelfuse = _mouser_part(
        ManufacturerPartNumber="MPN-DUAL-SOURCE",
        Manufacturer="Littelfuse Inc",
        MouserPartNumber="LF-DUAL-001",
    )
    bel_fuse = _mouser_part(
        ManufacturerPartNumber="MPN-DUAL-SOURCE",
        Manufacturer="Bel Fuse Inc.",
        MouserPartNumber="BF-DUAL-001",
    )
    adapter = _adapter(_search_response(littelfuse, bel_fuse), tmp_path)

    hits = adapter.search(
        SourcingQuery(
            requirement_id="REQ-1",
            category=ComponentCategory.DIODE,
            parameters={},
            footprint=Footprint(package_code="SOD-123"),
            specified_mpn=MpnRef(mpn="MPN-DUAL-SOURCE", source=ValueSource.ENGINEER_ENTERED),
        )
    )

    # search() still finds both, since `CatalogHit` carries no packaging field.
    assert {hit.manufacturer for hit in hits} == {"Littelfuse", "Bel Fuse"}
    assert {hit.sku for hit in hits} == {"LF-DUAL-001", "BF-DUAL-001"}


def test_offers_omits_offer_when_packaging_is_unknown(tmp_path: Path) -> None:
    adapter = _adapter(_search_response(_mouser_part()), tmp_path)

    assert adapter.offers("603-RC0603FR-0710KL", quantity=100) == []


def test_offers_returns_empty_list_when_http_call_ultimately_fails(tmp_path: Path) -> None:
    # A fast, no-real-sleep resilient caller: proves the adapter degrades to an empty
    # result rather than hanging or raising, without the test itself waiting on backoff.
    fast_caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep_fn=lambda _seconds: None,
    )
    adapter = MouserAdapter(
        credentials=_CREDENTIALS,
        http_client=_client_returning({}, status_code=500),
        snapshot_dir=tmp_path,
        resilient_caller=fast_caller,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert adapter.offers("603-RC0603FR-0710KL", quantity=1) == []
    assert adapter.details("RC0603FR-0710KL") is None

