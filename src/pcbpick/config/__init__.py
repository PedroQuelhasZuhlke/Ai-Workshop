"""Configuration and secret access, kept out of `contracts/` and every pure stage.

Only `pcbpick.config.secrets` exists here today: the secret store live supplier
adapters read API credentials from (see
`.github/instructions/supplier-adapters.instructions.md`).
"""

from pcbpick.config.secrets import Credentials, CredentialsNotFoundError, load_credentials

__all__ = ["Credentials", "CredentialsNotFoundError", "load_credentials"]
