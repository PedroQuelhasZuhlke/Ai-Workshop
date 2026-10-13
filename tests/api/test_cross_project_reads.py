"""A run id from one project must never be readable through another project's URL."""

from pathlib import Path

import pytest
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


def _planned_run(client: TestClient, api_key: str) -> str:
    headers = auth_headers(api_key)
    project = create_project(client, api_key, "Board A")
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
    assert (
        client.post(f"{base}/plans", json={"board_quantity": 10}, headers=headers).status_code
        == 200
    )
    return run["id"]


@pytest.mark.parametrize(
    "suffix",
    ["", "/mapping", "/requirements", "/candidates", "/plans", "/approvals", "/exports"],
)
def test_run_data_is_not_readable_through_another_project(
    client: TestClient, suffix: str
) -> None:
    alice = register_user(client, "Alice")
    run_id = _planned_run(client, alice["api_key"])

    mallory = register_user(client, "Mallory")
    own_project = create_project(client, mallory["api_key"], "Mallory Board")

    response = client.get(
        f"/projects/{own_project['id']}/runs/{run_id}{suffix}",
        headers=auth_headers(mallory["api_key"]),
    )
    assert response.status_code == 404, response.text
