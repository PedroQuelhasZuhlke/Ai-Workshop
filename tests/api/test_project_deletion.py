"""Project deletion is a soft delete: hidden from everyone, audit data retained."""

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from pcbpick.api.app import create_app
from pcbpick.api.db import ApprovalRecord, Project, Run
from pcbpick.api.settings import Settings
from tests.api.conftest import FIXTURE_CATALOG, auth_headers, create_project, register_user


def test_owner_can_delete_and_project_disappears(client: TestClient) -> None:
    owner = register_user(client, "Owner")
    headers = auth_headers(owner["api_key"])
    keep = create_project(client, owner["api_key"], "Keep")
    gone = create_project(client, owner["api_key"], "Gone")

    assert client.delete(f"/projects/{gone['id']}", headers=headers).status_code == 204

    assert [p["id"] for p in client.get("/projects", headers=headers).json()] == [keep["id"]]
    assert client.get(f"/projects/{gone['id']}", headers=headers).status_code == 404
    assert client.get(f"/projects/{gone['id']}/runs", headers=headers).status_code == 404


def test_deleted_project_blocks_all_run_routes(client: TestClient) -> None:
    owner = register_user(client, "Owner 2")
    headers = auth_headers(owner["api_key"])
    project = create_project(client, owner["api_key"], "Soon Gone")
    upload = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("x.csv", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=headers,
    )
    run_id = upload.json()["id"]

    client.delete(f"/projects/{project['id']}", headers=headers)

    base = f"/projects/{project['id']}/runs/{run_id}"
    assert client.get(base, headers=headers).status_code == 404
    assert client.get(f"{base}/approvals", headers=headers).status_code == 404
    assert client.get(f"{base}/exports", headers=headers).status_code == 404


def test_only_owner_can_delete(client: TestClient) -> None:
    owner = register_user(client, "Owner 3")
    engineer = register_user(client, "Engineer")
    project = create_project(client, owner["api_key"], "Protected")
    client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": engineer["id"], "role": "engineer"},
        headers=auth_headers(owner["api_key"]),
    )

    by_engineer = client.delete(
        f"/projects/{project['id']}", headers=auth_headers(engineer["api_key"])
    )
    assert by_engineer.status_code == 404
    outsider = register_user(client, "Outsider")
    by_outsider = client.delete(
        f"/projects/{project['id']}", headers=auth_headers(outsider["api_key"])
    )
    assert by_outsider.status_code == 404

    still_there = client.get(f"/projects/{project['id']}", headers=auth_headers(owner["api_key"]))
    assert still_there.status_code == 200


def test_delete_requires_authentication(client: TestClient) -> None:
    owner = register_user(client, "Owner 4")
    project = create_project(client, owner["api_key"], "Needs Auth")
    assert client.delete(f"/projects/{project['id']}").status_code == 401


def test_delete_retains_runs_and_approval_ledger(tmp_path: Path) -> None:
    settings = Settings(
        database_url="sqlite://",
        runs_root=tmp_path / "runs",
        catalog_snapshot_paths=(str(FIXTURE_CATALOG),),
        environment="test",
    )
    app = create_app(settings)
    client = TestClient(app)
    owner = register_user(client, "Owner 5")
    headers = auth_headers(owner["api_key"])
    project = create_project(client, owner["api_key"], "Audited")
    upload = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("x.csv", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=headers,
    )
    run_id = upload.json()["id"]

    session = app.state.session_factory()
    session.add(
        ApprovalRecord(
            run_id=run_id,
            decision_mode="lowest_cost",
            plan_hash="0" * 64,
            approved_by=owner["id"],
            approved_at=datetime.now(UTC),
        )
    )
    session.commit()

    client.delete(f"/projects/{project['id']}", headers=headers)

    session.expire_all()
    assert session.get(Project, project["id"]).deleted_at is not None
    assert session.get(Run, run_id) is not None
    assert session.query(ApprovalRecord).filter_by(run_id=run_id).count() == 1
    session.close()
