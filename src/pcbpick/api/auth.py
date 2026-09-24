"""Authentication and project-scoped authorization dependencies.

Every artifact-read route in `api.routers` depends on `require_role` (or
`get_current_user` alone for project-list/create routes), so access is checked on
every read, not just at upload — per `docs/architecture.md`'s security posture.
"""

from collections.abc import Callable, Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from pcbpick.api.db import Run, User, role_at_least, user_project_role


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(status_code=401, detail="missing X-Api-Key header")
    user = session.query(User).filter_by(api_key=api_key).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return user


def require_role(project_id_param: str, minimum: str) -> Callable[..., User]:
    """A dependency factory: the caller must hold at least `minimum` role on the
    project named by the path parameter `project_id_param`.

    A user with no membership at all gets 404, not 403 — project existence is not
    disclosed to callers who cannot access it.
    """

    def _dependency(
        request: Request,
        session: Session = Depends(get_session),
        user: User = Depends(get_current_user),
    ) -> User:
        project_id = request.path_params.get(project_id_param)
        role = user_project_role(session, str(project_id), user.id)
        if role is None or not role_at_least(role, minimum):
            raise HTTPException(status_code=404, detail="project not found")
        return user

    return _dependency


def get_owned_run(
    run_id: str,
    project_id: str,
    session: Session,
) -> Run:
    """A run scoped to its project — a run id from another project is a 404, not a 403."""
    run = session.query(Run).filter_by(id=run_id, project_id=project_id).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
