"""Backtracking: editing an earlier step invalidates later ones until they are re-run."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.api.conftest import auth_headers, create_project, register_user

KICAD_BOM = Path(__file__).resolve().parents[2] / "fixtures" / "boms" / "kicad_bom.csv"

R0_PATCH = {
    "parameters": {"tolerance_pct": {"value": "1", "unit": "percent", "raw_text": "1%"}},
    "footprint": {
        "package_code": "RESC1608X55N",
        "pin_count": 2,
        "length_mm": "1.6",
        "width_mm": "0.8",
        "height_mm": "0.55",
    },
}


def _planned_run(client: TestClient) -> tuple[str, dict[str, str]]:
    user = register_user(client, "Backtracker")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "Backtrack Board")
    with KICAD_BOM.open("rb") as fh:
        run = client.post(
            f"/projects/{project['id']}/runs",
            files={"file": ("kicad_bom.csv", fh, "text/csv")},
            headers=headers,
        ).json()
    base = f"/projects/{project['id']}/runs/{run['id']}"
    proposal = client.get(f"{base}/mapping", headers=headers).json()["mapping_proposal"]
    confirmed = {m["target_field"]: m["source_column"] for m in proposal["mappings"]}
    client.post(f"{base}/mapping/confirm", json={"mappings": confirmed}, headers=headers)
    client.post(f"{base}/requirements/req-0000/resolve", json=R0_PATCH, headers=headers)
    assert client.post(f"{base}/source", headers=headers).status_code == 200
    plans = client.post(f"{base}/plans", json={"board_quantity": 10}, headers=headers)
    assert plans.status_code == 200
    assert client.get(base, headers=headers).json()["status"] == "planned"
    return base, headers


def test_editing_a_requirement_invalidates_candidates_and_plans(client: TestClient) -> None:
    base, headers = _planned_run(client)

    edit = client.post(
        f"{base}/requirements/req-0001/resolve",
        json={"parameters": {"tolerance_pct": {"value": "5", "unit": "percent", "raw_text": "5%"}}},
        headers=headers,
    )
    assert edit.status_code == 200
    assert client.get(base, headers=headers).json()["status"] == "normalized"

    approve = client.post(f"{base}/plans/lowest_cost/approve", json={}, headers=headers)
    assert approve.status_code == 409
    export = client.post(
        f"{base}/plans/lowest_cost/export",
        json={"supplier": "mouser", "format": "csv"},
        headers=headers,
    )
    assert export.status_code == 409
    revalidate = client.post(f"{base}/plans/lowest_cost/revalidate", headers=headers)
    assert revalidate.status_code == 409


def test_rerunning_later_steps_makes_plans_actionable_again(client: TestClient) -> None:
    base, headers = _planned_run(client)
    client.post(
        f"{base}/requirements/req-0001/resolve",
        json={"parameters": {"tolerance_pct": {"value": "5", "unit": "percent", "raw_text": "5%"}}},
        headers=headers,
    )

    assert client.post(f"{base}/source", headers=headers).status_code == 200
    assert client.get(base, headers=headers).json()["status"] == "sourced"
    assert (
        client.post(f"{base}/plans", json={"board_quantity": 10}, headers=headers).status_code
        == 200
    )
    assert client.get(base, headers=headers).json()["status"] == "planned"

    approve = client.post(f"{base}/plans/lowest_cost/approve", json={}, headers=headers)
    assert approve.status_code == 200
