"""Orchestrates registered stages against a run directory."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from typing import Any
from uuid import uuid4

from pcbpick.errors import RunNotFoundError, StageNotFoundError
from pcbpick.ingest.mapping_store import MappingProfileStore
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.models import RunManifest, StageMeta
from pcbpick.pipeline.results import StageResult
from pcbpick.pipeline.stage import Stage

# Registered in execution order. The rest land with normalize/classify in M2.
STAGES: list[Stage] = [IngestStage()]

DEFAULT_MAPPING_PROFILES_ROOT = Path("mapping_profiles")


class PipelineRunner:
    """Runs `STAGES` in order against a source file, writing artifacts as it goes."""

    def __init__(self, runs_root: Path, mapping_profiles_root: Path | None = None) -> None:
        self._runs_root = runs_root
        self._mapping_profiles_root = mapping_profiles_root or DEFAULT_MAPPING_PROFILES_ROOT

    def run(
        self, source_file: Path, *, run_id: str | None = None, project_id: str | None = None
    ) -> str:
        run_id = run_id or uuid4().hex
        run_dir = self._runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        now = datetime.now(UTC)
        manifest = RunManifest(
            run_id=run_id,
            created_at=now,
            source_file=str(source_file),
            source_file_sha256=_sha256_file(source_file),
        )

        project_mapping = None
        if project_id is not None:
            project_mapping = MappingProfileStore(self._mapping_profiles_root).load(project_id)

        ctx = StageContext(run_id=run_id, now=now, rng=Random(run_id), config=PipelineConfig())
        payload: Any = IngestInput(
            file_name=source_file.name,
            content=source_file.read_bytes(),
            project_mapping=project_mapping,
        )
        stage_metas: list[StageMeta] = []
        for seq, stage in enumerate(STAGES):
            input_hash = _hash_json(payload)
            config_hash = _hash_json(ctx.config.model_dump(mode="json"))
            started = time.monotonic()
            result = stage.run(payload, ctx)
            duration = time.monotonic() - started

            _write_stage_artifact(run_dir, seq, stage.name, result)
            stage_metas.append(
                StageMeta(
                    seq=seq,
                    stage_name=stage.name,
                    input_hash=input_hash,
                    config_hash=config_hash,
                    duration_seconds=duration,
                    issue_counts=_count_issues(result),
                )
            )
            payload = result.output

        manifest = manifest.model_copy(update={"stages": stage_metas})
        _write_json(run_dir / "meta.json", manifest.model_dump(mode="json"))
        return run_id

    def resume(self, run_id: str, *, from_stage: str) -> None:
        run_dir = self._runs_root / run_id
        if not run_dir.exists():
            raise RunNotFoundError(f"no run directory for {run_id!r}")

        names = [stage.name for stage in STAGES]
        if from_stage not in names:
            raise StageNotFoundError(
                f"stage {from_stage!r} is not registered; registered stages: {names!r}"
            )
        # Loading the prior artifact and re-running downstream stages lands with the
        # first real stage in M1 — there is nothing to resume from yet.


def _count_issues(result: StageResult[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in result.issues:
        counts[issue.severity.value] = counts.get(issue.severity.value, 0) + 1
    return counts


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_stage_artifact(
    run_dir: Path, seq: int, stage_name: str, result: StageResult[Any]
) -> None:
    artifact_path = run_dir / f"{seq:03d}-{stage_name}.json"
    output = result.output
    if hasattr(output, "model_dump"):
        serialized_output = output.model_dump(mode="json")
    elif isinstance(output, list):
        serialized_output = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in output
        ]
    else:
        serialized_output = output
    payload = {
        "output": serialized_output,
        "issues": [
            {
                "severity": issue.severity.value,
                "code": issue.code,
                "message": issue.message,
                "item_id": issue.item_id,
            }
            for issue in result.issues
        ],
    }
    _write_json(artifact_path, payload)
