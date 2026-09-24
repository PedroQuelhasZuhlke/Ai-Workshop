"""Bootstrap user registration.

No external identity provider is wired yet (out of scope for this milestone) — this
is a deliberately minimal internal-directory stand-in, not a public signup surface.
It never grants project access on its own: a fresh user has no memberships until an
existing project owner adds one via `POST /projects/{project_id}/members`.

Disabled outside `development`/`test` -- a production deployment replaces this route
entirely with real identity-provider-backed authentication rather than open self-
registration of API keys.
"""

from secrets import token_hex

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pcbpick.api.auth import get_session
from pcbpick.api.db import User
from pcbpick.api.schemas import DevUserCreateRequest, DevUserOut
from pcbpick.api.settings import Settings, get_settings

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=DevUserOut)
def create_user(
    body: DevUserCreateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DevUserOut:
    if settings.environment not in ("development", "test"):
        raise HTTPException(status_code=403, detail="open user registration is disabled")
    user = User(api_key=token_hex(24), display_name=body.display_name)
    session.add(user)
    session.commit()
    return DevUserOut(id=user.id, display_name=user.display_name, api_key=user.api_key)
