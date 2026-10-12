"""API-layer configuration. Not a domain contract — see `docs/data-contracts.md` for those."""

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

DEFAULT_MOCK_SUPPLIER_SNAPSHOTS: dict[str, str] = {
    "mouser": "demo/catalogs/mock_mouser.json",
    "digikey": "demo/catalogs/mock_digikey.json",
    "farnell": "demo/catalogs/mock_farnell.json",
}


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
    # Offline mocks of real suppliers, keyed by `SupplierId` value. Empty by default so
    # tests stay pinned to one catalog; `get_settings()` turns them on for the app.
    mock_supplier_snapshots: dict[str, str] = {}
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    environment: str = "development"
    # `None` in production: every pipeline `StageContext.now` uses the real wall
    # clock. Tests set this so stale-offer detection against a pinned fixture
    # snapshot's `fetched_at` stays deterministic, per
    # `.github/instructions/testing.instructions.md`'s "no wall-clock dependence".
    clock_override: datetime | None = None


@lru_cache
def get_settings() -> Settings:
    explicit_catalogs = os.environ.get("PCBPICK_CATALOG_SNAPSHOTS")
    return Settings(
        database_url=os.environ.get("PCBPICK_DATABASE_URL", "sqlite:///./pcbpick_api.db"),
        runs_root=Path(os.environ.get("PCBPICK_RUNS_ROOT", "runs")),
        # Unset -> the mock Mouser/DigiKey/Farnell catalogs; set -> exactly those files.
        catalog_snapshot_paths=(
            tuple(explicit_catalogs.split(os.pathsep)) if explicit_catalogs else ()
        ),
        mock_supplier_snapshots={} if explicit_catalogs else dict(DEFAULT_MOCK_SUPPLIER_SNAPSHOTS),
        cors_origins=tuple(
            os.environ.get("PCBPICK_CORS_ORIGINS", "http://localhost:5173").split(",")
        ),
        environment=os.environ.get("PCBPICK_ENVIRONMENT", "development"),
    )
