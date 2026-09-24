"""Stage tests for `source` (`SourceStage`): candidate assembly against the M4
golden catalog snapshot, dedup behavior for the near-duplicate-MPN and
multi-manufacturer-MPN cases, issue codes, and determinism, per
`.github/instructions/pipeline-stages.instructions.md` and
`fixtures/catalogs/README.md`.

## Judgment calls made here (see also `pcbpick.sourcing.assembly`'s module docstring)

- **Near-duplicate MPN** (`RC0603FR-0710KL` vs `RC0603FR-0710KLTR`): these are two
  *different* MPN strings. `assembly.dedup_candidate_pairs` dedups on an exact-string
  `mpn` match, never fuzzy/prefix matching, so these do **not** collapse — they
  survive as two distinct candidates. Collapsing them would require deciding that a
  `-TR` packaging-suffix MPN "is the same part" as its base part, which is a
  sourcing/procurement judgment call this pure function is not in a position to make
  silently.
- **Multi-manufacturer MPN** (`ABM3-16.000MHZ-D2Y-T`, Abracon vs ECS Inc):
  `FixtureAdapter.details()` can only return one manufacturer's `CatalogPart` for a
  shared MPN (first-loaded, Abracon here) — it has no way to disambiguate by
  manufacturer. `SourceStage` therefore only builds a candidate for the hit whose
  manufacturer matches what `details()` actually returned; the other manufacturer's
  hit is skipped with a `catalog_details_missing` issue rather than a candidate
  built from misattributed data (see `pcbpick.sourcing.stage`'s module docstring).
  This means only the Abracon candidate survives for `Y1` here — attributing ECS
  Inc's ±30ppm/obsolete-lifecycle hit to Abracon's ±10ppm/active `CatalogPart` data
  would be inventing a fact the adapter never actually stated for that part.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random

from pcbpick.contracts.common import Footprint, MpnRef, ParameterValue, PriceBreak
from pcbpick.contracts.enums import ComponentCategory, Lifecycle, Packaging, SupplierId, ValueSource
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.sourcing.stage import SourceStage
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.types import CatalogHit, CatalogPart, SourcingQuery

CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "catalogs" / "kicad_golden_snapshot.json"
)


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _adapter() -> FixtureAdapter:
    return FixtureAdapter([CATALOG_PATH])


def _resistor_10k_query(specified: bool) -> SourcingQuery:
    return SourcingQuery(
        requirement_id="REQ-R1",
        category=ComponentCategory.RESISTOR,
        parameters={
            "resistance": ParameterValue(
                value=Decimal("10000"), unit="ohm", raw_text="10.0k", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="RESC1608X55N"),
        specified_mpn=(
            MpnRef(mpn="RC0603FR-0710KL", manufacturer="Yageo", source=ValueSource.PARSED)
            if specified
            else None
        ),
    )


def _capacitor_100nf_query() -> SourcingQuery:
    return SourcingQuery(
        requirement_id="REQ-C1",
        category=ComponentCategory.CAPACITOR,
        parameters={
            "capacitance": ParameterValue(
                value=Decimal("1E-7"), unit="farad", raw_text="100n", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="CAPC1005X55N"),
        specified_mpn=None,
    )


def _crystal_query() -> SourcingQuery:
    return SourcingQuery(
        requirement_id="REQ-Y1",
        category=ComponentCategory.CRYSTAL,
        parameters={
            "frequency": ParameterValue(
                value=Decimal("16000000"), unit="hertz", raw_text="16MHz", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="XTAL3225-4N"),
        specified_mpn=MpnRef(
            mpn="ABM3-16.000MHZ-D2Y-T", manufacturer="Abracon", source=ValueSource.PARSED
        ),
    )


def test_exact_mpn_resistor_query_returns_single_candidate() -> None:
    result = SourceStage([_adapter()]).run([_resistor_10k_query(specified=True)], _make_ctx())

    assert [(c.mpn, c.manufacturer) for c in result.output] == [("RC0603FR-0710KL", "Yageo")]


def test_exact_mpn_resistor_query_candidate_carries_correctly_populated_offers() -> None:
    result = SourceStage([_adapter()]).run([_resistor_10k_query(specified=True)], _make_ctx())

    candidate = result.output[0]
    assert len(candidate.offers) == 1
    offer = candidate.offers[0]
    assert offer.supplier == SupplierId.FIXTURE
    assert offer.sku == "YAG-RC0603FR-0710KL"
    assert offer.stock == 850000
    assert offer.moq == 1
    assert offer.spq == 1
    assert [(pb.quantity, pb.unit_price) for pb in offer.price_breaks] == [
        (1, Decimal("0.0100")),
        (1000, Decimal("0.0038")),
    ]
    assert offer.snapshot_id == "fixture-kicad-golden-2026-01-15"


def test_parametric_resistor_query_does_not_collapse_near_duplicate_mpn() -> None:
    result = SourceStage([_adapter()]).run([_resistor_10k_query(specified=False)], _make_ctx())

    mpns = sorted(c.mpn for c in result.output)
    assert mpns == [
        "CRCW060310K0FKEA",
        "RC0603FR-0710KL",
        "RC0603FR-0710KLTR",
        "RC0805FR-0710KL",
    ]


def test_parametric_capacitor_query_returns_every_natural_collision() -> None:
    result = SourceStage([_adapter()]).run([_capacitor_100nf_query()], _make_ctx())

    mpns = sorted(c.mpn for c in result.output)
    assert mpns == [
        "0402YC104KAT2A",
        "C0402C104K4RACTU",
        "CL10B104KB8NNNC",
        "GRM155R71C104KA88D",
        "GRM188R71C104KA01D",
    ]


def test_crystal_query_yields_only_the_manufacturer_details_can_authoritatively_return() -> None:
    result = SourceStage([_adapter()]).run([_crystal_query()], _make_ctx())

    assert [(c.mpn, c.manufacturer) for c in result.output] == [("ABM3-16.000MHZ-D2Y-T", "Abracon")]
    mismatch_issues = [
        issue
        for issue in result.issues
        if issue.code == "catalog_details_missing" and issue.item_id == "REQ-Y1"
    ]
    assert len(mismatch_issues) == 1
    assert "ECS Inc" in mismatch_issues[0].message


@dataclass
class _EmptyAdapter:
    supplier_id: SupplierId = SupplierId.FIXTURE

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        del query
        return []

    def details(self, mpn: str) -> CatalogPart | None:
        del mpn
        return None

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del sku, quantity
        return []


@dataclass
class _MissingDetailsAdapter:
    supplier_id: SupplierId = SupplierId.FIXTURE
    hits: list[CatalogHit] = field(
        default_factory=lambda: [
            CatalogHit(mpn="GHOST-MPN", manufacturer="Nobody", sku="GHOST-SKU")
        ]
    )

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        del query
        return list(self.hits)

    def details(self, mpn: str) -> CatalogPart | None:
        del mpn
        return None

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del sku, quantity
        return []


def _dummy_query(requirement_id: str = "REQ-GHOST") -> SourcingQuery:
    return SourcingQuery(
        requirement_id=requirement_id,
        category=ComponentCategory.RESISTOR,
        parameters={},
        footprint=Footprint(package_code="RESC1608X55N"),
        specified_mpn=None,
    )


_DUP_PART = CatalogPart(
    mpn="DUP-MPN",
    manufacturer="Acme",
    category=ComponentCategory.RESISTOR,
    parameters={},
    footprint=Footprint(package_code="RESC1608X55N"),
    lifecycle=Lifecycle.ACTIVE,
    compliance=[],
    skus=[],
    snapshot_id="SNAP-DUP",
    fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def _dup_offer(sku: str, supplier: SupplierId, price: str) -> SupplierOffer:
    return SupplierOffer(
        supplier=supplier,
        sku=sku,
        packaging=Packaging.CUT_TAPE,
        stock=100,
        moq=1,
        spq=1,
        price_breaks=[PriceBreak(quantity=1, unit_price=Decimal(price), currency="USD")],
        lead_time_days=None,
        snapshot_id="SNAP-DUP",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@dataclass
class _TwoHitsSamePartAdapter:
    """Two search hits for the same (mpn, manufacturer) with different SKUs -- proves
    `dedup_candidate_pairs` unions their offers rather than keeping only one."""

    supplier_id: SupplierId = SupplierId.FIXTURE

    def search(self, query: SourcingQuery) -> list[CatalogHit]:
        del query
        return [
            CatalogHit(mpn="DUP-MPN", manufacturer="Acme", sku="SKU-B"),
            CatalogHit(mpn="DUP-MPN", manufacturer="Acme", sku="SKU-A"),
        ]

    def details(self, mpn: str) -> CatalogPart | None:
        del mpn
        return _DUP_PART

    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]:
        del quantity
        return [_dup_offer(sku, SupplierId.FIXTURE, "0.01")]


def test_two_hits_of_same_candidate_dedup_with_offers_unioned_and_sorted() -> None:
    result = SourceStage([_TwoHitsSamePartAdapter()]).run([_dummy_query("REQ-DUP")], _make_ctx())

    assert len(result.output) == 1
    candidate = result.output[0]
    assert [offer.sku for offer in candidate.offers] == ["SKU-A", "SKU-B"]
    assert [(offer.supplier.value, offer.sku) for offer in candidate.offers] == sorted(
        (offer.supplier.value, offer.sku) for offer in candidate.offers
    )


def test_no_candidates_found_issue_when_no_adapter_has_a_hit() -> None:
    result = SourceStage([_EmptyAdapter()]).run([_dummy_query()], _make_ctx())

    assert result.output == []
    assert any(
        issue.code == "no_candidates_found" and issue.item_id == "REQ-GHOST"
        for issue in result.issues
    )


def test_catalog_details_missing_issue_when_details_returns_none() -> None:
    result = SourceStage([_MissingDetailsAdapter()]).run([_dummy_query()], _make_ctx())

    assert result.output == []
    assert any(
        issue.code == "catalog_details_missing" and issue.item_id == "REQ-GHOST"
        for issue in result.issues
    )
    # zero candidates after details-missing also fires no_candidates_found
    assert any(issue.code == "no_candidates_found" for issue in result.issues)


def test_output_sorted_by_requirement_id_then_mpn() -> None:
    result = SourceStage([_adapter()]).run(
        [_crystal_query(), _resistor_10k_query(specified=True)], _make_ctx()
    )

    keys = [(c.requirement_id, c.mpn) for c in result.output]
    assert keys == sorted(keys)


def test_source_stage_is_deterministic_across_runs() -> None:
    queries = [
        _resistor_10k_query(specified=False),
        _capacitor_100nf_query(),
        _crystal_query(),
    ]
    ctx = _make_ctx()

    first = SourceStage([_adapter()]).run(queries, ctx)
    second = SourceStage([_adapter()]).run(queries, ctx)

    assert [c.model_dump_json() for c in first.output] == [
        c.model_dump_json() for c in second.output
    ]
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]
