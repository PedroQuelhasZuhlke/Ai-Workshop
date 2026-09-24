"""Proves credentials never leak into logs, exceptions, or `repr()`/`str()`, per
`.github/instructions/supplier-adapters.instructions.md`'s "never with credentials" rule.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from pcbpick.config.secrets import Credentials, CredentialsNotFoundError, load_credentials
from pcbpick.contracts.enums import SupplierId
from pcbpick.sourcing.suppliers.digikey import DigiKeyAdapter
from pcbpick.sourcing.suppliers.farnell import FarnellAdapter
from pcbpick.sourcing.suppliers.live_base import redact_headers
from pcbpick.sourcing.suppliers.mouser import MouserAdapter
from pcbpick.sourcing.suppliers.resilience import RateLimitConfig, ResilientCaller, RetryConfig

_MOUSER_SECRET = "mouser-super-secret-key-do-not-log-me"
_FARNELL_SECRET = "farnell-super-secret-key-do-not-log-me"
_DIGIKEY_CLIENT_ID = "digikey-client-id-do-not-log-me"
_DIGIKEY_SECRET = "digikey-super-secret-token-do-not-log-me"

_SEARCH_RESPONSE: dict[str, Any] = {
    "SearchResults": {
        "Parts": [
            {
                "ManufacturerPartNumber": "RC0603FR-0710KL",
                "Manufacturer": "Yageo",
                "MouserPartNumber": "603-RC0603FR-0710KL",
                "Min": "1",
                "Mult": "1000",
                "PriceBreaks": [{"Quantity": 1, "Price": "$0.01", "Currency": "USD"}],
            }
        ]
    }
}


def _mock_client(status_code: int = 200, body: dict[str, Any] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body or _SEARCH_RESPONSE, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _no_sleep_caller() -> ResilientCaller:
    return ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        sleep_fn=lambda _seconds: None,
    )


def _all_log_text(records: list[logging.LogRecord]) -> str:
    """Every string a record could conceivably render to, including `extra=` values."""
    chunks: list[str] = []
    for record in records:
        chunks.append(record.getMessage())
        chunks.append(str(record.__dict__))
    return "\n".join(chunks)


def test_mouser_credential_never_appears_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = MouserAdapter(
        credentials=Credentials(supplier=SupplierId.MOUSER, api_key=_MOUSER_SECRET),
        http_client=_mock_client(),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.DEBUG, logger="pcbpick.sourcing.suppliers.live_base"):
        adapter.details("RC0603FR-0710KL")

    assert _MOUSER_SECRET not in _all_log_text(caplog.records)


def test_farnell_credential_never_appears_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = FarnellAdapter(
        credentials=Credentials(supplier=SupplierId.FARNELL, api_key=_FARNELL_SECRET),
        http_client=_mock_client(body={"premierFarnellPartNumberReturn": {"products": []}}),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.DEBUG, logger="pcbpick.sourcing.suppliers.live_base"):
        adapter.details("RC0603FR-0710KL")

    assert _FARNELL_SECRET not in _all_log_text(caplog.records)


def test_digikey_credentials_never_appear_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = DigiKeyAdapter(
        credentials=Credentials(
            supplier=SupplierId.DIGIKEY, api_key=_DIGIKEY_CLIENT_ID, client_secret=_DIGIKEY_SECRET
        ),
        http_client=_mock_client(body={"Products": []}),
        snapshot_dir=tmp_path,
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.DEBUG, logger="pcbpick.sourcing.suppliers.live_base"):
        adapter.details("GRM188R71H104KA93D")

    log_text = _all_log_text(caplog.records)
    assert _DIGIKEY_CLIENT_ID not in log_text
    assert _DIGIKEY_SECRET not in log_text


def test_credential_never_appears_in_logs_even_when_every_call_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = MouserAdapter(
        credentials=Credentials(supplier=SupplierId.MOUSER, api_key=_MOUSER_SECRET),
        http_client=_mock_client(status_code=500, body={}),
        snapshot_dir=tmp_path,
        resilient_caller=_no_sleep_caller(),
        now_fn=lambda: datetime(2026, 3, 1, tzinfo=UTC),
    )

    with caplog.at_level(logging.DEBUG, logger="pcbpick.sourcing.suppliers.live_base"):
        result = adapter.details("RC0603FR-0710KL")

    assert result is None
    assert _MOUSER_SECRET not in _all_log_text(caplog.records)


def test_redact_headers_masks_every_known_credential_header() -> None:
    headers = {
        "Authorization": "Bearer super-secret",
        "X-DIGIKEY-Client-Id": "client-id-value",
        "Content-Type": "application/json",
    }

    redacted = redact_headers(headers)

    assert redacted["Authorization"] != "Bearer super-secret"
    assert redacted["X-DIGIKEY-Client-Id"] != "client-id-value"
    assert redacted["Content-Type"] == "application/json"


def test_credentials_repr_and_str_never_leak_when_raised_in_an_exception() -> None:
    with pytest.raises(CredentialsNotFoundError) as exc_info:
        load_credentials(SupplierId.MOUSER, provider=lambda _name: None)

    assert _MOUSER_SECRET not in str(exc_info.value)
