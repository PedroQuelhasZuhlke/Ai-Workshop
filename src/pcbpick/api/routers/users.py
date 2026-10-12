"""Bootstrap user registration and key recovery.

No external identity provider is wired yet (out of scope for this milestone) — this
is a deliberately minimal internal-directory stand-in, not a public signup surface.
It never grants project access on its own: a fresh user has no memberships until an
existing project owner adds one via `POST /projects/{project_id}/members`.

Each account gets an API key plus a single-use recovery code, shown once. Presenting
the recovery code to `POST /users/recover` rotates both, so a lost or leaked key can
be replaced without losing the account's project memberships or approval history.

Disabled outside `development`/`test` -- a production deployment replaces these routes
entirely with real identity-provider-backed authentication rather than open self-
registration of API keys.
"""

import hashlib
from secrets import token_hex, token_urlsafe
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pcbpick.api.auth import get_session
from pcbpick.api.db import User
from pcbpick.api.schemas import DevUserCreateRequest, DevUserOut, RecoverRequest
from pcbpick.api.settings import Settings, get_settings

router = APIRouter(prefix="/users", tags=["users"])


def _hash_recovery_code(code: str) -> str:
    # The code is 192 random bits, so a plain SHA-256 is enough; no password KDF needed.
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _require_open_registration(settings: Settings) -> None:
    if settings.environment not in ("development", "test"):
        raise HTTPException(status_code=403, detail="open user registration is disabled")


def _issue_credentials(user: User) -> DevUserOut:
    """Rotates the key and recovery code on `user` (uncommitted) and returns them once."""
    recovery_code = token_urlsafe(24)
    user.api_key = token_hex(24)
    user.recovery_code_hash = _hash_recovery_code(recovery_code)
    return DevUserOut(
        id=user.id,
        display_name=user.display_name,
        api_key=user.api_key,
        recovery_code=recovery_code,
    )


@router.post("", response_model=DevUserOut)
def create_user(
    body: DevUserCreateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DevUserOut:
    _require_open_registration(settings)
    user = User(id=uuid4().hex, display_name=body.display_name)
    credentials = _issue_credentials(user)
    session.add(user)
    session.commit()
    return credentials


@router.post("/recover", response_model=DevUserOut)
def recover_user(
    body: RecoverRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DevUserOut:
    _require_open_registration(settings)
    user = (
        session.query(User)
        .filter_by(recovery_code_hash=_hash_recovery_code(body.recovery_code.strip()))
        .one_or_none()
    )
    if user is None:
        raise HTTPException(status_code=401, detail="invalid recovery code")
    credentials = _issue_credentials(user)
    session.commit()
    return credentials
