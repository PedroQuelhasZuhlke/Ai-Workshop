"""API-layer configuration. Not a domain contract — see `docs/data-contracts.md` for those."""

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Environment-driven configuration for the FastAPI app.

    `database_url` targets PostgreSQL in production (`postgresql+psycopg2://...`, per
    `docs/architecture.md`'s persistence table) and SQLite in local dev/tests — the
    schema is defined with plain SQLAlchemy Core types so both dialects work
    unchanged. Tests never point this at a live network database.
    """

    database_url: str = "sqlite:///./pcbpick_api.db"
    runs_root: Path = Path("runs")
    catalog_snapshot_paths: tuple[str, ...] = ("fixtures/catalogs/kicad_golden_snapshot.json",)
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    environment: str = "development"
    # `None` in production: every pipeline `StageContext.now` uses the real wall
    # clock. Tests set this so stale-offer detection against a pinned fixture
    # snapshot's `fetched_at` stays deterministic, per
    # `.github/instructions/testing.instructions.md`'s "no wall-clock dependence".
    clock_override: datetime | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("PCBPICK_DATABASE_URL", "sqlite:///./pcbpick_api.db"),
        runs_root=Path(os.environ.get("PCBPICK_RUNS_ROOT", "runs")),
        catalog_snapshot_paths=tuple(
            os.environ.get(
                "PCBPICK_CATALOG_SNAPSHOTS", "fixtures/catalogs/kicad_golden_snapshot.json"
            ).split(os.pathsep)
        ),
        cors_origins=tuple(
            os.environ.get("PCBPICK_CORS_ORIGINS", "http://localhost:5173").split(",")
        ),
        environment=os.environ.get("PCBPICK_ENVIRONMENT", "development"),
    )
