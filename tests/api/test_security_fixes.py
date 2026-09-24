"""Regression tests for the invariant-auditor's M6 findings."""

from pathlib import Path

from fastapi.testclient import TestClient

from pcbpick.api.app import create_app
from pcbpick.api.settings import Settings
from tests.api.conftest import FIXTURE_CATALOG, auth_headers, create_project, register_user


def test_upload_rejects_path_traversal_filename(client: TestClient) -> None:
    user = register_user(client, "Sec Engineer")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "Sec Board")

    response = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("../../../../etc/passwd", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=headers,
    )
    assert response.status_code == 400


def test_resolving_only_parameters_does_not_clear_unresolved_category(
    client: TestClient,
) -> None:
    """A requirement whose `category` is unresolved must stay unresolved unless the
    engineer explicitly supplies `category` -- patching only `parameters` must never
    silently confirm a category nobody reviewed."""
    user = register_user(client, "Sec Engineer 2")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "Sec Board 2")
    project_id = project["id"]

    bom = Path(__file__).resolve().parents[2] / "fixtures" / "boms" / "kicad_bom.csv"
    with bom.open("rb") as fh:
        run = client.post(
            f"/projects/{project_id}/runs",
            files={"file": ("kicad_bom.csv", fh, "text/csv")},
            headers=headers,
        ).json()
    base = f"/projects/{project_id}/runs/{run['id']}"
    proposal = client.get(f"{base}/mapping", headers=headers).json()["mapping_proposal"]
    confirmed = {m["target_field"]: m["source_column"] for m in proposal["mappings"]}
    client.post(f"{base}/mapping/confirm", json={"mappings": confirmed}, headers=headers)

    requirements = client.get(f"{base}/requirements", headers=headers).json()["requirements"]
    # req-0005 (U1, LM358) has `category` unresolved and no parameter requirements.
    target = next(r for r in requirements if r["requirement_id"] == "req-0005")
    assert "category" in target["unresolved"]

    # Patch only a footprint field, never `category`.
    response = client.post(
        f"{base}/requirements/req-0005/resolve",
        json={"footprint": {"pin_count": 8}},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()["requirement"]
    assert "category" in updated["unresolved"], updated


def test_open_user_registration_disabled_outside_dev_and_test(tmp_path: Path) -> None:
    settings = Settings(
        database_url="sqlite://",
        runs_root=tmp_path / "runs",
        catalog_snapshot_paths=(str(FIXTURE_CATALOG),),
        environment="production",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/users", json={"display_name": "Someone"})
    assert response.status_code == 403


def test_upload_rejects_oversized_file(client: TestClient) -> None:
    user = register_user(client, "Big Upload")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "Big Board")

    from pcbpick.ingest.readers import MAX_FILE_SIZE_BYTES

    oversized = b"Reference,Value\n" + b"R1,10k\n" * (MAX_FILE_SIZE_BYTES // 5)
    response = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("huge.csv", oversized, "text/csv")},
        headers=headers,
    )
    assert response.status_code == 413
