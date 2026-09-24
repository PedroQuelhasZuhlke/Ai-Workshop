"""Project-scoped authorization: every artifact read/write must check membership."""

from fastapi.testclient import TestClient

from tests.api.conftest import auth_headers, create_project, register_user


def test_missing_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/projects")
    assert response.status_code == 401


def test_invalid_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/projects", headers=auth_headers("not-a-real-key"))
    assert response.status_code == 401


def test_non_member_cannot_read_project(client: TestClient) -> None:
    owner = register_user(client, "Owner")
    project = create_project(client, owner["api_key"], "Confidential Board")

    outsider = register_user(client, "Outsider")
    response = client.get(f"/projects/{project['id']}", headers=auth_headers(outsider["api_key"]))
    assert response.status_code == 404


def test_non_member_cannot_list_runs_or_upload(client: TestClient) -> None:
    owner = register_user(client, "Owner2")
    project = create_project(client, owner["api_key"], "Another Board")

    outsider = register_user(client, "Outsider2")
    outsider_headers = auth_headers(outsider["api_key"])

    assert (
        client.get(f"/projects/{project['id']}/runs", headers=outsider_headers).status_code == 404
    )
    upload = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("x.csv", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=outsider_headers,
    )
    assert upload.status_code == 404


def test_viewer_cannot_mutate(client: TestClient) -> None:
    owner = register_user(client, "Owner3")
    project = create_project(client, owner["api_key"], "Viewer Board")

    viewer = register_user(client, "Viewer")
    client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": viewer["id"], "role": "viewer"},
        headers=auth_headers(owner["api_key"]),
    )
    viewer_headers = auth_headers(viewer["api_key"])

    # A viewer can read...
    assert client.get(f"/projects/{project['id']}/runs", headers=viewer_headers).status_code == 200
    # ...but not upload.
    upload = client.post(
        f"/projects/{project['id']}/runs",
        files={"file": ("x.csv", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=viewer_headers,
    )
    assert upload.status_code == 404


def test_run_from_another_project_is_not_found(client: TestClient) -> None:
    owner = register_user(client, "Owner4")
    headers = auth_headers(owner["api_key"])
    project_a = create_project(client, owner["api_key"], "Board A")
    project_b = create_project(client, owner["api_key"], "Board B")

    with open(__file__, "rb"):
        pass
    upload = client.post(
        f"/projects/{project_a['id']}/runs",
        files={"file": ("x.csv", b"Reference,Value\nR1,10k\n", "text/csv")},
        headers=headers,
    )
    run_id = upload.json()["id"]

    cross = client.get(f"/projects/{project_b['id']}/runs/{run_id}", headers=headers)
    assert cross.status_code == 404


def test_only_owner_can_add_members(client: TestClient) -> None:
    owner = register_user(client, "Owner5")
    project = create_project(client, owner["api_key"], "Owner Only Board")
    engineer = register_user(client, "Engineer5")
    client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": engineer["id"], "role": "engineer"},
        headers=auth_headers(owner["api_key"]),
    )

    other_user = register_user(client, "Random")
    response = client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": other_user["id"], "role": "engineer"},
        headers=auth_headers(engineer["api_key"]),
    )
    assert response.status_code == 404
