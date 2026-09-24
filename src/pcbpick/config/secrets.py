"""The secret store live supplier adapters read API credentials from.

Per `.github/instructions/supplier-adapters.instructions.md`: credentials come from
here and nowhere else — never a literal, never a committed file, never a run
artifact. `load_credentials` reads environment variables by default; tests inject a
fake `provider` callable instead of setting real environment variables, so no test
ever needs a real secret. `Credentials.__repr__`/`__str__` redact every secret value,
so accidentally logging or `assert`-printing one never leaks it.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass

from pcbpick.contracts.enums import SupplierId
from pcbpick.errors import PcbPickError

_REDACTED = "<redacted>"


class CredentialsNotFoundError(PcbPickError):
    """Raised when a supplier's credentials cannot be located in the secret store."""


# Maps a supplier to the environment variable(s) that hold its credential(s).
# DigiKey's OAuth2 client-credentials flow needs a client id *and* a client secret;
# Mouser/Farnell need a single API key, so their secondary variable is `None`.
_ENV_VARS_BY_SUPPLIER: dict[SupplierId, tuple[str, str | None]] = {
    SupplierId.MOUSER: ("PCBPICK_MOUSER_API_KEY", None),
    SupplierId.FARNELL: ("PCBPICK_FARNELL_API_KEY", None),
    SupplierId.DIGIKEY: ("PCBPICK_DIGIKEY_CLIENT_ID", "PCBPICK_DIGIKEY_CLIENT_SECRET"),
}

# Reads one named environment variable. Tests substitute their own provider instead
# of calling `os.environ.get` directly, so no real secret is ever needed for a test.
SecretProvider = Callable[[str], str | None]


def _env_provider(name: str) -> str | None:
    return os.environ.get(name)


@dataclass(frozen=True)
class Credentials:
    """One supplier's API credential(s), never printable in cleartext.

    `api_key` is the sole credential for Mouser/Farnell and the OAuth2 client id for
    DigiKey; `client_secret` is `None` unless the supplier needs a second value.
    """

    supplier: SupplierId
    api_key: str
    client_secret: str | None = None

    def __repr__(self) -> str:
        secret_repr = _REDACTED if self.client_secret is not None else None
        return (
            f"Credentials(supplier={self.supplier.value!r}, api_key={_REDACTED!r}, "
            f"client_secret={secret_repr!r})"
        )

    __str__ = __repr__


def load_credentials(
    supplier: SupplierId, *, provider: SecretProvider = _env_provider
) -> Credentials:
    """Reads one supplier's credential(s) via `provider` (environment variables by default).

    Raises `CredentialsNotFoundError` — never a bare `KeyError`/`ValueError` — if a
    required variable is unset or empty. The error message names the *variable*, never
    the value, so it stays safe to log or surface to an engineer.
    """
    mapping = _ENV_VARS_BY_SUPPLIER.get(supplier)
    if mapping is None:
        raise CredentialsNotFoundError(
            f"no credential mapping defined for supplier {supplier.value!r}"
        )

    api_key_var, secret_var = mapping
    api_key = provider(api_key_var)
    if not api_key:
        raise CredentialsNotFoundError(
            f"missing credential: environment variable {api_key_var!r} is unset for supplier "
            f"{supplier.value!r}"
        )

    client_secret: str | None = None
    if secret_var is not None:
        client_secret = provider(secret_var)
        if not client_secret:
            raise CredentialsNotFoundError(
                f"missing credential: environment variable {secret_var!r} is unset for supplier "
                f"{supplier.value!r}"
            )

    return Credentials(supplier=supplier, api_key=api_key, client_secret=client_secret)
