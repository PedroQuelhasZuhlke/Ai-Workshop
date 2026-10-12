"""Key recovery: a single-use recovery code rotates the API key and itself."""

from pathlib import Path

from fastapi.testclient import TestClient

from pcbpick.api.app import create_app
from pcbpick.api.settings import Settings
from tests.api.conftest import FIXTURE_CATALOG, auth_headers, create_project, register_user


def test_registration_returns_a_recovery_code(client: TestClient) -> None:
    user = register_user(client, "Recoverable")
    assert user["recovery_code"]
    assert user["recovery_code"] != user["api_key"]


def test_recovery_rotates_key_and_keeps_project_access(client: TestClient) -> None:
    user = register_user(client, "Lost Key")
    project = create_project(client, user["api_key"], "Survives Recovery")

    response = client.post("/users/recover", json={"recovery_code": user["recovery_code"]})
    assert response.status_code == 200, response.text
    recovered = response.json()

    assert recovered["id"] == user["id"]
    assert recovered["api_key"] != user["api_key"]
    assert recovered["recovery_code"] != user["recovery_code"]

    assert client.get("/projects", headers=auth_headers(user["api_key"])).status_code == 401
    projects = client.get("/projects", headers=auth_headers(recovered["api_key"]))
    assert [p["id"] for p in projects.json()] == [project["id"]]


def test_recovery_code_is_single_use(client: TestClient) -> None:
    user = register_user(client, "Single Use")
    first = client.post("/users/recover", json={"recovery_code": user["recovery_code"]})
    assert first.status_code == 200

    replay = client.post("/users/recover", json={"recovery_code": user["recovery_code"]})
    assert replay.status_code == 401


def test_wrong_recovery_code_is_rejected(client: TestClient) -> None:
    register_user(client, "Someone")
    response = client.post("/users/recover", json={"recovery_code": "not-a-real-code"})
    assert response.status_code == 401


def test_recovery_disabled_outside_dev_and_test(tmp_path: Path) -> None:
    settings = Settings(
        database_url="sqlite://",
        runs_root=tmp_path / "runs",
        catalog_snapshot_paths=(str(FIXTURE_CATALOG),),
        environment="production",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/users/recover", json={"recovery_code": "anything"})
    assert response.status_code == 403
