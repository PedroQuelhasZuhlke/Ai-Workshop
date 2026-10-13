"""Project creation, listing, and membership management."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pcbpick.api.auth import get_current_user, get_session, require_role
from pcbpick.api.db import Project, ProjectMembership, User
from pcbpick.api.schemas import MemberAddRequest, ProjectCreateRequest, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    now = datetime.now(UTC)
    project = Project(name=body.name, created_at=now, created_by=user.id)
    session.add(project)
    session.flush()
    session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="owner"))
    session.commit()
    return ProjectOut(id=project.id, name=project.name, created_at=project.created_at, role="owner")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    session: Session = Depends(get_session), user: User = Depends(get_current_user)
) -> list[ProjectOut]:
    memberships = session.query(ProjectMembership).filter_by(user_id=user.id).all()
    out = []
    for membership in memberships:
        project = session.get(Project, membership.project_id)
        if project is not None and project.deleted_at is not None:
            out.append(
                ProjectOut(
                    id=project.id,
                    name=project.name,
                    created_at=project.created_at,
                    role=membership.role,
                )
            )
    return out


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("project_id", "viewer")),
) -> ProjectOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    membership = (
        session.query(ProjectMembership).filter_by(project_id=project_id, user_id=user.id).one()
    )
    return ProjectOut(
        id=project.id, name=project.name, created_at=project.created_at, role=membership.role
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    session: Session = Depends(get_session),
    _owner: User = Depends(require_role("project_id", "owner")),
) -> None:
    """Soft delete: hides the project from everyone, but keeps its runs, approvals and
    exports, since the approval ledger is append-only and exports must stay reconstructible."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    project.deleted_at = datetime.now(UTC)
    session.commit()


@router.post("/{project_id}/members", status_code=204)
def add_member(
    project_id: str,
    body: MemberAddRequest,
    session: Session = Depends(get_session),
    _owner: User = Depends(require_role("project_id", "owner")),
) -> None:
    target = session.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="user not found")
    existing = (
        session.query(ProjectMembership)
        .filter_by(project_id=project_id, user_id=body.user_id)
        .one_or_none()
    )
    if existing is not None:
        existing.role = body.role
    else:
        session.add(ProjectMembership(project_id=project_id, user_id=body.user_id, role=body.role))
    session.commit()
