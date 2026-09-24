"""Run-scoped JSON persistence for the interactive API flow.

`pipeline.runner.PipelineRunner` writes one artifact file per registered stage in a
single batch run. The M6 flow instead needs to pause between stages for engineer
input (mapping confirmation, requirement resolution, plan approval), so each stage's
*current* output is kept as one overwritable file per run directory rather than a
strict `<seq>-<stage>.json` sequence — the run directory is the API's working state,
not a `pcbpick run` artifact set. Every write is plain `model_dump(mode="json")`, so
the files stay human-readable for the same audit purposes `pipeline-stages`
instructions require of stage artifacts.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.mapping import IngestResult
from pcbpick.contracts.plan import PurchasePlan
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.exporters.stage import ExportedFile
from pcbpick.pipeline.results import Severity, StageIssue

_REQUIREMENTS_ADAPTER = TypeAdapter(list[NormalizedRequirement])
_CANDIDATES_ADAPTER = TypeAdapter(list[PartCandidate])
_PLANS_ADAPTER = TypeAdapter(list[PurchasePlan])


def _issues_to_json(issues: list[StageIssue]) -> list[dict[str, Any]]:
    return [
        {"severity": i.severity.value, "code": i.code, "message": i.message, "item_id": i.item_id}
        for i in issues
    ]


def _issues_from_json(payload: list[dict[str, Any]]) -> list[StageIssue]:
    return [
        StageIssue(
            severity=Severity(item["severity"]),
            code=item["code"],
            message=item["message"],
            item_id=item.get("item_id"),
        )
        for item in payload
    ]


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename so a concurrent read (e.g. `export_plan` reading `plans.json`
    # while `revalidate_plans` rewrites it) never observes a partially-written file.
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def save_ingest_result(run_dir: Path, result: IngestResult, issues: list[StageIssue]) -> None:
    _write(
        run_dir / "ingest.json",
        {"output": result.model_dump(mode="json"), "issues": _issues_to_json(issues)},
    )


def load_ingest_result(run_dir: Path) -> tuple[IngestResult, list[StageIssue]]:
    payload = json.loads((run_dir / "ingest.json").read_text(encoding="utf-8"))
    return IngestResult.model_validate(payload["output"]), _issues_from_json(payload["issues"])


def save_requirements(
    run_dir: Path, requirements: list[NormalizedRequirement], issues: list[StageIssue]
) -> None:
    _write(
        run_dir / "requirements.json",
        {
            "output": [r.model_dump(mode="json") for r in requirements],
            "issues": _issues_to_json(issues),
        },
    )


def load_requirements(run_dir: Path) -> tuple[list[NormalizedRequirement], list[StageIssue]]:
    payload = json.loads((run_dir / "requirements.json").read_text(encoding="utf-8"))
    return (
        _REQUIREMENTS_ADAPTER.validate_python(payload["output"]),
        _issues_from_json(payload["issues"]),
    )


def save_candidates(
    run_dir: Path, candidates: list[PartCandidate], issues: list[StageIssue]
) -> None:
    _write(
        run_dir / "candidates.json",
        {
            "output": [c.model_dump(mode="json") for c in candidates],
            "issues": _issues_to_json(issues),
        },
    )


def load_candidates(run_dir: Path) -> tuple[list[PartCandidate], list[StageIssue]]:
    payload = json.loads((run_dir / "candidates.json").read_text(encoding="utf-8"))
    return (
        _CANDIDATES_ADAPTER.validate_python(payload["output"]),
        _issues_from_json(payload["issues"]),
    )


def save_plans(
    run_dir: Path, plans: list[PurchasePlan], board_quantity: int, issues: list[StageIssue]
) -> None:
    _write(
        run_dir / "plans.json",
        {
            "output": [p.model_dump(mode="json") for p in plans],
            "board_quantity": board_quantity,
            "issues": _issues_to_json(issues),
        },
    )


def load_plans(run_dir: Path) -> tuple[list[PurchasePlan], int, list[StageIssue]]:
    payload = json.loads((run_dir / "plans.json").read_text(encoding="utf-8"))
    return (
        _PLANS_ADAPTER.validate_python(payload["output"]),
        payload["board_quantity"],
        _issues_from_json(payload["issues"]),
    )


def save_export(run_dir: Path, export_id: str, exported: ExportedFile) -> Path:
    extension = "csv" if exported.export.format.value == "csv" else "xlsx"
    file_path = run_dir / "exports" / f"{export_id}.{extension}"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(exported.file_bytes)
    _write(
        run_dir / "exports" / f"{export_id}.meta.json",
        exported.export.model_dump(mode="json"),
    )
    return file_path
