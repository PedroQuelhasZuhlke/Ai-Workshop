"""Renaming a project: PATCH /projects/{id} with {"name": ...}. Owner only."""

from fastapi.testclient import TestClient

from tests.api.conftest import auth_headers, create_project, register_user


def test_owner_can_rename_project(client: TestClient) -> None:
    owner = register_user(client, "Owner")
    headers = auth_headers(owner["api_key"])
    project = create_project(client, owner["api_key"], "Old name")

    response = client.patch(f"/projects/{project['id']}", json={"name": "New name"}, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "New name"
    assert response.json()["id"] == project["id"]
    listed = client.get("/projects", headers=headers).json()
    assert [p["name"] for p in listed] == ["New name"]


def test_rename_rejects_empty_name(client: TestClient) -> None:
    owner = register_user(client, "Owner 2")
    headers = auth_headers(owner["api_key"])
    project = create_project(client, owner["api_key"], "Keep me")

    response = client.patch(f"/projects/{project['id']}", json={"name": ""}, headers=headers)

    assert response.status_code == 422
    assert client.get(f"/projects/{project['id']}", headers=headers).json()["name"] == "Keep me"


def test_only_owner_can_rename(client: TestClient) -> None:
    owner = register_user(client, "Owner 3")
    engineer = register_user(client, "Engineer 3")
    outsider = register_user(client, "Outsider 3")
    project = create_project(client, owner["api_key"], "Original")
    client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": engineer["id"], "role": "engineer"},
        headers=auth_headers(owner["api_key"]),
    )

    for user in (engineer, outsider):
        response = client.patch(
            f"/projects/{project['id']}",
            json={"name": "Hijacked"},
            headers=auth_headers(user["api_key"]),
        )
        assert response.status_code == 404

    name = client.get(f"/projects/{project['id']}", headers=auth_headers(owner["api_key"]))
    assert name.json()["name"] == "Original"


def test_rename_requires_authentication(client: TestClient) -> None:
    owner = register_user(client, "Owner 4")
    project = create_project(client, owner["api_key"], "Original")

    assert client.patch(f"/projects/{project['id']}", json={"name": "X"}).status_code == 401
