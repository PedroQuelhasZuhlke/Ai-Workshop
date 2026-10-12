"""The mock-supplier demo BOM, end to end: normalize -> source -> policy -> plan.

Asserts structural properties that follow from reading the mock catalogs (which supplier
alone carries a part, which offer is zero-stock or in EUR) and from what each decision
mode is defined to optimize -- not totals taken from a run. Offline, fixed clock.
"""

from datetime import UTC, datetime
from pathlib import Path
from random import Random

import pytest

from pcbpick.api import orchestrator
from pcbpick.api.settings import DEFAULT_MOCK_SUPPLIER_SNAPSHOTS
from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.enums import DecisionMode, SupplierId
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.normalize.stage import NormalizeStage
from pcbpick.pipeline.context import PipelineConfig, StageContext

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BOM = _REPO_ROOT / "demo" / "boms" / "mock_suppliers_demo.csv"
_FARNELL_ONLY_SKU = "MOCK-FAR-CRCW0603100RFKEA"
_ZERO_STOCK_SKU = "MOCK-MOU-ERJ-3EKF1001V"
_EUR_SKU = "MOCK-FAR-CL10B104KB8NNNC"


@pytest.fixture(scope="module")
def run() -> tuple[list[PartCandidate], dict[DecisionMode, PurchasePlan], list[str]]:
    ctx = StageContext(
        run_id="mock-demo",
        now=datetime(2026, 1, 16, tzinfo=UTC),
        rng=Random(0),
        config=PipelineConfig(),
    )
    ingest = IngestStage().run(IngestInput(file_name=_BOM.name, content=_BOM.read_bytes()), ctx)
    requirements = NormalizeStage(llm_client=None).run(ingest.output, ctx).output
    mocks = {k: str(_REPO_ROOT / v) for k, v in DEFAULT_MOCK_SUPPLIER_SNAPSHOTS.items()}
    adapters = orchestrator.default_adapters(
        (), use_live_suppliers=False, mock_supplier_snapshots=mocks
    )
    chain = orchestrator.run_sourcing_chain(requirements, adapters, None, ctx)
    plan_result = orchestrator.run_planning(
        {r.requirement_id: r for r in requirements}, chain.candidates, 100, ctx
    )
    plans = {plan.mode: plan for plan in plan_result.output}
    return chain.candidates, plans, [i.code for i in plan_result.issues]


def test_every_offer_comes_from_a_mock_supplier(run) -> None:
    candidates, _plans, _issues = run
    offers = [o for c in candidates for o in c.offers]

    assert offers
    assert {o.supplier for o in offers} == {
        SupplierId.MOUSER,
        SupplierId.DIGIKEY,
        SupplierId.FARNELL,
    }
    assert all(o.sku.startswith("MOCK-") for o in offers)


def test_part_carried_by_several_suppliers_is_one_candidate_with_all_offers(run) -> None:
    candidates, _plans, _issues = run
    lm358 = [c for c in candidates if c.mpn == "LM358DR"]

    assert len(lm358) == 1
    assert {o.supplier for o in lm358[0].offers} == {
        SupplierId.MOUSER,
        SupplierId.DIGIKEY,
        SupplierId.FARNELL,
    }


def test_every_mode_produces_a_plan_and_none_uses_fixture_supplier(run) -> None:
    _candidates, plans, _issues = run

    assert set(plans) == set(DecisionMode)
    for plan in plans.values():
        assert plan.lines
        assert SupplierId.FIXTURE not in {line.supplier for line in plan.lines}


def test_farnell_only_part_is_bought_from_farnell_in_every_plan(run) -> None:
    _candidates, plans, _issues = run

    for plan in plans.values():
        assert _FARNELL_ONLY_SKU in {line.sku for line in plan.lines}


def test_eur_priced_offer_is_excluded_from_every_plan(run) -> None:
    _candidates, plans, issues = run

    assert "offer_excluded_currency_mismatch" in issues
    for plan in plans.values():
        assert _EUR_SKU not in {line.sku for line in plan.lines}


def test_fastest_delivery_avoids_the_zero_stock_offer(run) -> None:
    _candidates, plans, _issues = run

    assert _ZERO_STOCK_SKU not in {line.sku for line in plans[DecisionMode.FASTEST_DELIVERY].lines}


def test_fewest_suppliers_never_uses_more_suppliers_than_lowest_cost(run) -> None:
    _candidates, plans, _issues = run
    fewest = {line.supplier for line in plans[DecisionMode.FEWEST_SUPPLIERS].lines}
    cheapest = {line.supplier for line in plans[DecisionMode.LOWEST_COST].lines}

    assert len(fewest) <= len(cheapest)


def test_lowest_cost_is_never_dearer_than_fewest_suppliers(run) -> None:
    _candidates, plans, _issues = run

    assert (
        plans[DecisionMode.LOWEST_COST].totals.grand_total
        <= plans[DecisionMode.FEWEST_SUPPLIERS].totals.grand_total
    )
