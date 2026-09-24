"""End-to-end API walkthrough: upload -> mapping confirmation -> requirement
resolution -> candidate review -> plan comparison -> approval -> export, driven only
through the HTTP surface (no CLI), against `fixtures/boms/kicad_bom.csv` and the
pinned `fixtures/catalogs/kicad_golden_snapshot.json` snapshot -- fixtures-first,
per M4/M5 precedent, since live supplier adapters are M7 scope.

`settings.clock_override` pins every `StageContext.now` close to the fixture
snapshot's `fetched_at` (2026-01-15) so stale-offer detection is deterministic
regardless of the real wall-clock date, per
`.github/instructions/testing.instructions.md`.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pcbpick.api.app import create_app
from pcbpick.api.settings import Settings
from tests.api.conftest import FIXTURE_CATALOG, auth_headers, create_project, register_user

KICAD_BOM = Path(__file__).resolve().parents[2] / "fixtures" / "boms" / "kicad_bom.csv"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite://",
        runs_root=tmp_path / "runs",
        catalog_snapshot_paths=(str(FIXTURE_CATALOG),),
        clock_override=datetime(2026, 1, 20, tzinfo=UTC),
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def _upload(client: TestClient, project_id: str, headers: dict[str, str]) -> dict[str, object]:
    with KICAD_BOM.open("rb") as fh:
        response = client.post(
            f"/projects/{project_id}/runs",
            files={"file": ("kicad_bom.csv", fh, "text/csv")},
            headers=headers,
        )
    assert response.status_code == 200, response.text
    return response.json()


def _resolve(
    client: TestClient, base: str, requirement_id: str, headers: dict[str, str], **body: object
) -> dict[str, object]:
    response = client.post(
        f"{base}/requirements/{requirement_id}/resolve", json=body, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_full_flow_from_upload_through_export(client: TestClient) -> None:
    user = register_user(client, "Ada Engineer")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "Test Board Rev A")
    project_id = project["id"]

    # 1. Upload
    run = _upload(client, project_id, headers)
    run_id = run["id"]
    base = f"/projects/{project_id}/runs/{run_id}"
    assert run["status"] == "awaiting_mapping_confirmation"

    # 2. Mapping confirmation
    mapping = client.get(f"{base}/mapping", headers=headers)
    assert mapping.status_code == 200, mapping.text
    proposal = mapping.json()["mapping_proposal"]
    confirmed = {m["target_field"]: m["source_column"] for m in proposal["mappings"]}
    confirm = client.post(f"{base}/mapping/confirm", json={"mappings": confirmed}, headers=headers)
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "normalized"

    # 3. Requirement resolution -- fill every unresolved field an engineer would see
    requirements = client.get(f"{base}/requirements", headers=headers).json()["requirements"]
    assert any(r["unresolved"] for r in requirements)

    _resolve(
        client,
        base,
        "req-0000",
        headers,
        parameters={"tolerance_pct": {"value": "1", "unit": "percent", "raw_text": "1%"}},
        footprint={
            "package_code": "RESC1608X55N",
            "pin_count": 2,
            "length_mm": "1.6",
            "width_mm": "0.8",
            "height_mm": "0.55",
        },
    )
    _resolve(
        client,
        base,
        "req-0001",
        headers,
        parameters={"tolerance_pct": {"value": "1", "unit": "percent", "raw_text": "1%"}},
        footprint={
            "package_code": "RESC1005X40N",
            "pin_count": 2,
            "length_mm": "1.0",
            "width_mm": "0.5",
            "height_mm": "0.4",
        },
    )
    for req_id, code, dims in (
        ("req-0002", "CAPC1005X55N", {"length_mm": "1.0", "width_mm": "0.5", "height_mm": "0.55"}),
        (
            "req-0003",
            "CAPC2012X125N",
            {"length_mm": "2.0", "width_mm": "1.25", "height_mm": "1.25"},
        ),
        ("req-0004", "CAPC1608X90N", {"length_mm": "1.6", "width_mm": "0.8", "height_mm": "0.9"}),
    ):
        _resolve(
            client,
            base,
            req_id,
            headers,
            parameters={
                # Below the 50%-of-rated Class II ceramic derating threshold for a
                # 16V-rated candidate, per `.github/skills/substitution-policy/SKILL.md`.
                "voltage_rating": {"value": "5", "unit": "volt", "raw_text": "5V"},
                "dielectric": {"raw_text": "X7R"},
            },
            footprint={"pin_count": 2, "package_code": code, **dims},
        )
    _resolve(
        client,
        base,
        "req-0005",
        headers,
        category="ic_analog",
        footprint={
            "package_code": "SOIC127P600X175-8N",
            "pin_count": 8,
            "pitch_mm": "1.27",
            "length_mm": "4.9",
            "width_mm": "3.9",
            "height_mm": "1.75",
        },
    )
    _resolve(
        client,
        base,
        "req-0006",
        headers,
        parameters={"frequency": {"value": "16000000", "unit": "hertz", "raw_text": "16MHz"}},
    )
    _resolve(
        client,
        base,
        "req-0007",
        headers,
        parameters={"pin_count": {"value": "4", "unit": "count", "raw_text": "4"}},
        footprint={"package_code": "PinHeader_1x04_P2.54mm"},
    )
    _resolve(
        client,
        base,
        "req-0009",
        headers,
        category="mechanical",
        footprint={"package_code": "TestPoint_Pad_1.5x1.5mm"},
    )

    requirements = client.get(f"{base}/requirements", headers=headers).json()["requirements"]
    assert all(not r["unresolved"] for r in requirements), requirements

    # 4. Candidate review
    sourced = client.post(f"{base}/source", headers=headers)
    assert sourced.status_code == 200, sourced.text
    candidates = sourced.json()["candidates"]
    matched_ids = {c["requirement_id"] for c in candidates}
    assert {
        "req-0000",
        "req-0001",
        "req-0002",
        "req-0003",
        "req-0004",
    }.issubset(matched_ids)
    # per-line evidence: policy results and a datasheet-derived rationale slot exist
    for candidate in candidates:
        assert candidate["policy_results"]

    # 5. Plan comparison
    plans_response = client.post(f"{base}/plans", json={"board_quantity": 100}, headers=headers)
    assert plans_response.status_code == 200, plans_response.text
    plans = plans_response.json()["plans"]
    assert len(plans) == 5  # one per DecisionMode
    for plan in plans:
        assert plan["unfilled"] == []

    plan = next(p for p in plans if p["mode"] == "lowest_cost")
    high_tier_ids = sorted(
        {line["requirement_id"] for line in plan["lines"] if line["substitution_tier"] >= 2}
    )
    stale_snapshot_ids = sorted(
        {
            w["requirement_id"]
            for w in plan["warnings"]
            if w["kind"] == "stale_offer" and w["requirement_id"]
        }
    )

    # 6. Approval (append-only ledger)
    approval = client.post(
        f"{base}/plans/lowest_cost/approve",
        json={
            "reviewed_high_tier_requirement_ids": high_tier_ids,
            "acknowledged_stale_offer_snapshot_ids": stale_snapshot_ids,
            "note": "reviewed candidate rationale and policy results",
        },
        headers=headers,
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["decision_mode"] == "lowest_cost"

    approvals = client.get(f"{base}/approvals", headers=headers).json()
    assert len(approvals) == 1

    # 7. Export
    export = client.post(
        f"{base}/plans/lowest_cost/export",
        json={"supplier": "mouser", "format": "csv"},
        headers=headers,
    )
    assert export.status_code == 200, export.text
    export_body = export.json()

    download = client.get(export_body["download_url"], headers=headers)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")


def test_export_blocked_without_approval(client: TestClient) -> None:
    user = register_user(client, "Bea Engineer")
    headers = auth_headers(user["api_key"])
    project = create_project(client, user["api_key"], "No Approval Project")
    project_id = project["id"]

    run = _upload(client, project_id, headers)
    base = f"/projects/{project_id}/runs/{run['id']}"
    proposal = client.get(f"{base}/mapping", headers=headers).json()["mapping_proposal"]
    confirmed = {m["target_field"]: m["source_column"] for m in proposal["mappings"]}
    client.post(f"{base}/mapping/confirm", json={"mappings": confirmed}, headers=headers)
    _resolve(
        client,
        base,
        "req-0000",
        headers,
        parameters={"tolerance_pct": {"value": "1", "unit": "percent", "raw_text": "1%"}},
    )
    client.post(f"{base}/source", headers=headers)
    client.post(f"{base}/plans", json={"board_quantity": 10}, headers=headers)

    export = client.post(
        f"{base}/plans/lowest_cost/export",
        json={"supplier": "mouser", "format": "csv"},
        headers=headers,
    )
    assert export.status_code == 409
