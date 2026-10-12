"""Offline mock Mouser/DigiKey/Farnell catalogs: supplier stamping and default wiring."""

from pathlib import Path

import pytest

from pcbpick.api.orchestrator import default_adapters
from pcbpick.api.settings import DEFAULT_MOCK_SUPPLIER_SNAPSHOTS, Settings, get_settings
from pcbpick.contracts.enums import SupplierId
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _absolute_mocks() -> dict[str, str]:
    return {k: str(_REPO_ROOT / v) for k, v in DEFAULT_MOCK_SUPPLIER_SNAPSHOTS.items()}


@pytest.mark.parametrize("supplier", [SupplierId.MOUSER, SupplierId.DIGIKEY, SupplierId.FARNELL])
def test_mock_adapter_stamps_its_own_supplier_on_every_offer(supplier: SupplierId) -> None:
    path = _REPO_ROOT / DEFAULT_MOCK_SUPPLIER_SNAPSHOTS[supplier.value]
    adapter = FixtureAdapter([path], supplier=supplier)

    part = adapter.details("LM358DR")
    assert part is not None
    offers = [o for sku in part.skus for o in adapter.offers(sku.sku, quantity=1)]

    assert adapter.supplier_id == supplier
    assert offers
    assert {o.supplier for o in offers} == {supplier}
    assert all(o.sku.startswith("MOCK-") for o in offers)
    assert all(o.snapshot_id == f"mock-{supplier.value}-2026-01-15" for o in offers)


def test_mock_snapshot_cannot_be_loaded_as_another_supplier() -> None:
    path = _REPO_ROOT / DEFAULT_MOCK_SUPPLIER_SNAPSHOTS["mouser"]

    with pytest.raises(ValueError, match="declares supplier 'mouser'"):
        FixtureAdapter([path], supplier=SupplierId.DIGIKEY)

    with pytest.raises(ValueError, match="declares supplier 'mouser'"):
        FixtureAdapter([path])


def test_default_adapters_builds_one_mock_adapter_per_supplier() -> None:
    adapters = default_adapters(
        (), use_live_suppliers=False, mock_supplier_snapshots=_absolute_mocks()
    )

    assert [a.supplier_id for a in adapters] == [
        SupplierId.DIGIKEY,
        SupplierId.FARNELL,
        SupplierId.MOUSER,
    ]


def test_default_adapters_keeps_the_plain_fixture_adapter_when_paths_are_given() -> None:
    catalog = str(_REPO_ROOT / "fixtures" / "catalogs" / "kicad_golden_snapshot.json")

    adapters = default_adapters(
        (catalog,), use_live_suppliers=False, mock_supplier_snapshots=_absolute_mocks()
    )

    assert [a.supplier_id for a in adapters][0] == SupplierId.FIXTURE
    assert len(adapters) == 4


def test_settings_default_to_no_mocks_but_the_app_enables_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PCBPICK_CATALOG_SNAPSHOTS", raising=False)
    get_settings.cache_clear()
    try:
        assert Settings().mock_supplier_snapshots == {}
        app_settings = get_settings()
        assert app_settings.catalog_snapshot_paths == ()
        assert set(app_settings.mock_supplier_snapshots) == {"mouser", "digikey", "farnell"}
    finally:
        get_settings.cache_clear()


def test_explicit_catalog_env_var_turns_the_mocks_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PCBPICK_CATALOG_SNAPSHOTS", "fixtures/catalogs/kicad_golden_snapshot.json")
    get_settings.cache_clear()
    try:
        app_settings = get_settings()
        assert app_settings.mock_supplier_snapshots == {}
        assert app_settings.catalog_snapshot_paths == (
            "fixtures/catalogs/kicad_golden_snapshot.json",
        )
    finally:
        get_settings.cache_clear()
