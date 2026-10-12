"""`live_adapters` requires at least one supplier with credentials; no network is used."""

import httpx
import pytest

from pcbpick.api.orchestrator import _fixture_catalog_notice, default_adapters, live_adapters
from pcbpick.config.secrets import CredentialsNotFoundError
from pcbpick.contracts.enums import SupplierId
from pcbpick.pipeline.results import Severity

_ALL_CREDENTIAL_VARS = (
    "PCBPICK_MOUSER_API_KEY",
    "PCBPICK_DIGIKEY_CLIENT_ID",
    "PCBPICK_DIGIKEY_CLIENT_SECRET",
    "PCBPICK_FARNELL_API_KEY",
)


@pytest.fixture(autouse=True)
def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)


def _client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))


def test_live_adapters_with_one_supplier_configured_returns_only_that_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("PCBPICK_MOUSER_API_KEY", "test-key")

    adapters = live_adapters(snapshot_root=tmp_path, http_client=_client())

    assert [a.supplier_id for a in adapters] == [SupplierId.MOUSER]


def test_live_adapters_skips_digikey_when_only_half_its_credentials_are_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("PCBPICK_DIGIKEY_CLIENT_ID", "id-only")
    monkeypatch.setenv("PCBPICK_FARNELL_API_KEY", "test-key")

    adapters = live_adapters(snapshot_root=tmp_path, http_client=_client())

    assert [a.supplier_id for a in adapters] == [SupplierId.FARNELL]


def test_live_adapters_raises_when_no_supplier_has_credentials(tmp_path) -> None:
    with pytest.raises(CredentialsNotFoundError, match="PCBPICK_USE_LIVE_SUPPLIERS"):
        live_adapters(snapshot_root=tmp_path, http_client=_client())


def test_default_adapters_with_live_flag_and_no_credentials_raises() -> None:
    with pytest.raises(CredentialsNotFoundError):
        default_adapters((), use_live_suppliers=True)


def test_fixture_adapter_yields_a_visible_warning() -> None:
    adapters = default_adapters((), use_live_suppliers=False)

    [issue] = _fixture_catalog_notice(adapters)

    assert issue.code == "using_fixture_catalog"
    assert issue.severity == Severity.WARNING


def test_live_adapters_yield_no_fixture_notice(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("PCBPICK_MOUSER_API_KEY", "test-key")
    adapters = live_adapters(snapshot_root=tmp_path, http_client=_client())

    assert _fixture_catalog_notice(adapters) == []
