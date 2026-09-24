"""Shared fixtures for API tests. In-memory SQLite, tmp-path run storage, no network."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pcbpick.api.app import create_app
from pcbpick.api.settings import Settings

FIXTURE_CATALOG = (
    Path(__file__).resolve().parents[2] / "fixtures" / "catalogs" / "kicad_golden_snapshot.json"
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite://",
        runs_root=tmp_path / "runs",
        catalog_snapshot_paths=(str(FIXTURE_CATALOG),),
        cors_origins=("http://localhost:5173",),
        environment="test",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    return TestClient(app)


def register_user(client: TestClient, display_name: str) -> dict[str, str]:
    response = client.post("/users", json={"display_name": display_name})
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(api_key: str) -> dict[str, str]:
    return {"x-api-key": api_key}


def create_project(client: TestClient, api_key: str, name: str) -> dict[str, object]:
    response = client.post("/projects", json={"name": name}, headers=auth_headers(api_key))
    assert response.status_code == 200, response.text
    return response.json()
