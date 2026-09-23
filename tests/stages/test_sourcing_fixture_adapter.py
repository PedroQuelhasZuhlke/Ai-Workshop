"""Tests for `pcbpick.sourcing.suppliers.fixture.FixtureAdapter`, per
`.github/instructions/testing.instructions.md` and
`.github/instructions/supplier-adapters.instructions.md`.

No live network calls anywhere: every test loads
`fixtures/catalogs/_adapter_contract_test.json` from disk.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pcbpick.contracts.common import Footprint, MpnRef, ParameterValue
from pcbpick.contracts.enums import ComponentCategory, Lifecycle, MountingType, ValueSource
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.types import SourcingQuery

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "catalogs" / ("_adapter_contract_test.json")
)


def _adapter() -> FixtureAdapter:
    return FixtureAdapter([FIXTURE_PATH])


def _resistor_query(mpn: MpnRef | None = None, resistance: str | None = None) -> SourcingQuery:
    parameters: dict[str, ParameterValue] = {}
    if resistance is not None:
        parameters["resistance"] = ParameterValue(
            value=Decimal(resistance),
            unit="ohm",
            raw_text=resistance,
            source=ValueSource.PARSED,
        )
    return SourcingQuery(
        requirement_id="REQ-1",
        category=ComponentCategory.RESISTOR,
        parameters=parameters,
        footprint=Footprint(package_code="0603", mounting=MountingType.SMT),
        specified_mpn=mpn,
    )


def test_loads_snapshot_and_indexes_every_part() -> None:
    adapter = _adapter()
    assert adapter.supplier_id.value == "fixture"
    # every part's mpn should be resolvable via details()
    for mpn in [
        "RC0603FR-0710KL",
        "RC0603FR-0710K1",
        "GRM188R71H104KA93D",
        "MPN-NRND-001",
        "MPN-OBSOLETE-001",
        "MPN-DUAL-SOURCE",
        "RC0805FR-0710KL",
    ]:
        assert adapter.details(mpn) is not None


def test_search_by_specified_mpn_matches_exactly() -> None:
    adapter = _adapter()
    mpn_ref = MpnRef(mpn="RC0603FR-0710KL", source=ValueSource.ENGINEER_ENTERED)
    hits = adapter.search(_resistor_query(mpn=mpn_ref))

    assert len(hits) == 1
    assert hits[0].mpn == "RC0603FR-0710KL"
    assert hits[0].manufacturer == "Yageo"
    assert hits[0].sku == "YAG-10K-0603-CT"


def test_search_by_category_and_primary_parameter() -> None:
    adapter = _adapter()
    hits = adapter.search(_resistor_query(resistance="10000"))

    # two distinct 10k resistor parts (0603 and 0805) share resistance=10000
    skus = {hit.sku for hit in hits}
    assert skus == {"YAG-10K-0603-CT", "YAG-10K-0805"}
    # the 4k7 part must not match
    assert "YAG-4K7-0603-NOMOQ" not in skus


def test_search_returns_multiple_hits_for_multi_manufacturer_mpn() -> None:
    adapter = _adapter()
    mpn_ref = MpnRef(mpn="MPN-DUAL-SOURCE", source=ValueSource.ENGINEER_ENTERED)
    query = SourcingQuery(
        requirement_id="REQ-2",
        category=ComponentCategory.DIODE,
        parameters={},
        footprint=Footprint(package_code="SOD-123", mounting=MountingType.SMT),
        specified_mpn=mpn_ref,
    )
    hits = adapter.search(query)

    assert {hit.manufacturer for hit in hits} == {"Littelfuse", "Bel Fuse"}
    assert {hit.sku for hit in hits} == {"LF-DUAL-001", "BF-DUAL-001"}


def test_details_returns_first_manufacturer_in_file_order_for_shared_mpn() -> None:
    adapter = _adapter()
    part = adapter.details("MPN-DUAL-SOURCE")

    assert part is not None
    # Littelfuse's entry appears first in the snapshot file's "parts" array.
    assert part.manufacturer == "Littelfuse"


def test_details_returns_none_for_unknown_mpn() -> None:
    adapter = _adapter()
    assert adapter.details("NOT-A-REAL-MPN") is None


def test_details_preserves_none_for_missing_moq_and_spq() -> None:
    adapter = _adapter()
    part = adapter.details("RC0603FR-0710K1")

    assert part is not None
    sku = part.skus[0]
    assert sku.sku == "YAG-4K7-0603-NOMOQ"
    assert sku.moq is None
    assert sku.spq is None
    assert sku.stock == 500


def test_offers_omits_offer_when_moq_or_spq_unknown() -> None:
    adapter = _adapter()
    # See fixture.py's module docstring: SupplierOffer.moq/.spq are required ints today,
    # so an offer that can't state them is omitted rather than fabricated.
    assert adapter.offers("YAG-4K7-0603-NOMOQ", quantity=100) == []


def test_offers_returns_empty_list_for_unknown_sku() -> None:
    adapter = _adapter()
    assert adapter.offers("NOT-A-REAL-SKU", quantity=1) == []


def test_offers_preserves_zero_stock_and_lead_time() -> None:
    adapter = _adapter()
    offers = adapter.offers("YAG-10K-0603-CT", quantity=1000)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.stock == 0
    assert offer.lead_time_days == 45
    assert offer.moq == 1
    assert offer.spq == 1000
    assert offer.snapshot_id == "snap-adapter-contract-test-001"
    assert offer.fetched_at == datetime(2026, 1, 15, tzinfo=UTC)


def test_offers_ignores_requested_quantity_and_returns_full_ladder() -> None:
    adapter = _adapter()
    offers_small = adapter.offers("YAG-10K-0603-CT", quantity=1)
    offers_large = adapter.offers("YAG-10K-0603-CT", quantity=999999)

    assert offers_small == offers_large
    assert len(offers_small[0].price_breaks) == 2


def test_offers_preserves_non_usd_currency() -> None:
    adapter = _adapter()
    offers = adapter.offers("MUR-100N-0603-EUR", quantity=1)

    assert len(offers) == 1
    for price_break in offers[0].price_breaks:
        assert price_break.currency == "EUR"
    assert offers[0].price_breaks[0].unit_price == Decimal("0.0089")


def test_nrnd_and_obsolete_lifecycle_preserved() -> None:
    adapter = _adapter()
    nrnd_part = adapter.details("MPN-NRND-001")
    obsolete_part = adapter.details("MPN-OBSOLETE-001")

    assert nrnd_part is not None and nrnd_part.lifecycle == Lifecycle.NRND
    assert obsolete_part is not None and obsolete_part.lifecycle == Lifecycle.OBSOLETE


def test_stock_none_preserved_when_supplier_does_not_state_it() -> None:
    adapter = _adapter()
    part = adapter.details("MPN-OBSOLETE-001")

    assert part is not None
    assert part.skus[0].stock is None


def test_manufacturer_names_normalized_on_load() -> None:
    adapter = _adapter()
    murata_part = adapter.details("GRM188R71H104KA93D")
    vishay_part = adapter.details("MPN-OBSOLETE-001")

    assert murata_part is not None and murata_part.manufacturer == "Murata"
    assert vishay_part is not None and vishay_part.manufacturer == "Vishay"
    assert normalize_manufacturer("MURATA MANUFACTURING") == "Murata"


def test_footprint_data_round_trips_even_when_mismatched() -> None:
    adapter = _adapter()
    # Same electrical resistor as RC0603FR-0710KL, but in an 0805 footprint. The adapter
    # is not responsible for rejecting this — policy is — only for faithful round-trip.
    part = adapter.details("RC0805FR-0710KL")

    assert part is not None
    assert part.footprint.package_code == "0805"
    assert part.parameters["resistance"].value == Decimal("10000")


def test_from_directory_loads_same_data_as_explicit_path_list() -> None:
    by_path = FixtureAdapter([FIXTURE_PATH])
    by_dir = FixtureAdapter.from_directory(
        FIXTURE_PATH.parent, pattern="_adapter_contract_test.json"
    )

    assert by_path.details("RC0603FR-0710KL") == by_dir.details("RC0603FR-0710KL")


def test_determinism_same_snapshot_twice_same_query_byte_identical() -> None:
    adapter_a = _adapter()
    adapter_b = _adapter()
    query = _resistor_query(resistance="10000")

    hits_a = adapter_a.search(query)
    hits_b = adapter_b.search(query)
    assert hits_a == hits_b

    details_a = adapter_a.details("RC0603FR-0710KL")
    details_b = adapter_b.details("RC0603FR-0710KL")
    assert details_a == details_b
    assert details_a.model_dump_json() == details_b.model_dump_json()

    offers_a = adapter_a.offers("YAG-10K-0603-CT", quantity=5)
    offers_b = adapter_b.offers("YAG-10K-0603-CT", quantity=5)
    assert offers_a == offers_b
