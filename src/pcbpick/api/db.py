"""SQLAlchemy persistence: projects, memberships, runs, and the approval ledger.

Targets PostgreSQL in production and SQLite in local dev/tests (see
`api.settings.Settings.database_url`) — schema uses only dialect-portable column
types. `ApprovalRecord` rows are inserted only; nothing in this module ever updates
or deletes one, per invariant 6 ("nothing reaches an export file without a recorded
engineer approval") and the append-only approval ledger `docs/roadmap.md` requires.
"""

from collections.abc import Generator, Iterable
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


# Project membership roles, ranked lowest to highest privilege.
ROLE_RANK: dict[str, int] = {"viewer": 0, "engineer": 1, "owner": 2}


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK[minimum]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    # SHA-256 of a single-use recovery code; None for users created before recovery existed.
    recovery_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    # Soft delete: runs, approvals and exports are retained for audit, per the append-only ledger.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"))
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))

    project: Mapped[Project] = relationship(back_populates="memberships")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_filename: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40))
    board_quantity: Mapped[int | None] = mapped_column(nullable=True)


class ApprovalRecord(Base):
    """One engineer's approval of one decision-mode plan for one run. Insert-only."""

    __tablename__ = "approval_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    decision_mode: Mapped[str] = mapped_column(String(40))
    plan_hash: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_high_tier_requirement_ids: Mapped[str] = mapped_column(Text, default="[]")
    acknowledged_stale_offer_snapshot_ids: Mapped[str] = mapped_column(Text, default="[]")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExportRecord(Base):
    """One generated export file. Insert-only, tied to the approval that authorized it."""

    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True)
    approval_id: Mapped[str] = mapped_column(String(32), ForeignKey("approval_records.id"))
    supplier: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(10))
    plan_hash: Mapped[str] = mapped_column(String(64))
    exported_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    file_path: Mapped[str] = mapped_column(String(1000))


def make_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            # Every connection in a pytest run must share the same in-memory DB.
            kwargs["poolclass"] = StaticPool
    return create_engine(database_url, connect_args=connect_args, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _add_missing_column(engine: Engine, table: str, column: str, ddl_type: str) -> None:
    # create_all never alters existing tables; add columns introduced after a dev DB was made.
    if column in {c["name"] for c in inspect(engine).get_columns(table)}:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _add_missing_column(engine, "users", "recovery_code_hash", "VARCHAR(64)")
    timestamp_type = (
        "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    )
    _add_missing_column(engine, "projects", "deleted_at", timestamp_type)


def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()


def user_project_role(session: Session, project_id: str, user_id: str) -> str | None:
    # Joining on Project makes a soft-deleted project unreachable for every authorized route.
    membership = (
        session.query(ProjectMembership)
        .join(Project, Project.id == ProjectMembership.project_id)
        .filter(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
            Project.deleted_at.is_(None),
        )
        .one_or_none()
    )
    return membership.role if membership else None


def latest_approval(session: Session, run_id: str, decision_mode: str) -> ApprovalRecord | None:
    return (
        session.query(ApprovalRecord)
        .filter_by(run_id=run_id, decision_mode=decision_mode)
        .order_by(ApprovalRecord.approved_at.desc())
        .first()
    )


def approvals_for_run(session: Session, run_id: str) -> Iterable[ApprovalRecord]:
    return (
        session.query(ApprovalRecord)
        .filter_by(run_id=run_id)
        .order_by(ApprovalRecord.approved_at.desc())
        .all()
    )
