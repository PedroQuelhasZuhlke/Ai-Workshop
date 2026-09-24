"""Tests for `pcbpick.config.secrets`, per
`.github/instructions/supplier-adapters.instructions.md`'s credential-handling rules.

No test ever sets a real environment variable or reads a real secret: every test
injects a fake `provider` callable instead.
"""

from collections.abc import Callable

import pytest

from pcbpick.config.secrets import Credentials, CredentialsNotFoundError, load_credentials
from pcbpick.contracts.enums import SupplierId

_REAL_LOOKING_SECRET = "sk-live-abc123-do-not-print-me"


def _fake_provider(values: dict[str, str]) -> Callable[[str], str | None]:
    def provider(name: str) -> str | None:
        return values.get(name)

    return provider


def test_load_credentials_reads_single_api_key_supplier() -> None:
    provider = _fake_provider({"PCBPICK_MOUSER_API_KEY": _REAL_LOOKING_SECRET})

    creds = load_credentials(SupplierId.MOUSER, provider=provider)

    assert creds.supplier == SupplierId.MOUSER
    assert creds.api_key == _REAL_LOOKING_SECRET
    assert creds.client_secret is None


def test_load_credentials_reads_two_part_digikey_credentials() -> None:
    provider = _fake_provider(
        {
            "PCBPICK_DIGIKEY_CLIENT_ID": "client-id-value",
            "PCBPICK_DIGIKEY_CLIENT_SECRET": _REAL_LOOKING_SECRET,
        }
    )

    creds = load_credentials(SupplierId.DIGIKEY, provider=provider)

    assert creds.api_key == "client-id-value"
    assert creds.client_secret == _REAL_LOOKING_SECRET


def test_load_credentials_raises_when_env_var_missing() -> None:
    provider = _fake_provider({})

    with pytest.raises(CredentialsNotFoundError) as exc_info:
        load_credentials(SupplierId.MOUSER, provider=provider)

    assert "PCBPICK_MOUSER_API_KEY" in str(exc_info.value)


def test_load_credentials_raises_when_digikey_secondary_var_missing() -> None:
    provider = _fake_provider({"PCBPICK_DIGIKEY_CLIENT_ID": "client-id-value"})

    with pytest.raises(CredentialsNotFoundError):
        load_credentials(SupplierId.DIGIKEY, provider=provider)


def test_load_credentials_raises_for_fixture_supplier_with_no_mapping() -> None:
    with pytest.raises(CredentialsNotFoundError):
        load_credentials(SupplierId.FIXTURE, provider=_fake_provider({}))


def test_credentials_repr_never_reveals_api_key_or_client_secret() -> None:
    creds = Credentials(
        supplier=SupplierId.DIGIKEY, api_key=_REAL_LOOKING_SECRET, client_secret="another-secret"
    )

    rendered = repr(creds)

    assert _REAL_LOOKING_SECRET not in rendered
    assert "another-secret" not in rendered
    assert str(creds) == rendered


def test_credentials_str_never_reveals_secret_with_no_client_secret() -> None:
    creds = Credentials(supplier=SupplierId.MOUSER, api_key=_REAL_LOOKING_SECRET)

    assert _REAL_LOOKING_SECRET not in str(creds)
    assert _REAL_LOOKING_SECRET not in repr(creds)


def test_credentials_not_found_error_message_never_contains_a_value() -> None:
    # Only the *variable name* may appear in an exception message, never a value —
    # there is no value to leak here since the variable was never set, but this
    # guards against a future change accidentally interpolating a fetched value in.
    provider = _fake_provider({})
    try:
        load_credentials(SupplierId.FARNELL, provider=provider)
    except CredentialsNotFoundError as exc:
        assert "PCBPICK_FARNELL_API_KEY" in str(exc)
